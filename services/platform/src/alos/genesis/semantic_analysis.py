"""Bounded, source-only semantic analysis through the shared Model Gateway.

Genesis does not upload files or grant tools to the provider.  It sends a
bounded text extract from one approved INTERNAL document, then stores the
result as a human-reviewable ALOS artifact and DRAFT.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from decimal import Decimal
from math import ceil
from typing import Any
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, Field

from alos.config import Settings
from alos.model_gateway import (
    GatewayProvider,
    GuardedModelGateway,
    ModelGateway,
    ModelGatewayError,
    ModelRequest,
    ModelResponse,
    ModelUsage,
    RetryingModelGateway,
    UsageBudget,
)
from alos.persistence.database import psycopg_url

_MAX_SOURCE_CHARACTERS = 60_000


class GenesisSemanticAnalysisError(RuntimeError):
    """A safe error at the external-model boundary."""


class GenesisSemanticAnalysisResult(BaseModel):
    """The non-secret execution metadata and reviewable model answer."""

    analysis_run_id: UUID
    provider: GatewayProvider
    model: str
    answer: str = Field(min_length=1)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_milliseconds: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)
    source_characters: int = Field(ge=0)


class GenesisSemanticAnalysisRepository:
    """Reserve the existing workspace budget before a document reaches a provider."""

    def __init__(self, database_url: str, settings: Settings) -> None:
        self._database_url = psycopg_url(database_url)
        self._settings = settings

    def reserve(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        source_document_id: UUID,
        source_version_number: int,
        source_content_sha256: str,
        actor_user_id: UUID,
        correlation_id: UUID,
        prompt: str,
        input_text: str,
        max_output_tokens: int,
    ) -> UUID:
        input_tokens = _estimated_input_tokens(input_text)
        model = self._settings.model_for_route("standard")
        reserved_cost = self._settings.estimate_llm_cost_usd(
            model=model,
            input_tokens=input_tokens,
            output_tokens=max_output_tokens,
        )
        with self._transaction() as connection:
            self._require_workspace_actor(connection, organization_id, workspace_id, actor_user_id)
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"alos-budget:{organization_id}:{workspace_id}",),
            )
            limit = self._workspace_limit(connection, organization_id, workspace_id)
            usage = self._today_usage(connection, organization_id, workspace_id)
            if usage["requests"] >= limit["daily_request_limit"]:
                raise GenesisSemanticAnalysisError("daily request budget cap reached")
            if usage["output_tokens"] + max_output_tokens > limit["daily_output_token_limit"]:
                raise GenesisSemanticAnalysisError("daily output token budget cap reached")
            if usage["cost_usd"] + reserved_cost > Decimal(str(limit["daily_cost_cap_usd"])):
                raise GenesisSemanticAnalysisError("daily cost budget cap reached")
            row = connection.execute(
                """
                INSERT INTO genesis.semantic_analysis_runs (
                    organization_id, workspace_id, source_document_id, requested_by_user_id,
                    correlation_id, source_version_number, source_content_sha256, prompt_sha256,
                    data_classification, status, requested_output_tokens, reserved_cost_usd, model
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'INTERNAL', 'RUNNING', %s, %s, %s)
                RETURNING semantic_analysis_run_id
                """,
                (
                    organization_id,
                    workspace_id,
                    source_document_id,
                    actor_user_id,
                    correlation_id,
                    source_version_number,
                    source_content_sha256,
                    _sha256(prompt),
                    max_output_tokens,
                    reserved_cost,
                    model,
                ),
            ).fetchone()
            if row is None:
                raise GenesisSemanticAnalysisError("semantic analysis budget reservation failed")
            run_id = UUID(str(row["semantic_analysis_run_id"]))
            self._audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="GENESIS_SEMANTIC_ANALYSIS_RESERVED",
                entity_id=run_id,
                correlation_id=correlation_id,
                reason="Director requested one bounded INTERNAL document analysis",
                metadata={
                    "workspace_id": str(workspace_id),
                    "source_document_id": str(source_document_id),
                    "source_version_number": source_version_number,
                    "requested_output_tokens": max_output_tokens,
                    "reserved_cost_usd": str(reserved_cost),
                    "provider_storage": "store=false",
                    "tools": "none",
                    "external_web": False,
                },
            )
            return run_id

    def complete(
        self,
        run_id: UUID,
        response: ModelResponse,
        *,
        analysis_artifact_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> None:
        with self._transaction() as connection:
            row = connection.execute(
                """
                UPDATE genesis.semantic_analysis_runs
                SET status = 'SUCCEEDED', provider = %s, model = %s,
                    input_tokens = %s, output_tokens = %s, estimated_cost_usd = %s,
                    analysis_artifact_id = %s, completed_at = now()
                WHERE semantic_analysis_run_id = %s AND organization_id = %s AND status = 'RUNNING'
                RETURNING semantic_analysis_run_id
                """,
                (
                    response.provider,
                    response.model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.estimated_cost_usd,
                    analysis_artifact_id,
                    run_id,
                    organization_id,
                ),
            ).fetchone()
            if row is None:
                raise GenesisSemanticAnalysisError("semantic analysis run could not be completed")
            self._audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="GENESIS_SEMANTIC_ANALYSIS_COMPLETED",
                entity_id=run_id,
                correlation_id=correlation_id,
                reason="Genesis stored a source-bound model answer as a human-review DRAFT",
                metadata={
                    "provider": response.provider,
                    "model": response.model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "estimated_cost_usd": str(response.estimated_cost_usd),
                    "analysis_artifact_id": str(analysis_artifact_id),
                },
            )

    def fail(
        self,
        run_id: UUID,
        error: Exception,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> None:
        code = error.code if isinstance(error, ModelGatewayError) else "GENESIS_ANALYSIS_FAILED"
        with self._transaction() as connection:
            updated = connection.execute(
                """
                UPDATE genesis.semantic_analysis_runs
                SET status = 'FAILED', failure_code = %s, completed_at = now()
                WHERE semantic_analysis_run_id = %s AND organization_id = %s AND status = 'RUNNING'
                RETURNING semantic_analysis_run_id
                """,
                (code, run_id, organization_id),
            ).fetchone()
            if updated is None:
                return
            self._audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="GENESIS_SEMANTIC_ANALYSIS_FAILED",
                entity_id=run_id,
                correlation_id=correlation_id,
                reason="Genesis semantic analysis did not produce a reviewable answer",
                metadata={"failure_code": code},
            )

    def _workspace_limit(
        self, connection: psycopg.Connection[Any], organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        row = connection.execute(
            """
            SELECT daily_request_limit, daily_output_token_limit, daily_cost_cap_usd
            FROM governance.cost_limits
            WHERE organization_id = %s AND workspace_id = %s AND active
            """,
            (organization_id, workspace_id),
        ).fetchone()
        if row is None:
            if self._settings.environment not in {"local", "test"}:
                raise GenesisSemanticAnalysisError("an active workspace cost limit is required")
            row = connection.execute(
                """
                INSERT INTO governance.cost_limits (
                    organization_id, workspace_id, daily_request_limit,
                    daily_output_token_limit, daily_cost_cap_usd
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING daily_request_limit, daily_output_token_limit, daily_cost_cap_usd
                """,
                (
                    organization_id,
                    workspace_id,
                    self._settings.llm_daily_request_limit,
                    self._settings.llm_daily_output_token_limit,
                    self._settings.llm_daily_cost_cap_usd,
                ),
            ).fetchone()
        if row is None:
            raise GenesisSemanticAnalysisError("workspace cost limit could not be read")
        return dict(row)

    def _today_usage(
        self, connection: psycopg.Connection[Any], organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        window = "(date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s)"
        row = connection.execute(
            f"""
            SELECT count(*) AS requests,
                   coalesce(sum(output_tokens), 0) AS output_tokens,
                   coalesce(sum(cost_usd), 0) AS cost_usd
            FROM (
                SELECT ledger.output_tokens, ledger.estimated_cost_usd AS cost_usd
                FROM observability.usage_ledger AS ledger
                JOIN runtime.agent_runs AS run ON run.agent_run_id = ledger.agent_run_id
                WHERE run.organization_id = %s AND run.workspace_id = %s
                  AND run.created_at >= {window}

                UNION ALL

                SELECT output_tokens, estimated_cost_usd AS cost_usd
                FROM genesis.semantic_analysis_runs
                WHERE organization_id = %s AND workspace_id = %s AND status = 'SUCCEEDED'
                  AND created_at >= {window}

                UNION ALL

                SELECT CASE WHEN status = 'FAILED'
                              THEN coalesce(output_tokens, requested_output_tokens)
                            ELSE output_tokens END AS output_tokens,
                       CASE WHEN status = 'FAILED'
                              THEN coalesce(estimated_cost_usd, reserved_cost_usd)
                            ELSE estimated_cost_usd END AS cost_usd
                FROM genesis.follow_up_runs
                WHERE organization_id = %s AND workspace_id = %s
                  AND status IN ('SUCCEEDED', 'FAILED')
                  AND created_at >= {window}

                UNION ALL

                SELECT reserved_output_tokens AS output_tokens, reserved_cost_usd AS cost_usd
                FROM runtime.budget_reservations
                WHERE organization_id = %s AND workspace_id = %s
                  AND created_at >= {window}

                UNION ALL

                SELECT requested_output_tokens AS output_tokens, reserved_cost_usd AS cost_usd
                FROM genesis.semantic_analysis_runs
                WHERE organization_id = %s AND workspace_id = %s AND status = 'RUNNING'
                  AND created_at >= {window}

                UNION ALL

                SELECT requested_output_tokens AS output_tokens, reserved_cost_usd AS cost_usd
                FROM genesis.follow_up_runs
                WHERE organization_id = %s AND workspace_id = %s AND status = 'RUNNING'
                  AND created_at >= {window}
            ) AS daily_usage
            """,
            (
                organization_id,
                workspace_id,
                self._settings.budget_timezone,
                self._settings.budget_timezone,
                organization_id,
                workspace_id,
                self._settings.budget_timezone,
                self._settings.budget_timezone,
                organization_id,
                workspace_id,
                self._settings.budget_timezone,
                self._settings.budget_timezone,
                organization_id,
                workspace_id,
                self._settings.budget_timezone,
                self._settings.budget_timezone,
                organization_id,
                workspace_id,
                self._settings.budget_timezone,
                self._settings.budget_timezone,
                organization_id,
                workspace_id,
                self._settings.budget_timezone,
                self._settings.budget_timezone,
            ),
        ).fetchone()
        if row is None:
            raise GenesisSemanticAnalysisError("semantic analysis usage could not be read")
        return dict(row)

    @staticmethod
    def _require_workspace_actor(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        workspace_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        actor = connection.execute(
            """
            SELECT 1 FROM identity.users AS user_record
            JOIN workspace.memberships AS membership ON membership.user_id = user_record.user_id
            JOIN workspace.workspaces AS workspace
              ON workspace.workspace_id = membership.workspace_id
            WHERE user_record.organization_id = %s AND user_record.user_id = %s
              AND workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE'
            """,
            (organization_id, actor_user_id, workspace_id, organization_id),
        ).fetchone()
        if actor is None:
            raise GenesisSemanticAnalysisError("active workspace membership is required")

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any], *, organization_id: UUID, actor_user_id: UUID,
        action: str, entity_id: UUID, correlation_id: UUID, reason: str, metadata: dict[str, Any]
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, 'GENESIS_SEMANTIC_ANALYSIS', %s, %s, %s, %s)
            """,
            (
                organization_id,
                actor_user_id,
                action,
                entity_id,
                correlation_id,
                reason,
                Jsonb(metadata),
            ),
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection[Any]]:
        with self._connection() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise


