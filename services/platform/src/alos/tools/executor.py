"""Server-side typed ToolExecutor used by GENESIS and the shared Agent Runtime."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field

from alos.capabilities import CapabilityRegistryRepository, TypedToolRecord
from alos.documents.intelligence import (
    DocumentComparisonRequest,
    DocumentIntelligenceRepository,
)
from alos.identity import DivisionCode
from alos.operational.models import (
    ApprovalCreateRequest,
    FindingCreateRequest,
    ReportGenerateRequest,
    TaskCreateRequest,
    TaskStatusRequest,
)
from alos.operational.repository import OperationalRepository
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext


class ToolExecutionError(RuntimeError):
    """Safe tool failure without database or credential details."""


class ToolExecutionDenied(ToolExecutionError):
    pass


class StructuredToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_key: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=200)


class ToolExecutionResult(BaseModel):
    tool_key: str
    capability_key: str
    correlation_id: UUID
    status: str
    output: Any
    elapsed_milliseconds: int


class ToolExecutor:
    """Resolve metadata, validate permission/scope, execute a fixed handler, and audit."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)
        self._catalog = CapabilityRegistryRepository(database_url)
        self._operations = OperationalRepository(database_url)
        self._documents = DocumentIntelligenceRepository(database_url)
        self._handlers: dict[str, Callable[[ActorContext, dict[str, Any], UUID], Any]] = {
            "ORGANIZATION_CONTEXT_READ": self._organization_context,
            "DIVISION_CONTEXT_READ": self._division_context,
            "PROJECT_LIST": self._project_list,
            "PROJECT_READ": self._project_read,
            "TASK_LIST": self._task_list,
            "TASK_READ": self._task_read,
            "TASK_CREATE_DRAFT": self._task_create_draft,
            "TASK_UPDATE_STATUS": self._task_update_status,
            "EVIDENCE_READ": self._evidence_read,
            "FINDING_LIST": self._finding_list,
            "APPROVAL_LIST": self._approval_list,
            "DOCUMENT_SEARCH": self._document_search,
            "DOCUMENT_READ": self._document_read,
            "DOCUMENT_COMPARE": self._document_compare,
            "FINDING_CREATE": self._finding_create,
            "APPROVAL_REQUEST": self._approval_request,
            "REPORT_LIST": self._report_list,
            "REPORT_GENERATE": self._report_generate,
            "GLOBAL_SEARCH": self._global_search,
        }

    def execute(
        self,
        call: StructuredToolCall,
        *,
        actor: ActorContext,
        correlation_id: UUID | None = None,
        agent_version_id: UUID | None = None,
        agent_run_id: UUID | None = None,
    ) -> ToolExecutionResult:
        correlation = correlation_id or uuid4()
        specification = self._catalog.get_tool(call.tool_key)
        if specification is None or specification.lifecycle_status != "APPROVED":
            self._record_denied(
                call.tool_key, actor, correlation, agent_run_id, "TOOL_NOT_APPROVED"
            )
            raise ToolExecutionDenied("tool is not approved or registered")
        _validate_schema(specification.input_schema, call.arguments)
        if specification.idempotency_policy == "REQUIRED" and not call.idempotency_key:
            self._record_denied(
                call.tool_key, actor, correlation, agent_run_id, "IDEMPOTENCY_REQUIRED"
            )
            raise ToolExecutionDenied("tool requires an idempotency key")
        if agent_version_id is not None:
            self._require_agent_permission(agent_version_id, specification)
        handler = self._handlers.get(specification.runtime_handler)
        if handler is None:
            self._record_denied(
                call.tool_key, actor, correlation, agent_run_id, "HANDLER_UNAVAILABLE"
            )
            raise ToolExecutionDenied("tool handler is unavailable")
        arguments = dict(call.arguments)
        if call.idempotency_key:
            arguments.setdefault("idempotency_key", call.idempotency_key)
        started = time.monotonic()
        try:
            output = handler(actor, arguments, correlation)
        except ToolExecutionError:
            raise
        except Exception as error:
            self._record_denied(
                call.tool_key, actor, correlation, agent_run_id, "SAFE_TOOL_FAILURE"
            )
            raise ToolExecutionError("tool execution failed safely") from error
        elapsed = int((time.monotonic() - started) * 1000)
        self._record_allowed(
            specification,
            actor,
            correlation,
            agent_run_id,
            elapsed_milliseconds=elapsed,
        )
        return ToolExecutionResult(
            tool_key=call.tool_key,
            capability_key=specification.capability_key,
            correlation_id=correlation,
            status="SUCCEEDED",
            output=output,
            elapsed_milliseconds=elapsed,
        )

    def _require_agent_permission(
        self, agent_version_id: UUID, specification: TypedToolRecord
    ) -> None:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT effect, access_mode
                FROM governance.permission_policies
                WHERE agent_version_id = %s AND lifecycle_status = 'APPROVED'
                  AND (tool_key = %s OR capability_key = %s)
                ORDER BY CASE effect WHEN 'DENY' THEN 0 ELSE 1 END
                """,
                (agent_version_id, specification.tool_key, specification.capability_key),
            ).fetchall()
        if any(row["effect"] == "DENY" for row in rows):
            raise ToolExecutionDenied("an approved policy explicitly denies this tool")
        if not any(
            row["effect"] == "ALLOW" and row["access_mode"] == specification.access_mode
            for row in rows
        ):
            raise ToolExecutionDenied("Agent Version lacks an approved matching permission")

    def _organization_context(
        self, actor: ActorContext, _: dict[str, Any], __: UUID
    ) -> dict[str, Any]:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT organization_id, code, name, created_at
                FROM identity.organizations WHERE organization_id = %s
                """,
                (actor.organization_id,),
            ).fetchone()
        if row is None:
            raise ToolExecutionDenied("organization is outside the actor scope")
        return dict(row)

    def _division_context(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> dict[str, Any]:
        division_code = DivisionCode(str(arguments["division_code"]))
        from alos.authorization import require_division

        require_division(actor, division_code)
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT division.division_id, division.code, division.name, division.created_at,
                       count(DISTINCT project.project_id) AS project_count,
                       count(DISTINCT task.task_id) AS task_count
                FROM identity.divisions AS division
                LEFT JOIN portfolio.projects AS project
                  ON project.division_id = division.division_id
                LEFT JOIN operational.tasks AS task ON task.division_id = division.division_id
                WHERE division.organization_id = %s AND division.code = %s
                GROUP BY division.division_id
                """,
                (actor.organization_id, division_code.value),
            ).fetchone()
        if row is None:
            raise ToolExecutionDenied("division is outside the actor scope")
        return dict(row)

    def _project_list(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> list[dict[str, Any]]:
        division_code = arguments.get("division_code")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT project.project_id, project.code, project.name, project.status,
                       project.progress_percent, project.deadline, division.code AS division_code,
                       count(task.task_id) FILTER (
                           WHERE task.status NOT IN ('DONE', 'CANCELLED')
                             AND task.due_date < current_date
                       ) AS overdue_tasks
                FROM portfolio.projects AS project
                JOIN identity.divisions AS division ON division.division_id = project.division_id
                LEFT JOIN operational.tasks AS task ON task.project_id = project.project_id
                WHERE project.organization_id = %s AND project.workspace_id = ANY(%s)
                  AND (%s IS NULL OR division.code = %s)
                  AND (%s OR division.code = ANY(%s))
                GROUP BY project.project_id, division.code
                ORDER BY project.updated_at DESC
                LIMIT 100
                """,
                (
                    actor.organization_id,
                    actor.workspace_ids,
                    division_code,
                    division_code,
                    _company_scope(actor),
                    [code.value for code in actor.division_codes],
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def _project_read(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> dict[str, Any]:
        project_id = UUID(str(arguments["project_id"]))
        rows = self._project_list(actor, {}, uuid4())
        result = next((row for row in rows if row["project_id"] == project_id), None)
        if result is None:
            raise ToolExecutionDenied("project is outside the actor scope")
        return result

    def _task_list(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> dict[str, Any]:
        result = self._operations.list_tasks(
            actor,
            status=str(arguments["status"]) if arguments.get("status") else None,
            project_id=UUID(str(arguments["project_id"])) if arguments.get("project_id") else None,
            search=str(arguments["search"]) if arguments.get("search") else None,
            page_size=min(int(arguments.get("limit", 50)), 100),
        )
        return result.model_dump(mode="json")

    def _task_read(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> dict[str, Any]:
        return self._operations.get_task(
            actor, UUID(str(arguments["task_id"]))
        ).model_dump(mode="json")

    def _task_create_draft(
        self, actor: ActorContext, arguments: dict[str, Any], correlation: UUID
    ) -> dict[str, Any]:
        request = TaskCreateRequest.model_validate(arguments)
        return self._operations.create_task(
            actor, request, correlation_id=correlation, force_draft=True
        ).model_dump(mode="json")

    def _task_update_status(
        self, actor: ActorContext, arguments: dict[str, Any], correlation: UUID
    ) -> dict[str, Any]:
        task_id = UUID(str(arguments["task_id"]))
        request = TaskStatusRequest(status=arguments["status"])
        return self._operations.update_task_status(
            actor, task_id, request, correlation_id=correlation
        ).model_dump(mode="json")

    def _evidence_read(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> list[dict[str, Any]]:
        records = self._operations.list_evidence(
            actor,
            task_id=UUID(str(arguments["task_id"])) if arguments.get("task_id") else None,
            project_id=UUID(str(arguments["project_id"])) if arguments.get("project_id") else None,
        )
        if arguments.get("evidence_id"):
            evidence_id = UUID(str(arguments["evidence_id"]))
            records = [record for record in records if record.evidence_id == evidence_id]
        return [record.model_dump(mode="json") for record in records]

    def _finding_list(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> list[dict[str, Any]]:
        records = self._operations.list_findings(
            actor, status=str(arguments["status"]) if arguments.get("status") else None
        )
        if arguments.get("finding_id"):
            finding_id = UUID(str(arguments["finding_id"]))
            records = [record for record in records if record.finding_id == finding_id]
        return [record.model_dump(mode="json") for record in records]

    def _approval_list(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> list[dict[str, Any]]:
        records = self._operations.list_approvals(
            actor, status=str(arguments["status"]) if arguments.get("status") else None
        )
        if arguments.get("approval_request_id"):
            approval_id = UUID(str(arguments["approval_request_id"]))
            records = [
                record for record in records if record.approval_request_id == approval_id
            ]
        return [record.model_dump(mode="json") for record in records]

    def _document_search(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> list[dict[str, Any]]:
        term = f"%{str(arguments['query']).strip()}%"
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT document.document_id, document.title, document.category,
                       document.classification, document.status, division.code AS division_code,
                       version.version_number, version.content_sha256,
                       left(version.content, 500) AS excerpt
                FROM documents.records AS document
                JOIN LATERAL (
                    SELECT version_number, content_sha256, content
                    FROM documents.versions
                    WHERE document_id = document.document_id
                    ORDER BY version_number DESC LIMIT 1
                ) AS version ON true
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = document.division_id
                WHERE document.organization_id = %s AND document.workspace_id = ANY(%s)
                  AND (document.title ILIKE %s OR version.content ILIKE %s)
                  AND (%s OR division.code IS NULL OR division.code = ANY(%s))
                ORDER BY document.updated_at DESC LIMIT 50
                """,
                (
                    actor.organization_id,
                    actor.workspace_ids,
                    term,
                    term,
                    _company_scope(actor),
                    [code.value for code in actor.division_codes],
                ),
            ).fetchall()
        return [dict(row) for row in rows]

    def _document_read(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> dict[str, Any]:
        document_id = UUID(str(arguments["document_id"]))
        version_number = arguments.get("version_number")
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT document.document_id, document.title, document.category,
                       document.classification, document.status, division.code AS division_code,
                       version.version_number, version.content_sha256, version.content
                FROM documents.records AS document
                JOIN documents.versions AS version ON version.document_id = document.document_id
                LEFT JOIN identity.divisions AS division
                  ON division.division_id = document.division_id
                WHERE document.document_id = %s AND document.organization_id = %s
                  AND document.workspace_id = ANY(%s)
                  AND (%s IS NULL OR version.version_number = %s)
                  AND (%s OR division.code IS NULL OR division.code = ANY(%s))
                ORDER BY version.version_number DESC LIMIT 1
                """,
                (
                    document_id,
                    actor.organization_id,
                    actor.workspace_ids,
                    version_number,
                    version_number,
                    _company_scope(actor),
                    [code.value for code in actor.division_codes],
                ),
            ).fetchone()
        if row is None:
            raise ToolExecutionDenied("document is outside the actor scope")
        return dict(row)

    def _document_compare(
        self, actor: ActorContext, arguments: dict[str, Any], correlation: UUID
    ) -> dict[str, Any]:
        request = DocumentComparisonRequest.model_validate(arguments)
        return self._documents.compare(
            actor, request, correlation_id=correlation
        ).model_dump(mode="json")

    def _finding_create(
        self, actor: ActorContext, arguments: dict[str, Any], correlation: UUID
    ) -> dict[str, Any]:
        request = FindingCreateRequest.model_validate(arguments)
        return self._operations.create_finding(
            actor, request, correlation_id=correlation, generated_by="GENESIS"
        ).model_dump(mode="json")

    def _approval_request(
        self, actor: ActorContext, arguments: dict[str, Any], correlation: UUID
    ) -> dict[str, Any]:
        request = ApprovalCreateRequest.model_validate(arguments)
        return self._operations.create_approval(
            actor, request, correlation_id=correlation
        ).model_dump(mode="json")

    def _report_generate(
        self, actor: ActorContext, arguments: dict[str, Any], correlation: UUID
    ) -> dict[str, Any]:
        definition_id = UUID(str(arguments["report_definition_id"]))
        request = ReportGenerateRequest.model_validate(
            {"idempotency_key": arguments.get("idempotency_key")}
        )
        return self._operations.generate_report(
            actor, definition_id, request, correlation_id=correlation
        ).model_dump(mode="json")

    def _report_list(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> list[dict[str, Any]]:
        records = self._operations.list_reports(actor)
        if arguments.get("report_id"):
            report_id = UUID(str(arguments["report_id"]))
            records = [record for record in records if record.report_id == report_id]
        return [record.model_dump(mode="json") for record in records]

    def _global_search(
        self, actor: ActorContext, arguments: dict[str, Any], _: UUID
    ) -> list[dict[str, Any]]:
        return [
            result.model_dump(mode="json")
            for result in self._operations.global_search(
                actor, str(arguments["query"]), limit=min(int(arguments.get("limit", 20)), 50)
            )
        ]

    def _record_allowed(
        self,
        specification: TypedToolRecord,
        actor: ActorContext,
        correlation_id: UUID,
        agent_run_id: UUID | None,
        *,
        elapsed_milliseconds: int,
    ) -> None:
        with self._transaction() as connection:
            if agent_run_id:
                connection.execute(
                    """
                    INSERT INTO runtime.tool_calls (agent_run_id, tool_key, decision, reason)
                    VALUES (%s, %s, 'ALLOWED', %s)
                    """,
                    (agent_run_id, specification.tool_key, "approved typed tool execution"),
                )
            self._audit_tool(
                connection,
                actor,
                specification.tool_key,
                correlation_id,
                "ALLOWED",
                {"elapsed_milliseconds": elapsed_milliseconds},
            )

    def _record_denied(
        self,
        tool_key: str,
        actor: ActorContext,
        correlation_id: UUID,
        agent_run_id: UUID | None,
        reason: str,
    ) -> None:
        with self._transaction() as connection:
            if agent_run_id:
                connection.execute(
                    """
                    INSERT INTO runtime.tool_calls (agent_run_id, tool_key, decision, reason)
                    VALUES (%s, %s, 'DENIED', %s)
                    """,
                    (agent_run_id, tool_key, reason),
                )
            self._audit_tool(
                connection,
                actor,
                tool_key,
                correlation_id,
                "DENIED",
                {"reason": reason},
            )

    @staticmethod
    def _audit_tool(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        tool_key: str,
        correlation_id: UUID,
        decision: str,
        metadata: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action, entity_type,
                entity_id, correlation_id, reason, metadata
            ) VALUES (%s, 'HUMAN', %s, %s, 'TOOL_CALL', %s, %s, %s, %s)
            """,
            (
                actor.organization_id,
                actor.user_id,
                f"TOOL_CALL_{decision}",
                uuid4(),
                correlation_id,
                "Server-side typed tool authorization decision",
                Jsonb({"tool_key": tool_key, **metadata}),
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


def _validate_schema(schema: dict[str, Any], value: dict[str, Any]) -> None:
    required = schema.get("required", [])
    if not isinstance(required, list) or any(not isinstance(key, str) for key in required):
        raise ToolExecutionDenied("tool input schema is invalid")
    missing = [key for key in required if key not in value]
    if missing:
        raise ToolExecutionDenied(f"tool input is missing required fields: {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            raise ToolExecutionDenied("tool input schema properties are invalid")
        unknown = sorted(set(value).difference(properties))
        if unknown:
            raise ToolExecutionDenied(f"tool input has unknown fields: {', '.join(unknown)}")


def _company_scope(actor: ActorContext) -> bool:
    from alos.authorization import effective_data_scope
    from alos.identity import DataScope

    return effective_data_scope(actor) == DataScope.COMPANY
