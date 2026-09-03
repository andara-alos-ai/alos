"""H3 shared Agent Runtime with deterministic budgets and tool guardrails."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.agents.registry import AgentContract
from alos.config import Settings
from alos.model_gateway import ModelGateway, ModelGatewayError, ModelResponse
from alos.persistence.database import psycopg_url

RunStatus = Literal["SUCCEEDED", "FAILED", "BLOCKED"]


class AgentRuntimeError(RuntimeError):
    """A safe, deterministic runtime failure."""


class AgentRuntimeBlocked(AgentRuntimeError):
    """The runtime refused a run before contacting the provider."""


class InputSchemaError(AgentRuntimeError):
    """The supplied fixture does not match the Contract input schema."""


class OutputSchemaError(AgentRuntimeError):
    """The provider output does not match the Contract output schema."""


class AgentRunRequest(BaseModel):
    """A human-requested, bounded runtime invocation."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    input: dict[str, Any] = Field(default_factory=dict)
    requested_tool_keys: list[str] = Field(default_factory=list)


class WorkspaceBudgetRequest(BaseModel):
    """Human-controlled daily policy; it is never selected by an LLM."""

    model_config = ConfigDict(extra="forbid")

    daily_request_limit: int = Field(ge=1, le=100_000)
    daily_output_token_limit: int = Field(ge=1_000, le=10_000_000)
    daily_cost_cap_usd: Decimal = Field(ge=0, le=1_000_000)


class WorkspaceBudget(BaseModel):
    workspace_id: UUID
    daily_request_limit: int
    daily_output_token_limit: int
    daily_cost_cap_usd: Decimal


class ToolDecision(BaseModel):
    tool_key: str
    decision: Literal["ALLOWED", "BLOCKED"]
    reason: str


class AgentRunResult(BaseModel):
    agent_run_id: UUID
    agent_key: str
    semantic_version: str
    status: RunStatus
    correlation_id: UUID
    output: dict[str, Any] | None = None
    provider: str | None = None
    model: str | None = None
    tool_decisions: list[ToolDecision] = Field(default_factory=list)
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class _ExecutionVersion:
    agent_contract_id: UUID
    agent_version_id: UUID
    agent_key: str
    semantic_version: str
    contract: AgentContract


@dataclass(frozen=True, slots=True)
class _PreparedRun:
    agent_run_id: UUID
    execution: _ExecutionVersion
    organization_id: UUID
    workspace_id: UUID
    actor_user_id: UUID
    correlation_id: UUID
    input_hash: str
    tool_decisions: tuple[ToolDecision, ...]
    fixture_context: tuple[dict[str, Any], ...]