class GenesisSemanticAnalyzer:
    """Call exactly one provider request with no tools or external research."""

    def __init__(
        self,
        settings: Settings,
        gateway_factory: Callable[[], tuple[ModelGateway, Callable[[], None]]],
        usage: GenesisSemanticAnalysisRepository,
    ) -> None:
        self._settings = settings
        self._gateway_factory = gateway_factory
        self._usage = usage

    def analyze(
        self,
        *,
        organization_id: UUID,
        workspace_id: UUID,
        source_document_id: UUID,
        source_version_number: int,
        source_content_sha256: str,
        source_title: str,
        source_content: str,
        prompt: str,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> GenesisSemanticAnalysisResult:
        if not self._settings.genesis_semantic_analysis_enabled:
            raise GenesisSemanticAnalysisError("semantic Genesis analysis is not enabled")
        if len(source_content) > _MAX_SOURCE_CHARACTERS:
            raise GenesisSemanticAnalysisError(
                "source is too large for one safe analysis; "
                "prepare a shorter approved extract first"
            )
        if not source_content.strip():
            raise GenesisSemanticAnalysisError(
                "source has no extracted text; prepare an approved text extract first"
            )
        input_text = _analysis_input(
            source_title,
            source_version_number,
            source_content_sha256,
            source_content,
            prompt,
        )
        output_limit = self._settings.genesis_semantic_max_output_tokens
        run_id = self._usage.reserve(
            organization_id=organization_id,
            workspace_id=workspace_id,
            source_document_id=source_document_id,
            source_version_number=source_version_number,
            source_content_sha256=source_content_sha256,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            prompt=prompt,
            input_text=input_text,
            max_output_tokens=output_limit,
        )
        close_gateway: Callable[[], None] | None = None
        try:
            delegate, close_gateway = self._gateway_factory()
            response = GuardedModelGateway(
                RetryingModelGateway(delegate, self._settings.llm_max_retries),
                self._settings,
                UsageBudget(request_limit=1, output_token_limit=output_limit),
            ).generate(
                ModelRequest(
                    correlation_id=correlation_id,
                    model=self._settings.model_for_route("standard"),
                    instructions=_analysis_instructions(),
                    input_text=input_text,
                    data_classification="INTERNAL",
                    max_output_tokens=output_limit,
                )
            )
            answer = response.output_text.strip()
            validate_genesis_answer(answer, source_content)
            return GenesisSemanticAnalysisResult(
                analysis_run_id=run_id,
                provider=response.provider,
                model=response.model,
                answer=answer,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_milliseconds=response.latency_milliseconds,
                estimated_cost_usd=response.estimated_cost_usd,
                source_characters=len(source_content),
            )
        except Exception as error:
            self._usage.fail(
                run_id,
                error,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
            )
            if isinstance(error, GenesisSemanticAnalysisError):
                raise
            if isinstance(error, ModelGatewayError):
                raise GenesisSemanticAnalysisError(str(error)) from error
            raise GenesisSemanticAnalysisError(
                "semantic Genesis analysis could not be completed"
            ) from error
        finally:
            if close_gateway is not None:
                close_gateway()

    def complete(
        self,
        response: GenesisSemanticAnalysisResult,
        *,
        analysis_artifact_id: UUID,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> None:
        self._usage.complete(
            response.analysis_run_id,
            ModelResponse(
                provider=response.provider,
                model=response.model,
                output_text=response.answer,
                usage=ModelUsage(
                    input_tokens=response.input_tokens, output_tokens=response.output_tokens
                ),
                latency_milliseconds=response.latency_milliseconds,
                estimated_cost_usd=response.estimated_cost_usd,
            ),
            analysis_artifact_id=analysis_artifact_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )

    def fail(
        self,
        response: GenesisSemanticAnalysisResult,
        error: Exception,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> None:
        """Close a reserved run if local DRAFT persistence fails after generation."""

        self._usage.fail(
            response.analysis_run_id,
            error,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
        )


def _analysis_instructions() -> str:
    return """You are GENESIS, a governed internal document analyst.

Use only the numbered SOURCE TEXT supplied by ALOS. Do not browse, call tools,
use external knowledge, invent facts, make approvals, change data, or propose
that any action has already been completed. Reply in Indonesian.

Write concise Markdown with these headings:
1. Jawaban ringkas
2. Temuan dan kekurangan
3. Checklist perbaikan
4. Batasan dan informasi yang belum tersedia
5. Sumber

For each material factual statement, cite the matching source lines exactly as
`[Sumber L12-L18]`. If the source does not contain an answer, explicitly say
`Tidak ditemukan pada sumber yang disetujui.` Recommendations must be marked
as recommendations, not facts. Under "Checklist perbaikan", use a numbered
list of passive recommendations; do not use Markdown task checkboxes, do not
claim that any item is complete, and do not ask a user to tick an item. The
Director confirms, rejects, or prioritises recommendations through the Genesis
conversation. The result is a DRAFT for human review.
"""


def _analysis_input(
    source_title: str,
    source_version_number: int,
    source_content_sha256: str,
    source_content: str,
    prompt: str,
) -> str:
    numbered_lines = "\n".join(
        f"L{index}: {line}"
        for index, line in enumerate(source_content.splitlines() or [source_content], start=1)
    )
    return "\n\n".join(
        (
            "SOURCE METADATA",
            (
                f"Title: {source_title}\nVersion: {source_version_number}\n"
                f"SHA-256: {source_content_sha256}\nClassification: INTERNAL"
            ),
            "SOURCE TEXT (the only permitted evidence)",
            numbered_lines,
            "USER QUESTION",
            prompt.strip(),
        )
    )


def _estimated_input_tokens(value: str) -> int:
    return max(1, ceil(len(value) / 4))


def validate_genesis_answer(answer: str, source_content: str) -> None:
    """Reject an answer that cannot be reviewed against the supplied source."""

    required_sections = (
        "jawaban ringkas",
        "temuan dan kekurangan",
        "checklist perbaikan",
        "batasan dan informasi yang belum tersedia",
        "sumber",
    )
    normalized = answer.casefold()
    missing_sections = [section for section in required_sections if section not in normalized]
    if missing_sections:
        raise GenesisSemanticAnalysisError(
            "model answer is missing required review sections: " + ", ".join(missing_sections)
        )
    citations = list(re.finditer(r"\[Sumber L(\d+)(?:-L?(\d+))?\]", answer))
    if not citations:
        raise GenesisSemanticAnalysisError("model answer has no source-line citation")
    source_line_count = max(1, len(source_content.splitlines()))
    for citation in citations:
        start = int(citation.group(1))
        end = int(citation.group(2) or start)
        if start < 1 or end < start or end > source_line_count:
            raise GenesisSemanticAnalysisError(
                "model answer cites a line outside the approved source"
            )


# Keep the former private name for internal compatibility while the public
# validator is shared by document analysis and conversational follow-ups.
_validate_answer = validate_genesis_answer


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
