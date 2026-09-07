"""Two-way, source-bound Genesis conversation follow-ups.

Every eligible prompt remains attached to the immutable source version from
the first analysis.  A follow-up may add conversation messages, but it never
advances a document workflow or mutates a document.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from math import ceil
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.config import Settings
from alos.genesis.history import GenesisMessageRecord
from alos.genesis.semantic_analysis import (
    GenesisSemanticAnalysisError,
    validate_genesis_answer,
)
from alos.model_gateway import (
    GatewayProvider,
    GuardedModelGateway,
    ModelGateway,
    ModelGatewayError,
    ModelRequest,
    ModelResponse,
    RetryingModelGateway,
    UsageBudget,
)
from alos.persistence.database import psycopg_url

FollowUpStatus = Literal["SUCCEEDED", "BLOCKED", "FAILED"]
_MAX_HISTORY_TURNS = 8
_MAX_HISTORY_TOKENS = 4_000


class GenesisFollowUpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: UUID
    content: str = Field(min_length=3, max_length=10_000)


class GenesisFollowUpWorkflowReference(BaseModel):
    workflow_id: UUID
    status: str


class GenesisFollowUpSourceReference(BaseModel):
    document_id: UUID
    title: str
    version_number: int
    content_sha256: str
    classification: Literal["INTERNAL"]


class GenesisFollowUpModelExecution(BaseModel):
    follow_up_run_id: UUID
    provider: GatewayProvider
    model: str
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_milliseconds: int = Field(ge=0)
    estimated_cost_usd: Decimal = Field(ge=0)
    history_turns_included: int = Field(ge=0)
    estimated_context_tokens: int = Field(ge=0)


class GenesisFollowUpResponse(BaseModel):
    status: Literal["SUCCEEDED"] = "SUCCEEDED"
    correlation_id: UUID
    idempotent_replay: bool = False
    workflow: GenesisFollowUpWorkflowReference
    source: GenesisFollowUpSourceReference
    human_message: GenesisMessageRecord
    genesis_message: GenesisMessageRecord
    model_execution: GenesisFollowUpModelExecution


class GenesisFollowUpErrorDetail(BaseModel):
    code: str
    message: str


class GenesisFollowUpErrorResponse(BaseModel):
    status: Literal["BLOCKED", "FAILED"]
    correlation_id: UUID
    error: GenesisFollowUpErrorDetail


class GenesisFollowUpError(RuntimeError):
    """A safe, classified follow-up failure suitable for the API boundary."""

    status: Literal["BLOCKED", "FAILED"]

    def __init__(self, code: str, message: str, correlation_id: UUID) -> None:
        self.code = code
        self.correlation_id = correlation_id
        self.estimated_context_tokens = 0
        super().__init__(message)

    def response(self) -> GenesisFollowUpErrorResponse:
        return GenesisFollowUpErrorResponse(
            status=self.status,
            correlation_id=self.correlation_id,
            error=GenesisFollowUpErrorDetail(code=self.code, message=str(self)),
        )


class GenesisFollowUpBlocked(GenesisFollowUpError):
    status: Literal["BLOCKED"] = "BLOCKED"


class GenesisFollowUpFailed(GenesisFollowUpError):
    status: Literal["FAILED"] = "FAILED"


@dataclass(frozen=True, slots=True)
class _HistoryTurn:
    human: str
    genesis: str


@dataclass(frozen=True, slots=True)
class _FollowUpContext:
    workflow_id: UUID
    workflow_status: str
    organization_id: UUID
    workspace_id: UUID
    conversation_id: UUID
    source_document_id: UUID
    source_title: str
    source_version_number: int
    source_content_sha256: str
    source_classification: str
    source_origin: str
    source_status: str
    source_content: str | None
    stored_source_sha256: str | None
    initial_answer: str
    history: tuple[_HistoryTurn, ...]

    @property
    def workflow_reference(self) -> GenesisFollowUpWorkflowReference:
        return GenesisFollowUpWorkflowReference(
            workflow_id=self.workflow_id,
            status=self.workflow_status,
        )

    @property
    def source_reference(self) -> GenesisFollowUpSourceReference:
        return GenesisFollowUpSourceReference(
            document_id=self.source_document_id,
            title=self.source_title,
            version_number=self.source_version_number,
            content_sha256=self.source_content_sha256,
            classification=cast(Literal["INTERNAL"], self.source_classification),
        )


@dataclass(frozen=True, slots=True)
class _WindowedInput:
    input_text: str
    history_turns_included: int
    estimated_context_tokens: int


@dataclass(frozen=True, slots=True)
class _PreparedFollowUp:
    run_id: UUID
    human_message: GenesisMessageRecord


class GenesisFollowUpRepository:
    """Durable idempotency, message persistence, budgets, and audit events."""

    def __init__(self, database_url: str, settings: Settings) -> None:
        self._database_url = psycopg_url(database_url)
        self._settings = settings

    def replay(
        self,
        *,
        organization_id: UUID,
        conversation_id: UUID,
        correlation_id: UUID,
        prompt: str,
    ) -> GenesisFollowUpResponse | None:
        with self._connection() as connection:
            row = self._existing_run(connection, organization_id, correlation_id)
            if row is None:
                return None
            return self._replay_row(connection, row, conversation_id, prompt)

    def load_context(
        self,
        conversation_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> _FollowUpContext:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT workflow.workflow_id, workflow.status AS workflow_status,
                       workflow.organization_id, workflow.workspace_id,
                       workflow.conversation_id, workflow.source_document_id,
                       workflow.source_version_number, workflow.source_content_sha256,
                       conversation.status AS conversation_status,
                       source.title AS source_title,
                       source.classification AS source_classification,
                       source.origin AS source_origin, source.status AS source_status,
                       source_version.content AS source_content,
                       source_version.content_sha256 AS stored_source_sha256,
                       analysis_artifact.content AS analysis_artifact_content,
                       analysis_version.content AS analysis_draft_content
                FROM genesis.document_workflows AS workflow
                JOIN genesis.conversations AS conversation
                  ON conversation.conversation_id = workflow.conversation_id
                JOIN workspace.memberships AS membership
                  ON membership.workspace_id = workflow.workspace_id
                JOIN documents.records AS source
                  ON source.document_id = workflow.source_document_id
                 AND source.organization_id = workflow.organization_id
                 AND source.workspace_id = workflow.workspace_id
                LEFT JOIN documents.versions AS source_version
                  ON source_version.document_id = workflow.source_document_id
                 AND source_version.version_number = workflow.source_version_number
                LEFT JOIN LATERAL (
                    SELECT artifact.content
                    FROM genesis.artifacts AS artifact
                    WHERE artifact.conversation_id = workflow.conversation_id
                      AND artifact.artifact_type = 'ANALYSIS'
                    ORDER BY artifact.version DESC
                    LIMIT 1
                ) AS analysis_artifact ON true
                LEFT JOIN LATERAL (
                    SELECT version.content
                    FROM documents.versions AS version
                    WHERE version.document_id = workflow.analysis_document_id
                    ORDER BY version.version_number DESC
                    LIMIT 1
                ) AS analysis_version ON true
                WHERE workflow.conversation_id = %s
                  AND workflow.organization_id = %s
                  AND membership.user_id = %s
                """,
                (conversation_id, organization_id, actor_user_id),
            ).fetchone()
            if row is None:
                raise GenesisFollowUpBlocked(
                    "FOLLOW_UP_NOT_AVAILABLE",
                    "Percakapan tidak terikat ke analisis dokumen yang tersedia.",
                    correlation_id,
                )
            if row["conversation_status"] != "OPEN":
                raise GenesisFollowUpBlocked(
                    "CONVERSATION_CLOSED",
                    "Percakapan Genesis sudah ditutup.",
                    correlation_id,
                )
            artifact_content = row["analysis_artifact_content"]
            initial_answer = ""
            if isinstance(artifact_content, dict):
                answer = artifact_content.get("answer")
                if isinstance(answer, str):
                    initial_answer = answer.strip()
            if not initial_answer:
                draft_content = row["analysis_draft_content"]
                if isinstance(draft_content, str):
                    initial_answer = draft_content.strip()
            history_rows = connection.execute(
                """
                SELECT human.content AS human_content, genesis.content AS genesis_content
                FROM genesis.follow_up_runs AS run
                JOIN genesis.messages AS human ON human.message_id = run.human_message_id
                JOIN genesis.messages AS genesis ON genesis.message_id = run.genesis_message_id
                WHERE run.organization_id = %s AND run.conversation_id = %s
                  AND run.status = 'SUCCEEDED'
                ORDER BY run.created_at DESC, run.follow_up_run_id DESC
                LIMIT %s
                """,
                (organization_id, conversation_id, _MAX_HISTORY_TURNS),
            ).fetchall()
        history = tuple(
            _HistoryTurn(human=item["human_content"], genesis=item["genesis_content"])
            for item in reversed(history_rows)
        )
        return _FollowUpContext(
            workflow_id=row["workflow_id"],
            workflow_status=row["workflow_status"],
            organization_id=row["organization_id"],
            workspace_id=row["workspace_id"],
            conversation_id=row["conversation_id"],
            source_document_id=row["source_document_id"],
            source_title=row["source_title"],
            source_version_number=row["source_version_number"],
            source_content_sha256=row["source_content_sha256"],
            source_classification=row["source_classification"],
            source_origin=row["source_origin"],
            source_status=row["source_status"],
            source_content=row["source_content"],
            stored_source_sha256=row["stored_source_sha256"],
            initial_answer=initial_answer,
            history=history,
        )

    def record_blocked(
        self,
        context: _FollowUpContext,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
        prompt: str,
        code: str,
        message: str,
        estimated_context_tokens: int = 0,
    ) -> GenesisFollowUpBlocked | GenesisFollowUpResponse:
        with self._transaction() as connection:
            self._lock_correlation(connection, context.organization_id, correlation_id)
            existing = self._existing_run(connection, context.organization_id, correlation_id)
            if existing is not None:
                return self._replay_row(
                    connection, existing, context.conversation_id, prompt
                )
            run_id = self._insert_run(
                connection,
                context,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
                prompt=prompt,
                status="BLOCKED",
                requested_output_tokens=self._settings.genesis_follow_up_max_output_tokens,
                reserved_cost=Decimal("0"),
                model=self._settings.model_for_route("standard"),
                estimated_context_tokens=estimated_context_tokens,
                history_turns_included=0,
                failure_code=code,
                failure_message=message,
            )
            self._audit_prompt(
                connection, context, actor_user_id, correlation_id, run_id, prompt
            )
            self._audit_run(
                connection,
                context,
                actor_user_id,
                correlation_id,
                run_id,
                action="GENESIS_FOLLOW_UP_BLOCKED",
                reason=message,
                metadata={"failure_code": code},
            )
        return GenesisFollowUpBlocked(code, message, correlation_id)

    def reserve(
        self,
        context: _FollowUpContext,
        window: _WindowedInput,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
        prompt: str,
    ) -> _PreparedFollowUp | GenesisFollowUpResponse | GenesisFollowUpBlocked:
        output_limit = self._settings.genesis_follow_up_max_output_tokens
        model = self._settings.model_for_route("standard")
        reserved_cost = self._settings.estimate_llm_cost_usd(
            model=model,
            input_tokens=_conservative_input_token_bound(
                _follow_up_instructions(), window.input_text
            ),
            output_tokens=output_limit,
        )
        with self._transaction() as connection:
            self._lock_correlation(connection, context.organization_id, correlation_id)
            existing = self._existing_run(connection, context.organization_id, correlation_id)
            if existing is not None:
                return self._replay_row(
                    connection, existing, context.conversation_id, prompt
                )
            workflow = connection.execute(
                """
                SELECT status, source_document_id, source_version_number,
                       source_content_sha256
                FROM genesis.document_workflows
                WHERE workflow_id = %s AND organization_id = %s
                FOR UPDATE
                """,
                (context.workflow_id, context.organization_id),
            ).fetchone()
            if workflow is None or workflow["status"] != "ANALYSIS_DRAFT":
                return self._record_blocked_in_transaction(
                    connection,
                    context,
                    actor_user_id=actor_user_id,
                    correlation_id=correlation_id,
                    prompt=prompt,
                    code="WORKFLOW_STATUS_INVALID",
                    message="Follow-up hanya tersedia saat workflow berstatus ANALYSIS_DRAFT.",
                    estimated_context_tokens=window.estimated_context_tokens,
                )
            if (
                workflow["source_document_id"] != context.source_document_id
                or workflow["source_version_number"] != context.source_version_number
                or workflow["source_content_sha256"] != context.source_content_sha256
            ):
                return self._record_blocked_in_transaction(
                    connection,
                    context,
                    actor_user_id=actor_user_id,
                    correlation_id=correlation_id,
                    prompt=prompt,
                    code="SOURCE_BINDING_CHANGED",
                    message="Binding dokumen sumber tidak lagi sama dengan analisis awal.",
                    estimated_context_tokens=window.estimated_context_tokens,
                )
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"alos-budget:{context.organization_id}:{context.workspace_id}",),
            )
            blocked = self._budget_block(
                connection,
                context,
                correlation_id=correlation_id,
                output_limit=output_limit,
                reserved_cost=reserved_cost,
            )
            if blocked is not None:
                code, message = blocked
                return self._record_blocked_in_transaction(
                    connection,
                    context,
                    actor_user_id=actor_user_id,
                    correlation_id=correlation_id,
                    prompt=prompt,
                    code=code,
                    message=message,
                    estimated_context_tokens=window.estimated_context_tokens,
                )
            human_row = connection.execute(
                """
                INSERT INTO genesis.messages (
                    conversation_id, actor_kind, actor_user_id, content
                ) VALUES (%s, 'HUMAN', %s, %s)
                RETURNING message_id, conversation_id, actor_kind, actor_user_id,
                          system_actor, content, created_at
                """,
                (context.conversation_id, actor_user_id, prompt),
            ).fetchone()
            if human_row is None:
                raise GenesisFollowUpFailed(
                    "FOLLOW_UP_PERSISTENCE_FAILED",
                    "Pesan Direktur tidak dapat disimpan.",
                    correlation_id,
                )
            run_id = self._insert_run(
                connection,
                context,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
                prompt=prompt,
                status="RUNNING",
                requested_output_tokens=output_limit,
                reserved_cost=reserved_cost,
                model=model,
                estimated_context_tokens=window.estimated_context_tokens,
                history_turns_included=window.history_turns_included,
                human_message_id=human_row["message_id"],
            )
            self._audit_prompt(
                connection, context, actor_user_id, correlation_id, run_id, prompt
            )
            self._audit_run(
                connection,
                context,
                actor_user_id,
                correlation_id,
                run_id,
                action="GENESIS_FOLLOW_UP_MODEL_REQUESTED",
                reason="Director requested one bounded, source-only Genesis follow-up",
                metadata={
                    "requested_output_tokens": output_limit,
                    "reserved_cost_usd": str(reserved_cost),
                    "estimated_context_tokens": window.estimated_context_tokens,
                    "history_turns_included": window.history_turns_included,
                    "provider_storage": "store=false",
                    "tools": "none",
                    "external_web": False,
                },
            )
            return _PreparedFollowUp(
                run_id=run_id,
                human_message=GenesisMessageRecord(**human_row),
            )

    def complete(
        self,
        context: _FollowUpContext,
        prepared: _PreparedFollowUp,
        response: ModelResponse,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
        answer: str,
    ) -> GenesisFollowUpResponse:
        with self._transaction() as connection:
            genesis_row = connection.execute(
                """
                INSERT INTO genesis.messages (
                    conversation_id, actor_kind, system_actor, content
                ) VALUES (%s, 'SYSTEM', 'GENESIS', %s)
                RETURNING message_id, conversation_id, actor_kind, actor_user_id,
                          system_actor, content, created_at
                """,
                (context.conversation_id, answer),
            ).fetchone()
            if genesis_row is None:
                raise GenesisFollowUpFailed(
                    "FOLLOW_UP_PERSISTENCE_FAILED",
                    "Balasan Genesis tidak dapat disimpan.",
                    correlation_id,
                )
            run = connection.execute(
                """
                UPDATE genesis.follow_up_runs
                SET status = 'SUCCEEDED', provider = %s, model = %s,
                    input_tokens = %s, output_tokens = %s,
                    latency_milliseconds = %s, estimated_cost_usd = %s,
                    genesis_message_id = %s, completed_at = now()
                WHERE follow_up_run_id = %s AND organization_id = %s
                  AND status = 'RUNNING'
                RETURNING follow_up_run_id, history_turns_included,
                          estimated_context_tokens
                """,
                (
                    response.provider,
                    response.model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.latency_milliseconds,
                    response.estimated_cost_usd,
                    genesis_row["message_id"],
                    prepared.run_id,
                    context.organization_id,
                ),
            ).fetchone()
            if run is None:
                raise GenesisFollowUpFailed(
                    "FOLLOW_UP_PERSISTENCE_FAILED",
                    "Run follow-up Genesis tidak dapat diselesaikan.",
                    correlation_id,
                )
            self._audit_run(
                connection,
                context,
                actor_user_id,
                correlation_id,
                prepared.run_id,
                action="GENESIS_FOLLOW_UP_COMPLETED",
                reason="Genesis stored one validated reply without changing the workflow",
                metadata={
                    "provider": response.provider,
                    "model": response.model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                    "estimated_cost_usd": str(response.estimated_cost_usd),
                    "genesis_message_id": str(genesis_row["message_id"]),
                },
            )
        return GenesisFollowUpResponse(
            correlation_id=correlation_id,
            workflow=context.workflow_reference,
            source=context.source_reference,
            human_message=prepared.human_message,
            genesis_message=GenesisMessageRecord(**genesis_row),
            model_execution=GenesisFollowUpModelExecution(
                follow_up_run_id=prepared.run_id,
                provider=response.provider,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                latency_milliseconds=response.latency_milliseconds,
                estimated_cost_usd=response.estimated_cost_usd,
                history_turns_included=run["history_turns_included"],
                estimated_context_tokens=run["estimated_context_tokens"],
            ),
        )

    def fail(
        self,
        context: _FollowUpContext,
        prepared: _PreparedFollowUp,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
        code: str,
        message: str,
        response: ModelResponse | None = None,
    ) -> None:
        with self._transaction() as connection:
            values: tuple[object, ...]
            if response is None:
                values = (code, message, prepared.run_id, context.organization_id)
                sql = """
                    UPDATE genesis.follow_up_runs
                    SET status = 'FAILED', failure_code = %s, failure_message = %s,
                        completed_at = now()
                    WHERE follow_up_run_id = %s AND organization_id = %s
                      AND status = 'RUNNING'
                    RETURNING follow_up_run_id
                """
            else:
                values = (
                    code,
                    message,
                    response.provider,
                    response.model,
                    response.usage.input_tokens,
                    response.usage.output_tokens,
                    response.latency_milliseconds,
                    response.estimated_cost_usd,
                    prepared.run_id,
                    context.organization_id,
                )
                sql = """
                    UPDATE genesis.follow_up_runs
                    SET status = 'FAILED', failure_code = %s, failure_message = %s,
                        provider = %s, model = %s, input_tokens = %s, output_tokens = %s,
                        latency_milliseconds = %s, estimated_cost_usd = %s,
                        completed_at = now()
                    WHERE follow_up_run_id = %s AND organization_id = %s
                      AND status = 'RUNNING'
                    RETURNING follow_up_run_id
                """
            updated = connection.execute(sql, values).fetchone()
            if updated is None:
                return
            self._audit_run(
                connection,
                context,
                actor_user_id,
                correlation_id,
                prepared.run_id,
                action="GENESIS_FOLLOW_UP_FAILED",
                reason="Genesis follow-up did not produce a validated reply",
                metadata={"failure_code": code},
            )

    def _record_blocked_in_transaction(
        self,
        connection: psycopg.Connection[Any],
        context: _FollowUpContext,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
        prompt: str,
        code: str,
        message: str,
        estimated_context_tokens: int,
    ) -> GenesisFollowUpBlocked:
        run_id = self._insert_run(
            connection,
            context,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            prompt=prompt,
            status="BLOCKED",
            requested_output_tokens=self._settings.genesis_follow_up_max_output_tokens,
            reserved_cost=Decimal("0"),
            model=self._settings.model_for_route("standard"),
            estimated_context_tokens=estimated_context_tokens,
            history_turns_included=0,
            failure_code=code,
            failure_message=message,
        )
        self._audit_prompt(connection, context, actor_user_id, correlation_id, run_id, prompt)
        self._audit_run(
            connection,
            context,
            actor_user_id,
            correlation_id,
            run_id,
            action="GENESIS_FOLLOW_UP_BLOCKED",
            reason=message,
            metadata={"failure_code": code},
        )
        return GenesisFollowUpBlocked(code, message, correlation_id)

    def _budget_block(
        self,
        connection: psycopg.Connection[Any],
        context: _FollowUpContext,
        *,
        correlation_id: UUID,
        output_limit: int,
        reserved_cost: Decimal,
    ) -> tuple[str, str] | None:
        limit = self._workspace_limit(
            connection,
            context.organization_id,
            context.workspace_id,
            correlation_id,
        )
        if limit is None:
            return "WORKSPACE_COST_LIMIT_REQUIRED", "Workspace memerlukan batas biaya aktif."
        usage = self._today_usage(
            connection,
            context.organization_id,
            context.workspace_id,
            correlation_id,
        )
        if usage["requests"] >= limit["daily_request_limit"]:
            return "DAILY_REQUEST_LIMIT_REACHED", "Batas permintaan model harian telah tercapai."
        if usage["output_tokens"] + output_limit > limit["daily_output_token_limit"]:
            return (
                "DAILY_OUTPUT_TOKEN_LIMIT_REACHED",
                "Batas token keluaran harian telah tercapai.",
            )
        if usage["cost_usd"] + reserved_cost > Decimal(str(limit["daily_cost_cap_usd"])):
            return "DAILY_COST_LIMIT_REACHED", "Batas biaya model harian telah tercapai."
        return None

    def _workspace_limit(
        self,
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        workspace_id: UUID,
        correlation_id: UUID,
    ) -> dict[str, Any] | None:
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
                return None
            row = connection.execute(
                """
                INSERT INTO governance.cost_limits (
                    organization_id, workspace_id, daily_request_limit,
                    daily_output_token_limit, daily_cost_cap_usd
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING daily_request_limit, daily_output_token_limit,
                          daily_cost_cap_usd
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
            raise GenesisFollowUpFailed(
                "FOLLOW_UP_PERSISTENCE_FAILED",
                "Batas biaya workspace tidak dapat dibaca.",
                correlation_id,
            )
        return dict(row)

    def _today_usage(
        self,
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        workspace_id: UUID,
        correlation_id: UUID,
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

                SELECT reserved_output_tokens AS output_tokens,
                       reserved_cost_usd AS cost_usd
                FROM runtime.budget_reservations
                WHERE organization_id = %s AND workspace_id = %s
                  AND created_at >= {window}

                UNION ALL

                SELECT requested_output_tokens AS output_tokens,
                       reserved_cost_usd AS cost_usd
                FROM genesis.semantic_analysis_runs
                WHERE organization_id = %s AND workspace_id = %s AND status = 'RUNNING'
                  AND created_at >= {window}

                UNION ALL

                SELECT requested_output_tokens AS output_tokens,
                       reserved_cost_usd AS cost_usd
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
            raise GenesisFollowUpFailed(
                "FOLLOW_UP_PERSISTENCE_FAILED",
                "Pemakaian budget follow-up tidak dapat dibaca.",
                correlation_id,
            )
        usage = dict(row)
        usage["cost_usd"] = Decimal(str(usage["cost_usd"]))
        return usage

    @staticmethod
    def _insert_run(
        connection: psycopg.Connection[Any],
        context: _FollowUpContext,
        *,
        actor_user_id: UUID,
        correlation_id: UUID,
        prompt: str,
        status: Literal["RUNNING", "BLOCKED"],
        requested_output_tokens: int,
        reserved_cost: Decimal,
        model: str,
        estimated_context_tokens: int,
        history_turns_included: int,
        human_message_id: UUID | None = None,
        failure_code: str | None = None,
        failure_message: str | None = None,
    ) -> UUID:
        row = connection.execute(
            """
            INSERT INTO genesis.follow_up_runs (
                organization_id, workspace_id, workflow_id, conversation_id,
                source_document_id, requested_by_user_id, correlation_id,
                source_version_number, source_content_sha256, prompt_sha256,
                data_classification, status, requested_output_tokens,
                reserved_cost_usd, model, estimated_context_tokens,
                history_turns_included, human_message_id, failure_code,
                failure_message, completed_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                'INTERNAL', %s, %s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s = 'BLOCKED' THEN now() ELSE NULL END
            )
            RETURNING follow_up_run_id
            """,
            (
                context.organization_id,
                context.workspace_id,
                context.workflow_id,
                context.conversation_id,
                context.source_document_id,
                actor_user_id,
                correlation_id,
                context.source_version_number,
                context.source_content_sha256,
                _sha256(prompt),
                status,
                requested_output_tokens,
                reserved_cost,
                model,
                estimated_context_tokens,
                history_turns_included,
                human_message_id,
                failure_code,
                failure_message,
                status,
            ),
        ).fetchone()
        if row is None:
            raise GenesisFollowUpFailed(
                "FOLLOW_UP_PERSISTENCE_FAILED",
                "Run follow-up Genesis tidak dapat disimpan.",
                correlation_id,
            )
        return UUID(str(row["follow_up_run_id"]))

    @staticmethod
    def _existing_run(
        connection: psycopg.Connection[Any], organization_id: UUID, correlation_id: UUID
    ) -> dict[str, Any] | None:
        row = connection.execute(
            """
            SELECT run.*, source.title AS source_title,
                   source.classification AS source_classification,
                   workflow.status AS workflow_status
            FROM genesis.follow_up_runs AS run
            JOIN documents.records AS source
              ON source.document_id = run.source_document_id
            JOIN genesis.document_workflows AS workflow
              ON workflow.workflow_id = run.workflow_id
            WHERE run.organization_id = %s AND run.correlation_id = %s
            """,
            (organization_id, correlation_id),
        ).fetchone()
        return dict(row) if row is not None else None

    @staticmethod
    def _lock_correlation(
        connection: psycopg.Connection[Any], organization_id: UUID, correlation_id: UUID
    ) -> None:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (f"alos-follow-up:{organization_id}:{correlation_id}",),
        )

    def _replay_row(
        self,
        connection: psycopg.Connection[Any],
        row: dict[str, Any],
        conversation_id: UUID,
        prompt: str,
    ) -> GenesisFollowUpResponse:
        correlation_id = UUID(str(row["correlation_id"]))
        if row["conversation_id"] != conversation_id or row["prompt_sha256"] != _sha256(prompt):
            raise GenesisFollowUpBlocked(
                "IDEMPOTENCY_CONFLICT",
                "Correlation ID sudah digunakan untuk payload follow-up yang berbeda.",
                correlation_id,
            )
        if row["status"] == "RUNNING":
            raise GenesisFollowUpBlocked(
                "FOLLOW_UP_IN_PROGRESS",
                "Genesis masih memproses follow-up dengan correlation ID ini.",
                correlation_id,
            )
        if row["status"] == "BLOCKED":
            raise GenesisFollowUpBlocked(
                row["failure_code"] or "FOLLOW_UP_BLOCKED",
                row["failure_message"] or "Follow-up diblokir oleh kebijakan.",
                correlation_id,
            )
        if row["status"] == "FAILED":
            raise GenesisFollowUpFailed(
                row["failure_code"] or "FOLLOW_UP_FAILED",
                row["failure_message"] or "Follow-up Genesis gagal.",
                correlation_id,
            )
        human = self._load_message(
            connection, row["human_message_id"], correlation_id
        )
        genesis = self._load_message(
            connection, row["genesis_message_id"], correlation_id
        )
        return GenesisFollowUpResponse(
            correlation_id=correlation_id,
            idempotent_replay=True,
            workflow=GenesisFollowUpWorkflowReference(
                workflow_id=row["workflow_id"], status="ANALYSIS_DRAFT"
            ),
            source=GenesisFollowUpSourceReference(
                document_id=row["source_document_id"],
                title=row["source_title"],
                version_number=row["source_version_number"],
                content_sha256=row["source_content_sha256"],
                classification=row["source_classification"],
            ),
            human_message=human,
            genesis_message=genesis,
            model_execution=GenesisFollowUpModelExecution(
                follow_up_run_id=row["follow_up_run_id"],
                provider=row["provider"],
                model=row["model"],
                input_tokens=row["input_tokens"],
                output_tokens=row["output_tokens"],
                latency_milliseconds=row["latency_milliseconds"],
                estimated_cost_usd=row["estimated_cost_usd"],
                history_turns_included=row["history_turns_included"],
                estimated_context_tokens=row["estimated_context_tokens"],
            ),
        )

    @staticmethod
    def _load_message(
        connection: psycopg.Connection[Any], message_id: UUID | None, correlation_id: UUID
    ) -> GenesisMessageRecord:
        row = connection.execute(
            """
            SELECT message_id, conversation_id, actor_kind, actor_user_id,
                   system_actor, content, created_at
            FROM genesis.messages
            WHERE message_id = %s
            """,
            (message_id,),
        ).fetchone()
        if row is None:
            raise GenesisFollowUpFailed(
                "FOLLOW_UP_PERSISTENCE_FAILED",
                "Pesan follow-up tersimpan tidak dapat dibaca.",
                correlation_id,
            )
        return GenesisMessageRecord(**row)

    @staticmethod
    def _audit_prompt(
        connection: psycopg.Connection[Any],
        context: _FollowUpContext,
        actor_user_id: UUID,
        correlation_id: UUID,
        run_id: UUID,
        prompt: str,
    ) -> None:
        GenesisFollowUpRepository._audit_run(
            connection,
            context,
            actor_user_id,
            correlation_id,
            run_id,
            action="GENESIS_FOLLOW_UP_PROMPT_RECORDED",
            reason="Director submitted a follow-up prompt for a source-bound analysis",
            metadata={"prompt_sha256": _sha256(prompt)},
        )

    @staticmethod
    def _audit_run(
        connection: psycopg.Connection[Any],
        context: _FollowUpContext,
        actor_user_id: UUID,
        correlation_id: UUID,
        run_id: UUID,
        *,
        action: str,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, 'GENESIS_FOLLOW_UP', %s, %s, %s, %s)
            """,
            (
                context.organization_id,
                actor_user_id,
                action,
                run_id,
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


class GenesisFollowUpService:
    """Generate one validated conversational reply through the shared gateway."""

    def __init__(
        self,
        settings: Settings,
        repository: GenesisFollowUpRepository,
        gateway_factory: Callable[[], tuple[ModelGateway, Callable[[], None]]],
    ) -> None:
        self._settings = settings
        self._repository = repository
        self._gateway_factory = gateway_factory

    def follow_up(
        self,
        conversation_id: UUID,
        request: GenesisFollowUpRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> GenesisFollowUpResponse:
        replay = self._repository.replay(
            organization_id=organization_id,
            conversation_id=conversation_id,
            correlation_id=request.correlation_id,
            prompt=request.content,
        )
        if replay is not None:
            return replay
        context = self._repository.load_context(
            conversation_id,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=request.correlation_id,
        )
        blocked = self._precondition_block(context)
        if blocked is not None:
            code, message = blocked
            result = self._repository.record_blocked(
                context,
                actor_user_id=actor_user_id,
                correlation_id=request.correlation_id,
                prompt=request.content,
                code=code,
                message=message,
            )
            if isinstance(result, GenesisFollowUpResponse):
                return result
            raise result
        assert context.source_content is not None
        try:
            window = build_follow_up_input(
                context,
                request.content,
                max_context_tokens=self._settings.llm_max_context_tokens,
            )
        except GenesisFollowUpBlocked as error:
            result = self._repository.record_blocked(
                context,
                actor_user_id=actor_user_id,
                correlation_id=request.correlation_id,
                prompt=request.content,
                code=error.code,
                message=str(error),
                estimated_context_tokens=error.estimated_context_tokens,
            )
            if isinstance(result, GenesisFollowUpResponse):
                return result
            raise result from error
        reservation = self._repository.reserve(
            context,
            window,
            actor_user_id=actor_user_id,
            correlation_id=request.correlation_id,
            prompt=request.content,
        )
        if isinstance(reservation, GenesisFollowUpResponse):
            return reservation
        if isinstance(reservation, GenesisFollowUpBlocked):
            raise reservation
        close_gateway: Callable[[], None] | None = None
        model_response: ModelResponse | None = None
        try:
            delegate, close_gateway = self._gateway_factory()
            model_response = GuardedModelGateway(
                RetryingModelGateway(delegate, self._settings.llm_max_retries),
                self._settings,
                UsageBudget(
                    request_limit=1,
                    output_token_limit=self._settings.genesis_follow_up_max_output_tokens,
                ),
            ).generate(
                ModelRequest(
                    correlation_id=request.correlation_id,
                    model=self._settings.model_for_route("standard"),
                    instructions=_follow_up_instructions(),
                    input_text=window.input_text,
                    data_classification="INTERNAL",
                    max_output_tokens=self._settings.genesis_follow_up_max_output_tokens,
                )
            )
            answer = model_response.output_text.strip()
            validate_genesis_answer(answer, context.source_content)
            return self._repository.complete(
                context,
                reservation,
                model_response,
                actor_user_id=actor_user_id,
                correlation_id=request.correlation_id,
                answer=answer,
            )
        except Exception as error:
            code = _failure_code(error)
            message = _failure_message(error)
            self._repository.fail(
                context,
                reservation,
                actor_user_id=actor_user_id,
                correlation_id=request.correlation_id,
                code=code,
                message=message,
                response=model_response,
            )
            raise GenesisFollowUpFailed(code, message, request.correlation_id) from error
        finally:
            if close_gateway is not None:
                close_gateway()

    def _precondition_block(
        self, context: _FollowUpContext
    ) -> tuple[str, str] | None:
        if not self._settings.genesis_conversation_follow_up_enabled:
            return "FOLLOW_UP_DISABLED", "Percakapan dua arah Genesis belum diaktifkan."
        if context.workflow_status != "ANALYSIS_DRAFT":
            return (
                "WORKFLOW_STATUS_INVALID",
                "Follow-up hanya tersedia saat workflow berstatus ANALYSIS_DRAFT.",
            )
        if context.source_classification != "INTERNAL":
            return "SOURCE_NOT_INTERNAL", "Follow-up hanya menerima sumber INTERNAL."
        if context.source_origin != "MANUAL":
            return "SOURCE_NOT_CANONICAL", "Sumber follow-up harus berupa dokumen kanonis."
        if context.source_status not in {"APPROVED", "ACTIVE"}:
            return "SOURCE_NOT_APPROVED", "Dokumen sumber tidak lagi APPROVED atau ACTIVE."
        if (
            context.source_content is None
            or context.stored_source_sha256 != context.source_content_sha256
            or _sha256(context.source_content) != context.source_content_sha256
        ):
            return (
                "SOURCE_BINDING_CHANGED",
                "Versi atau SHA-256 sumber tidak sama dengan analisis awal.",
            )
        if not context.initial_answer:
            return "INITIAL_ANALYSIS_MISSING", "Jawaban analisis awal tidak tersedia."
        return None


def build_follow_up_input(
    context: _FollowUpContext,
    prompt: str,
    *,
    max_context_tokens: int,
) -> _WindowedInput:
    """Keep mandatory evidence intact and trim only complete oldest turns."""

    if context.source_content is None:
        raise ValueError("source content is required to build a follow-up input")
    selected_reversed: list[_HistoryTurn] = []
    mandatory = _follow_up_input_text(context, prompt, ())
    mandatory_tokens = _estimated_context_tokens(_follow_up_instructions(), mandatory)
    if mandatory_tokens > max_context_tokens:
        error = GenesisFollowUpBlocked(
            "CONTEXT_LIMIT_EXCEEDED",
            (
                "Konteks wajib Genesis melampaui batas: "
                f"estimasi {mandatory_tokens}, batas {max_context_tokens}."
            ),
            UUID(int=0),
        )
        error.estimated_context_tokens = mandatory_tokens
        raise error
    history_tokens = 0
    for turn in reversed(context.history[-_MAX_HISTORY_TURNS:]):
        turn_tokens = _estimated_text_tokens(_history_turn_text(turn))
        candidate_history_tokens = history_tokens + turn_tokens
        if candidate_history_tokens > _MAX_HISTORY_TOKENS:
            break
        candidate_reversed = [*selected_reversed, turn]
        candidate = tuple(reversed(candidate_reversed))
        input_text = _follow_up_input_text(context, prompt, candidate)
        context_tokens = _estimated_context_tokens(_follow_up_instructions(), input_text)
        if context_tokens > max_context_tokens:
            break
        selected_reversed = candidate_reversed
        history_tokens = candidate_history_tokens
    selected = tuple(reversed(selected_reversed))
    input_text = _follow_up_input_text(context, prompt, selected)
    return _WindowedInput(
        input_text=input_text,
        history_turns_included=len(selected),
        estimated_context_tokens=_estimated_context_tokens(
            _follow_up_instructions(), input_text
        ),
    )


def _follow_up_instructions() -> str:
    return """You are GENESIS, a governed internal document analyst in a conversation.

Reply directly and naturally in Indonesian. Use only the numbered SOURCE TEXT,
the INITIAL ANALYSIS, and the supplied conversation. Do not browse, call tools,
use external knowledge, change a document, approve anything, or claim an action
has already happened.

Write concise Markdown with these headings:
1. Jawaban ringkas
2. Temuan dan kekurangan
3. Checklist perbaikan
4. Batasan dan informasi yang belum tersedia
5. Sumber

Every material source fact must use `[Sumber L12-L18]`. Preserve source-line
citations. Mark recommendations as recommendations and Director statements as
decisions or directions. If a direction is ambiguous, request one brief
confirmation. If the Director approves a recommendation, explain what can be
prepared next, but do not claim it has been prepared. Recommendations are not
checklist items Genesis can mark complete. Under "Checklist perbaikan", use a
numbered list without task checkboxes. The answer remains a DRAFT for human review.
"""


def _follow_up_input_text(
    context: _FollowUpContext,
    prompt: str,
    history: tuple[_HistoryTurn, ...],
) -> str:
    assert context.source_content is not None
    numbered_lines = "\n".join(
        f"L{index}: {line}"
        for index, line in enumerate(
            context.source_content.splitlines() or [context.source_content], start=1
        )
    )
    history_text = (
        "\n\n".join(_history_turn_text(turn) for turn in history)
        if history
        else "Belum ada turn follow-up sukses sebelumnya."
    )
    return "\n\n".join(
        (
            "SOURCE METADATA",
            (
                f"Title: {context.source_title}\n"
                f"Version: {context.source_version_number}\n"
                f"SHA-256: {context.source_content_sha256}\n"
                "Classification: INTERNAL"
            ),
            "SOURCE TEXT (the only permitted factual evidence)",
            numbered_lines,
            "INITIAL ANALYSIS (DRAFT, not an approved fact)",
            context.initial_answer,
            "RECENT COMPLETED CONVERSATION",
            history_text,
            "LATEST DIRECTOR PROMPT",
            prompt.strip(),
        )
    )


def _history_turn_text(turn: _HistoryTurn) -> str:
    return f"DIRECTOR:\n{turn.human}\n\nGENESIS:\n{turn.genesis}"


def _estimated_text_tokens(value: str) -> int:
    return max(1, ceil(len(value.encode("utf-8")) / 4))


def _estimated_context_tokens(instructions: str, input_text: str) -> int:
    return _estimated_text_tokens(instructions + input_text)


def _conservative_input_token_bound(instructions: str, input_text: str) -> int:
    return len((instructions + input_text).encode("utf-8"))


def _failure_code(error: Exception) -> str:
    if isinstance(error, ModelGatewayError):
        return error.code
    if isinstance(error, GenesisSemanticAnalysisError):
        return "MODEL_ANSWER_INVALID"
    if isinstance(error, GenesisFollowUpError):
        return error.code
    return "GENESIS_FOLLOW_UP_FAILED"


def _failure_message(error: Exception) -> str:
    if isinstance(error, GenesisSemanticAnalysisError):
        return "Balasan model tidak lolos validasi struktur dan sitasi Genesis."
    if isinstance(error, GenesisFollowUpFailed):
        return str(error)
    if isinstance(error, ModelGatewayError):
        return "Provider model tidak dapat menyelesaikan balasan Genesis."
    return "Follow-up Genesis tidak dapat diselesaikan."


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