class AgentRuntime:
    """Run every logical agent through one constrained execution path."""

    def __init__(
        self,
        repository: AgentRuntimeRepository,
        gateway: ModelGateway,
        settings: Settings,
        close_gateway: Callable[[], None] | None = None,
    ) -> None:
        self._repository = repository
        self._gateway = gateway
        self._settings = settings
        self._close_gateway = close_gateway

    def execute(
        self,
        agent_key: str,
        request: AgentRunRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID | None = None,
    ) -> AgentRunResult:
        correlation_id = correlation_id or uuid4()
        prepared = self._repository.prepare_run(
            agent_key,
            request,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            correlation_id=correlation_id,
            max_output_tokens=self._max_output_tokens,
        )
        if isinstance(prepared, AgentRunResult):
            self._close()
            return prepared

        response: ModelResponse | None = None
        try:
            model_request = self._model_request(
                prepared.execution.contract, request, prepared.fixture_context
            )
            response = self._gateway.generate(model_request)
            output = _parse_and_validate_output(
                response.output_text, prepared.execution.contract.output_schema
            )
        except AgentRuntimeBlocked as error:
            self._repository.complete_failure(prepared, str(error))
            return _failure_result(prepared, "CONTRACT_POLICY_BLOCKED")
        except OutputSchemaError as error:
            self._repository.complete_failure(prepared, str(error), response=response)
            return _failure_result(prepared, "OUTPUT_SCHEMA_INVALID")
        except ModelGatewayError as error:
            self._repository.complete_failure(prepared, error.code)
            return _failure_result(prepared, error.code)
        finally:
            self._close()

        self._repository.complete_success(prepared, response, output)
        return AgentRunResult(
            agent_run_id=prepared.agent_run_id,
            agent_key=prepared.execution.agent_key,
            semantic_version=prepared.execution.semantic_version,
            status="SUCCEEDED",
            correlation_id=prepared.correlation_id,
            output=output,
            provider=response.provider,
            model=response.model,
            tool_decisions=list(prepared.tool_decisions),
        )

    @property
    def _max_output_tokens(self) -> int:
        return self._settings.llm_max_output_tokens

    def _model_request(
        self,
        contract: AgentContract,
        request: AgentRunRequest,
        fixture_context: tuple[dict[str, Any], ...],
    ) -> Any:
        from alos.model_gateway import ModelRequest

        configured_provider = contract.model_policy.get("provider")
        if configured_provider not in {None, self._settings.llm_provider}:
            raise AgentRuntimeBlocked("contract model provider does not match Model Gateway policy")
        configured_limit = contract.model_policy.get("max_output_tokens", self._max_output_tokens)
        if isinstance(configured_limit, bool) or not isinstance(configured_limit, int):
            raise AgentRuntimeBlocked("contract output token policy is invalid")
        output_limit = min(configured_limit, self._max_output_tokens)
        if output_limit < 1:
            raise AgentRuntimeBlocked("contract output token policy is invalid")
        return ModelRequest(
            instructions=(
                f"{contract.prompt_template}\n\n"
                "Return JSON only. Do not take actions. "
                "The JSON must conform to this output schema: "
                f"{json.dumps(contract.output_schema, ensure_ascii=False)}"
            ),
            input_text=json.dumps(
                {"input": request.input, "read_only_fixture_context": fixture_context},
                ensure_ascii=False,
            ),
            data_classification="INTERNAL",
            max_output_tokens=output_limit,
        )

    def _close(self) -> None:
        if self._close_gateway is not None:
            self._close_gateway()


class AgentRuntimeRepository:
    """Persist executions, budgets, tool decisions, usage, and audit events."""

    def __init__(self, database_url: str, settings: Settings) -> None:
        self._database_url = psycopg_url(database_url)
        self._settings = settings

    def prepare_run(
        self,
        agent_key: str,
        request: AgentRunRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        max_output_tokens: int,
    ) -> _PreparedRun | AgentRunResult:
        with self._transaction() as connection:
            self._require_actor_workspace(
                connection, organization_id, actor_user_id, request.workspace_id
            )
            execution = self._load_execution(
                connection, organization_id, request.workspace_id, agent_key
            )
            input_hash = _digest(request.input)
            try:
                _validate_json_schema(request.input, execution.contract.input_schema, "input")
            except InputSchemaError as error:
                return self._block_run(
                    connection,
                    execution,
                    organization_id,
                    request.workspace_id,
                    actor_user_id,
                    correlation_id,
                    input_hash,
                    tool_key="INPUT_SCHEMA",
                    reason=str(error),
                )
            tool_evaluation = self._evaluate_tools(
                connection,
                execution,
                organization_id,
                request.requested_tool_keys,
                request.input,
            )
            if isinstance(tool_evaluation, ToolDecision):
                return self._block_run(
                    connection,
                    execution,
                    organization_id,
                    request.workspace_id,
                    actor_user_id,
                    correlation_id,
                    input_hash,
                    tool_key=tool_evaluation.tool_key,
                    reason=tool_evaluation.reason,
                )
            decisions, fixture_context = tool_evaluation
            agent_run_id = self._reserve_budget_and_create_run(
                connection,
                execution,
                organization_id,
                request.workspace_id,
                actor_user_id,
                correlation_id,
                input_hash,
                max_output_tokens,
            )
            for decision in decisions:
                connection.execute(
                    """
                    INSERT INTO runtime.tool_calls (agent_run_id, tool_key, decision, reason)
                    VALUES (%s, %s, 'ALLOWED', %s)
                    """,
                    (agent_run_id, decision.tool_key, decision.reason),
                )
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="AGENT_RUN_STARTED",
                entity_type="AGENT_RUN",
                entity_id=agent_run_id,
                correlation_id=correlation_id,
                reason="Human requested a bounded Agent Runtime execution",
                metadata={"agent_key": execution.agent_key, "version": execution.semantic_version},
            )
            return _PreparedRun(
                agent_run_id=agent_run_id,
                execution=execution,
                organization_id=organization_id,
                workspace_id=request.workspace_id,
                actor_user_id=actor_user_id,
                correlation_id=correlation_id,
                input_hash=input_hash,
                tool_decisions=tuple(decisions),
                fixture_context=tuple(fixture_context),
            )

    def get_budget_limit(
        self,
        workspace_id: UUID,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
    ) -> WorkspaceBudget:
        with self._connection() as connection:
            self._require_actor_workspace(connection, organization_id, actor_user_id, workspace_id)
            limit = connection.execute(
                """
                SELECT daily_request_limit, daily_output_token_limit, daily_cost_cap_usd
                FROM governance.cost_limits
                WHERE organization_id = %s AND workspace_id = %s AND active
                """,
                (organization_id, workspace_id),
            ).fetchone()
            if limit is None:
                raise AgentRuntimeBlocked("an active workspace cost limit was not found")
            return WorkspaceBudget(workspace_id=workspace_id, **limit)

    def set_budget_limit(
        self,
        workspace_id: UUID,
        request: WorkspaceBudgetRequest,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
    ) -> WorkspaceBudget:
        with self._transaction() as connection:
            self._require_actor_workspace(connection, organization_id, actor_user_id, workspace_id)
            connection.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%s))",
                (f"alos-budget:{organization_id}:{workspace_id}",),
            )
            existing = connection.execute(
                """
                SELECT cost_limit_id FROM governance.cost_limits
                WHERE organization_id = %s AND workspace_id = %s AND active
                FOR UPDATE
                """,
                (organization_id, workspace_id),
            ).fetchone()
            if existing is None:
                updated = connection.execute(
                    """
                    INSERT INTO governance.cost_limits (
                        organization_id, workspace_id, daily_request_limit,
                        daily_output_token_limit, daily_cost_cap_usd
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING cost_limit_id
                    """,
                    (
                        organization_id,
                        workspace_id,
                        request.daily_request_limit,
                        request.daily_output_token_limit,
                        request.daily_cost_cap_usd,
                    ),
                ).fetchone()
            else:
                updated = connection.execute(
                    """
                    UPDATE governance.cost_limits
                    SET daily_request_limit = %s, daily_output_token_limit = %s,
                        daily_cost_cap_usd = %s
                    WHERE cost_limit_id = %s
                    RETURNING cost_limit_id
                    """,
                    (
                        request.daily_request_limit,
                        request.daily_output_token_limit,
                        request.daily_cost_cap_usd,
                        existing["cost_limit_id"],
                    ),
                ).fetchone()
            if updated is None:
                raise AgentRuntimeError("workspace cost limit could not be updated")
            self._append_audit(
                connection,
                organization_id=organization_id,
                actor_user_id=actor_user_id,
                action="COST_LIMIT_UPDATED",
                entity_type="COST_LIMIT",
                entity_id=updated["cost_limit_id"],
                correlation_id=correlation_id,
                reason="Human updated the workspace Agent Runtime budget",
                metadata={
                    "workspace_id": str(workspace_id),
                    "daily_request_limit": request.daily_request_limit,
                    "daily_output_token_limit": request.daily_output_token_limit,
                    "daily_cost_cap_usd": str(request.daily_cost_cap_usd),
                },
            )
            return WorkspaceBudget(workspace_id=workspace_id, **request.model_dump())

    def complete_success(
        self, prepared: _PreparedRun, response: ModelResponse, output: dict[str, Any]
    ) -> None:
        with self._transaction() as connection:
            self._complete_usage(connection, prepared.agent_run_id, response)
            connection.execute(
                """
                UPDATE runtime.agent_runs
                SET status = 'SUCCEEDED', output_reference = %s, completed_at = now()
                WHERE agent_run_id = %s
                """,
                (
                    Jsonb({"sha256": _digest(output), "schema_valid": True}),
                    prepared.agent_run_id,
                ),
            )
            self._append_audit(
                connection,
                organization_id=prepared.organization_id,
                actor_user_id=prepared.actor_user_id,
                action="AGENT_RUN_SUCCEEDED",
                entity_type="AGENT_RUN",
                entity_id=prepared.agent_run_id,
                correlation_id=prepared.correlation_id,
                reason="Agent Runtime returned schema-valid output",
                metadata={"agent_key": prepared.execution.agent_key},
            )

    def complete_failure(
        self, prepared: _PreparedRun, reason: str, response: ModelResponse | None = None
    ) -> None:
        with self._transaction() as connection:
            if response is not None:
                self._complete_usage(connection, prepared.agent_run_id, response)
            else:
                connection.execute(
                    "DELETE FROM runtime.budget_reservations WHERE agent_run_id = %s",
                    (prepared.agent_run_id,),
                )
            connection.execute(
                """
                UPDATE runtime.agent_runs
                SET status = 'FAILED', output_reference = %s, completed_at = now()
                WHERE agent_run_id = %s
                """,
                (Jsonb({"reason": reason}), prepared.agent_run_id),
            )
            self._append_audit(
                connection,
                organization_id=prepared.organization_id,
                actor_user_id=prepared.actor_user_id,
                action="AGENT_RUN_FAILED",
                entity_type="AGENT_RUN",
                entity_id=prepared.agent_run_id,
                correlation_id=prepared.correlation_id,
                reason=reason,
                metadata={"agent_key": prepared.execution.agent_key},
            )

    def _load_execution(
        self,
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        workspace_id: UUID,
        agent_key: str,
    ) -> _ExecutionVersion:
        if self._settings.environment not in {"local", "test"}:
            raise AgentRuntimeBlocked("local runtime execution is disabled outside local/test")
        row = connection.execute(
            """
            SELECT contract.agent_contract_id, version.agent_version_id, contract.agent_key,
                   version.semantic_version, version.contract_snapshot
            FROM agents.contracts AS contract
            JOIN agents.registry AS registry
              ON registry.agent_contract_id = contract.agent_contract_id
            JOIN LATERAL (
                SELECT agent_version_id, semantic_version, contract_snapshot
                FROM agents.versions
                WHERE agent_contract_id = contract.agent_contract_id
                  AND (
                      lifecycle_status = 'DRAFT'
                      OR agent_version_id = registry.active_version_id
                  )
                ORDER BY CASE WHEN lifecycle_status = 'DRAFT' THEN 0 ELSE 1 END,
                         created_at DESC, agent_version_id DESC
                LIMIT 1
            ) AS version ON true
            WHERE contract.organization_id = %s
              AND contract.workspace_id = %s
              AND contract.agent_key = %s
            """,
            (organization_id, workspace_id, agent_key),
        ).fetchone()
        if row is None:
            raise AgentRuntimeBlocked("a local DRAFT or ACTIVE Agent Contract was not found")
        kill_switch = connection.execute(
            """
            SELECT 1 FROM governance.kill_switches
            WHERE organization_id = %s AND agent_contract_id = %s AND active
            """,
            (organization_id, row["agent_contract_id"]),
        ).fetchone()
        if kill_switch is not None:
            raise AgentRuntimeBlocked("agent kill switch is active")
        try:
            contract = AgentContract.model_validate(row["contract_snapshot"])
        except ValueError as error:
            raise AgentRuntimeBlocked("stored Agent Contract is invalid") from error
        return _ExecutionVersion(
            agent_contract_id=row["agent_contract_id"],
            agent_version_id=row["agent_version_id"],
            agent_key=row["agent_key"],
            semantic_version=row["semantic_version"],
            contract=contract,
        )

    def _evaluate_tools(
        self,
        connection: psycopg.Connection[Any],
        execution: _ExecutionVersion,
        organization_id: UUID,
        requested_tool_keys: list[str],
        fixture_input: dict[str, Any],
    ) -> tuple[list[ToolDecision], list[dict[str, Any]]] | ToolDecision:
        decisions: list[ToolDecision] = []
        fixture_context: list[dict[str, Any]] = []
        allowed_keys = set(execution.contract.tool_keys)
        for tool_key in requested_tool_keys:
            if tool_key not in allowed_keys:
                return ToolDecision(
                    tool_key=tool_key,
                    decision="BLOCKED",
                    reason="tool is outside the Agent Contract allowlist",
                )
            definition = connection.execute(
                """
                SELECT lifecycle_status, manifest FROM agents.tool_definitions
                WHERE organization_id = %s AND tool_key = %s
                """,
                (organization_id, tool_key),
            ).fetchone()
            if definition is None or definition["lifecycle_status"] != "APPROVED":
                return ToolDecision(
                    tool_key=tool_key,
                    decision="BLOCKED",
                    reason="tool is not approved in the Tool Registry",
                )
            manifest = definition["manifest"]
            if not isinstance(manifest, dict) or manifest.get("access_mode") != "READ_ONLY":
                return ToolDecision(
                    tool_key=tool_key,
                    decision="BLOCKED",
                    reason="tool is not an approved read-only tool",
                )
            if manifest.get("runtime_handler") != "FIXTURE_SOURCE_READ":
                return ToolDecision(
                    tool_key=tool_key,
                    decision="BLOCKED",
                    reason="tool has no approved H3 runtime handler",
                )
            decisions.append(
                ToolDecision(
                    tool_key=tool_key,
                    decision="ALLOWED",
                    reason="approved read-only fixture tool",
                )
            )
            fixture_context.append(_read_only_fixture(fixture_input))
        return decisions, fixture_context

    def _reserve_budget_and_create_run(
        self,
        connection: psycopg.Connection[Any],
        execution: _ExecutionVersion,
        organization_id: UUID,
        workspace_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        input_hash: str,
        max_output_tokens: int,
    ) -> UUID:
        connection.execute(
            "SELECT pg_advisory_xact_lock(hashtext(%s))",
            (f"alos-budget:{organization_id}:{workspace_id}",),
        )
        limit = self._get_or_create_local_limit(connection, organization_id, workspace_id)
        window_start_sql = "(date_trunc('day', now() AT TIME ZONE %s) AT TIME ZONE %s)"
        parameters = (self._settings.budget_timezone, self._settings.budget_timezone)
        completed = connection.execute(
            f"""
            SELECT count(*) AS requests,
                   coalesce(sum(ledger.output_tokens), 0) AS output_tokens,
                   coalesce(sum(ledger.estimated_cost_usd), 0) AS cost_usd
            FROM observability.usage_ledger AS ledger
            JOIN runtime.agent_runs AS run ON run.agent_run_id = ledger.agent_run_id
            WHERE run.organization_id = %s AND run.workspace_id = %s
              AND run.created_at >= {window_start_sql}
            """,
            (organization_id, workspace_id, *parameters),
        ).fetchone()
        reserved = connection.execute(
            f"""
            SELECT count(*) AS requests,
                   coalesce(sum(reserved_output_tokens), 0) AS output_tokens,
                   coalesce(sum(reserved_cost_usd), 0) AS cost_usd
            FROM runtime.budget_reservations
            WHERE organization_id = %s AND workspace_id = %s
              AND created_at >= {window_start_sql}
            """,
            (organization_id, workspace_id, *parameters),
        ).fetchone()
        if completed is None or reserved is None:
            raise AgentRuntimeError("daily budget usage could not be read")
        request_total = completed["requests"] + reserved["requests"]
        output_total = completed["output_tokens"] + reserved["output_tokens"]
        cost_total = Decimal(str(completed["cost_usd"])) + Decimal(str(reserved["cost_usd"]))
        if request_total >= limit["daily_request_limit"]:
            raise AgentRuntimeBlocked("daily request budget cap reached")
        if output_total + max_output_tokens > limit["daily_output_token_limit"]:
            raise AgentRuntimeBlocked("daily output token budget cap reached")
        if cost_total > Decimal(str(limit["daily_cost_cap_usd"])):
            raise AgentRuntimeBlocked("daily cost budget cap reached")
        run = connection.execute(
            """
            INSERT INTO runtime.agent_runs (
                organization_id, workspace_id, agent_version_id, requested_by_user_id,
                correlation_id, status, input_reference
            ) VALUES (%s, %s, %s, %s, %s, 'RUNNING', %s)
            RETURNING agent_run_id
            """,
            (
                organization_id,
                workspace_id,
                execution.agent_version_id,
                actor_user_id,
                correlation_id,
                Jsonb({"sha256": input_hash}),
            ),
        ).fetchone()
        if run is None:
            raise AgentRuntimeError("Agent Run could not be created")
        connection.execute(
            """
            INSERT INTO runtime.budget_reservations (
                agent_run_id, organization_id, workspace_id, reserved_output_tokens
            ) VALUES (%s, %s, %s, %s)
            """,
            (run["agent_run_id"], organization_id, workspace_id, max_output_tokens),
        )
        return cast(UUID, run["agent_run_id"])

    def _get_or_create_local_limit(
        self, connection: psycopg.Connection[Any], organization_id: UUID, workspace_id: UUID
    ) -> dict[str, Any]:
        limit = connection.execute(
            """
            SELECT daily_request_limit, daily_output_token_limit, daily_cost_cap_usd
            FROM governance.cost_limits
            WHERE organization_id = %s AND workspace_id = %s AND active
            """,
            (organization_id, workspace_id),
        ).fetchone()
        if limit is not None:
            return dict(limit)
        if self._settings.environment not in {"local", "test"}:
            raise AgentRuntimeBlocked("an active workspace cost limit is required")
        connection.execute(
            """
            INSERT INTO governance.cost_limits (
                organization_id, workspace_id, daily_request_limit,
                daily_output_token_limit, daily_cost_cap_usd
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                organization_id,
                workspace_id,
                self._settings.llm_daily_request_limit,
                self._settings.llm_daily_output_token_limit,
                self._settings.llm_daily_cost_cap_usd,
            ),
        )
        return {
            "daily_request_limit": self._settings.llm_daily_request_limit,
            "daily_output_token_limit": self._settings.llm_daily_output_token_limit,
            "daily_cost_cap_usd": self._settings.llm_daily_cost_cap_usd,
        }

    def _block_run(
        self,
        connection: psycopg.Connection[Any],
        execution: _ExecutionVersion,
        organization_id: UUID,
        workspace_id: UUID,
        actor_user_id: UUID,
        correlation_id: UUID,
        input_hash: str,
        *,
        tool_key: str,
        reason: str,
    ) -> AgentRunResult:
        run = connection.execute(
            """
            INSERT INTO runtime.agent_runs (
                organization_id, workspace_id, agent_version_id, requested_by_user_id,
                correlation_id, status, input_reference, output_reference, completed_at
            ) VALUES (%s, %s, %s, %s, %s, 'BLOCKED', %s, %s, now())
            RETURNING agent_run_id
            """,
            (
                organization_id,
                workspace_id,
                execution.agent_version_id,
                actor_user_id,
                correlation_id,
                Jsonb({"sha256": input_hash}),
                Jsonb({"reason": reason}),
            ),
        ).fetchone()
        if run is None:
            raise AgentRuntimeError("blocked Agent Run could not be recorded")
        connection.execute(
            """
            INSERT INTO runtime.tool_calls (agent_run_id, tool_key, decision, reason)
            VALUES (%s, %s, 'BLOCKED', %s)
            """,
            (run["agent_run_id"], tool_key, reason),
        )
        self._append_audit(
            connection,
            organization_id=organization_id,
            actor_user_id=actor_user_id,
            action="AGENT_RUN_BLOCKED",
            entity_type="AGENT_RUN",
            entity_id=run["agent_run_id"],
            correlation_id=correlation_id,
            reason=reason,
            metadata={"agent_key": execution.agent_key, "tool_key": tool_key},
        )
        return AgentRunResult(
            agent_run_id=run["agent_run_id"],
            agent_key=execution.agent_key,
            semantic_version=execution.semantic_version,
            status="BLOCKED",
            correlation_id=correlation_id,
            tool_decisions=[ToolDecision(tool_key=tool_key, decision="BLOCKED", reason=reason)],
            error_code="TOOL_OR_INPUT_BLOCKED",
        )

    def _complete_usage(
        self, connection: psycopg.Connection[Any], agent_run_id: UUID, response: ModelResponse
    ) -> None:
        connection.execute(
            "DELETE FROM runtime.budget_reservations WHERE agent_run_id = %s", (agent_run_id,)
        )
        connection.execute(
            """
            INSERT INTO observability.usage_ledger (
                agent_run_id, provider, model, input_tokens, output_tokens, latency_ms,
                estimated_cost_usd
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                agent_run_id,
                response.provider,
                response.model,
                response.usage.input_tokens,
                response.usage.output_tokens,
                response.latency_milliseconds,
                response.estimated_cost_usd,
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

    @staticmethod
    def _require_actor_workspace(
        connection: psycopg.Connection[Any],
        organization_id: UUID,
        actor_user_id: UUID,
        workspace_id: UUID,
    ) -> None:
        membership = connection.execute(
            """
            SELECT 1
            FROM identity.users AS actor
            JOIN workspace.memberships AS membership ON membership.user_id = actor.user_id
            JOIN workspace.workspaces AS workspace
              ON workspace.workspace_id = membership.workspace_id
            WHERE actor.organization_id = %s AND actor.user_id = %s
              AND workspace.workspace_id = %s AND workspace.organization_id = %s
              AND workspace.status = 'ACTIVE'
            """,
            (organization_id, actor_user_id, workspace_id, organization_id),
        ).fetchone()
        if membership is None:
            raise AgentRuntimeBlocked("active workspace membership is required")

    @staticmethod
    def _append_audit(
        connection: psycopg.Connection[Any],
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        reason: str,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                organization_id,
                actor_user_id,
                action,
                entity_type,
                entity_id,
                correlation_id,
                reason,
                Jsonb(metadata),
            ),
        )


def _parse_and_validate_output(value: str, schema: dict[str, Any]) -> dict[str, Any]:
    try:
        parsed = json.loads(_strip_code_fence(value))
    except json.JSONDecodeError as error:
        raise OutputSchemaError("model output was not valid JSON") from error
    if not isinstance(parsed, dict):
        raise OutputSchemaError("model output must be a JSON object")
    try:
        _validate_json_schema(parsed, schema, "output")
    except InputSchemaError as error:
        raise OutputSchemaError(str(error)) from error
    return parsed


def _validate_json_schema(value: Any, schema: dict[str, Any], path: str) -> None:
    expected_type = schema.get("type")
    if expected_type == "object":
        if not isinstance(value, dict):
            raise InputSchemaError(f"{path} must be an object")
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if isinstance(key, str) and key not in value:
                    raise InputSchemaError(f"{path}.{key} is required")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, property_schema in properties.items():
                if key in value and isinstance(property_schema, dict):
                    _validate_json_schema(value[key], property_schema, f"{path}.{key}")
    elif expected_type == "array" and not isinstance(value, list):
        raise InputSchemaError(f"{path} must be an array")
    elif expected_type == "string" and not isinstance(value, str):
        raise InputSchemaError(f"{path} must be a string")
    elif expected_type == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        raise InputSchemaError(f"{path} must be an integer")
    elif expected_type == "number" and (
        isinstance(value, bool) or not isinstance(value, (int, float))
    ):
        raise InputSchemaError(f"{path} must be a number")
    elif expected_type == "boolean" and not isinstance(value, bool):
        raise InputSchemaError(f"{path} must be a boolean")


def _read_only_fixture(fixture_input: dict[str, Any]) -> dict[str, Any]:
    return {
        "fixture": "H3_READ_ONLY_PROPERTY_SOURCE",
        "query": fixture_input.get("query", ""),
        "records": [
            {
                "reference": "FIXTURE-PROPERTY-001",
                "summary": (
                    "Synthetic read-only property opportunity fixture for runtime validation."
                ),
            }
        ],
    }


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _strip_code_fence(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        return stripped.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    return stripped


def _failure_result(prepared: _PreparedRun, error_code: str) -> AgentRunResult:
    return AgentRunResult(
        agent_run_id=prepared.agent_run_id,
        agent_key=prepared.execution.agent_key,
        semantic_version=prepared.execution.semantic_version,
        status="FAILED",
        correlation_id=prepared.correlation_id,
        tool_decisions=list(prepared.tool_decisions),
        error_code=error_code,
    )
