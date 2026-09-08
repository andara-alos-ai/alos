"""Scoped project, milestone, and issue write operations for the canonical portfolio."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import BaseModel, ConfigDict, Field, model_validator

from alos.authorization import AccessMode, require_business_access
from alos.identity import DivisionCode
from alos.persistence.database import psycopg_url
from alos.security.tokens import ActorContext

ProjectState = Literal["ON_TRACK", "AT_RISK", "CRITICAL", "COMPLETED", "ARCHIVED"]
ActiveProjectState = Literal["ON_TRACK", "AT_RISK", "CRITICAL", "COMPLETED"]


class ProjectOperationError(RuntimeError):
    """Safe project mutation failure."""


class ProjectNotFound(ProjectOperationError):
    pass


class ProjectConflict(ProjectOperationError):
    pass


class ProjectCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_code: DivisionCode
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{1,39}$")
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=80)
    owner_user_id: UUID | None = None
    status: ActiveProjectState = "ON_TRACK"
    progress_percent: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    start_date: date | None = None
    deadline: date | None = None
    budget_planned: Decimal | None = Field(default=None, ge=0)
    currency: str = Field(default="IDR", pattern=r"^[A-Z]{3}$")

    @model_validator(mode="after")
    def dates_are_ordered(self) -> ProjectCreateRequest:
        if self.start_date and self.deadline and self.deadline < self.start_date:
            raise ValueError("deadline must be on or after start_date")
        return self


class ProjectUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ProjectState | None = None
    progress_percent: Decimal | None = Field(default=None, ge=0, le=100)
    deadline: date | None = None
    budget_spent: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def has_change(self) -> ProjectUpdateRequest:
        if not self.model_fields_set:
            raise ValueError("at least one project field is required")
        return self


class ProjectRecord(BaseModel):
    project_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID
    division_code: DivisionCode
    code: str
    name: str
    category: str
    owner_user_id: UUID | None
    status: ProjectState
    progress_percent: Decimal
    start_date: date | None
    deadline: date | None
    budget_planned: Decimal | None
    budget_spent: Decimal | None
    currency: str
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class MilestoneCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=2, max_length=180)
    due_date: date
    status: ActiveProjectState = "ON_TRACK"


class MilestoneStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ActiveProjectState


class MilestoneRecord(BaseModel):
    milestone_id: UUID
    project_id: UUID
    title: str
    due_date: date
    status: ActiveProjectState
    completed_at: datetime | None
    created_at: datetime


class ProjectIssueCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    division_code: DivisionCode
    project_id: UUID | None = None
    title: str = Field(min_length=2, max_length=180)
    description: str = Field(default="", max_length=10_000)
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    owner_user_id: UUID | None = None
    due_date: date | None = None


class ProjectIssueStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"]


class ProjectIssueRecord(BaseModel):
    issue_id: UUID
    organization_id: UUID
    workspace_id: UUID
    division_id: UUID
    division_code: DivisionCode
    project_id: UUID | None
    title: str
    description: str
    severity: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"]
    owner_user_id: UUID | None
    due_date: date | None
    created_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class ProjectOperationsRepository:
    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def create_project(
        self, actor: ActorContext, request: ProjectCreateRequest, correlation_id: UUID
    ) -> ProjectRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.CREATE_DRAFT,
            workspace_id=request.workspace_id,
            division_code=request.division_code,
        )
        with self._transaction() as connection:
            division_id = self._division_for_workspace(
                connection, actor, request.workspace_id, request.division_code
            )
            owner = request.owner_user_id or actor.user_id
            self._require_user(connection, actor.organization_id, owner)
            try:
                row = connection.execute(
                    """
                    INSERT INTO portfolio.projects (
                        organization_id, workspace_id, division_id, code, name, category,
                        owner_user_id, status, progress_percent, start_date, deadline,
                        budget_planned, currency, created_by_user_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING project_id, organization_id, workspace_id, division_id, code,
                              name, category, owner_user_id, status, progress_percent,
                              start_date, deadline, budget_planned, budget_spent, currency,
                              created_by_user_id, created_at, updated_at
                    """,
                    (
                        actor.organization_id,
                        request.workspace_id,
                        division_id,
                        request.code,
                        request.name,
                        request.category,
                        owner,
                        request.status,
                        request.progress_percent,
                        request.start_date,
                        request.deadline,
                        request.budget_planned,
                        request.currency,
                        actor.user_id,
                    ),
                ).fetchone()
            except psycopg.errors.UniqueViolation as error:
                raise ProjectConflict("project code already exists") from error
            if row is None:
                raise ProjectOperationError("project could not be created")
            row["division_code"] = request.division_code
            self._audit(connection, actor, "PROJECT_CREATED", row["project_id"], correlation_id)
            return ProjectRecord(**row)

    def update_project(
        self,
        actor: ActorContext,
        project_id: UUID,
        request: ProjectUpdateRequest,
        correlation_id: UUID,
    ) -> ProjectRecord:
        with self._transaction() as connection:
            current = self._project(connection, actor, project_id, lock=True)
            require_business_access(
                actor,
                access_mode=AccessMode.UPDATE_SCOPED,
                workspace_id=current["workspace_id"],
                division_code=current["division_code"],
                owner_user_id=current["owner_user_id"],
            )
            changes = request.model_dump(exclude_unset=True)
            assignments = [f"{field} = %s" for field in changes]
            values = list(changes.values())
            assignments.append("updated_at = now()")
            row = connection.execute(
                f"""
                UPDATE portfolio.projects SET {", ".join(assignments)}
                WHERE project_id = %s
                RETURNING project_id, organization_id, workspace_id, division_id, code,
                          name, category, owner_user_id, status, progress_percent,
                          start_date, deadline, budget_planned, budget_spent, currency,
                          created_by_user_id, created_at, updated_at
                """,
                (*values, project_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFound("project was not found")
            row["division_code"] = current["division_code"]
            if request.progress_percent is not None or request.status is not None:
                connection.execute(
                    """
                    INSERT INTO portfolio.project_progress_history (
                        project_id, recorded_on, progress_percent, status, recorded_by_user_id
                    ) VALUES (%s, current_date, %s, %s, %s)
                    ON CONFLICT (project_id, recorded_on) DO UPDATE SET
                        progress_percent = EXCLUDED.progress_percent,
                        status = EXCLUDED.status,
                        recorded_by_user_id = EXCLUDED.recorded_by_user_id
                    """,
                    (project_id, row["progress_percent"], row["status"], actor.user_id),
                )
            self._audit(connection, actor, "PROJECT_UPDATED", project_id, correlation_id)
            return ProjectRecord(**row)

    def delete_project(
        self, actor: ActorContext, project_id: UUID, correlation_id: UUID
    ) -> None:
        with self._transaction() as connection:
            current = self._project(connection, actor, project_id, lock=True)
            require_business_access(
                actor,
                access_mode=AccessMode.UPDATE_SCOPED,
                workspace_id=current["workspace_id"],
                division_code=current["division_code"],
                owner_user_id=current["owner_user_id"],
            )
            dependencies = connection.execute(
                """
                SELECT
                    (SELECT count(*) FROM portfolio.project_milestones
                     WHERE project_id = %s) AS milestones,
                    (SELECT count(*) FROM portfolio.division_issues
                     WHERE project_id = %s) AS issues,
                    (SELECT count(*) FROM operational.tasks
                     WHERE project_id = %s) AS tasks,
                    (SELECT count(*) FROM operational.evidence
                     WHERE project_id = %s) AS evidence,
                    (SELECT count(*) FROM operational.findings
                     WHERE project_id = %s) AS findings,
                    (SELECT count(*) FROM operational.proposed_actions
                     WHERE project_id = %s) AS proposed_actions,
                    (SELECT count(*) FROM operational.approval_requests
                     WHERE project_id = %s) AS approvals,
                    (SELECT count(*) FROM reporting.definitions
                     WHERE project_id = %s) AS report_definitions,
                    (SELECT count(*) FROM business.records
                     WHERE project_id = %s) AS business_records
                """,
                (project_id,) * 9,
            ).fetchone()
            if dependencies is None:
                raise ProjectNotFound("project was not found")
            blocked = [name for name, count in dependencies.items() if count]
            if blocked:
                raise ProjectConflict(
                    "project has dependent records; remove these first: "
                    + ", ".join(blocked)
                )
            connection.execute(
                "DELETE FROM portfolio.project_progress_history WHERE project_id = %s",
                (project_id,),
            )
            deleted = connection.execute(
                """
                DELETE FROM portfolio.projects
                WHERE project_id = %s AND organization_id = %s
                RETURNING project_id
                """,
                (project_id, actor.organization_id),
            ).fetchone()
            if deleted is None:
                raise ProjectNotFound("project was not found")
            self._audit(connection, actor, "PROJECT_DELETED", project_id, correlation_id)

    def create_milestone(
        self,
        actor: ActorContext,
        project_id: UUID,
        request: MilestoneCreateRequest,
        correlation_id: UUID,
    ) -> MilestoneRecord:
        with self._transaction() as connection:
            project = self._project(connection, actor, project_id)
            require_business_access(
                actor,
                access_mode=AccessMode.UPDATE_SCOPED,
                workspace_id=project["workspace_id"],
                division_code=project["division_code"],
                owner_user_id=project["owner_user_id"],
            )
            row = connection.execute(
                """
                INSERT INTO portfolio.project_milestones (project_id, title, due_date, status)
                VALUES (%s, %s, %s, %s)
                RETURNING milestone_id, project_id, title, due_date, status,
                          completed_at, created_at
                """,
                (project_id, request.title, request.due_date, request.status),
            ).fetchone()
            if row is None:
                raise ProjectOperationError("milestone could not be created")
            self._audit(
                connection,
                actor,
                "PROJECT_MILESTONE_CREATED",
                row["milestone_id"],
                correlation_id,
            )
            return MilestoneRecord(**row)

    def update_milestone(
        self,
        actor: ActorContext,
        milestone_id: UUID,
        request: MilestoneStatusRequest,
        correlation_id: UUID,
    ) -> MilestoneRecord:
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT milestone.milestone_id, milestone.project_id, milestone.title,
                       milestone.due_date, milestone.status, milestone.completed_at,
                       milestone.created_at, project.organization_id, project.workspace_id,
                       project.owner_user_id, division.code AS division_code
                FROM portfolio.project_milestones AS milestone
                JOIN portfolio.projects AS project ON project.project_id = milestone.project_id
                JOIN identity.divisions AS division ON division.division_id = project.division_id
                WHERE milestone.milestone_id = %s AND project.organization_id = %s
                  AND project.workspace_id = ANY(%s)
                FOR UPDATE OF milestone
                """,
                (milestone_id, actor.organization_id, actor.workspace_ids),
            ).fetchone()
            if row is None:
                raise ProjectNotFound("milestone was not found")
            require_business_access(
                actor,
                access_mode=AccessMode.UPDATE_SCOPED,
                workspace_id=row["workspace_id"],
                division_code=row["division_code"],
                owner_user_id=row["owner_user_id"],
            )
            updated = connection.execute(
                """
                UPDATE portfolio.project_milestones
                SET status = %s,
                    completed_at = CASE WHEN %s = 'COMPLETED' THEN coalesce(completed_at, now())
                                        ELSE NULL END
                WHERE milestone_id = %s
                RETURNING milestone_id, project_id, title, due_date, status,
                          completed_at, created_at
                """,
                (request.status, request.status, milestone_id),
            ).fetchone()
            if updated is None:
                raise ProjectNotFound("milestone was not found")
            self._audit(
                connection,
                actor,
                "PROJECT_MILESTONE_UPDATED",
                milestone_id,
                correlation_id,
            )
            return MilestoneRecord(**updated)

    def create_issue(
        self, actor: ActorContext, request: ProjectIssueCreateRequest, correlation_id: UUID
    ) -> ProjectIssueRecord:
        require_business_access(
            actor,
            access_mode=AccessMode.CREATE_DRAFT,
            workspace_id=request.workspace_id,
            division_code=request.division_code,
        )
        with self._transaction() as connection:
            division_id = self._division_for_workspace(
                connection, actor, request.workspace_id, request.division_code
            )
            if request.project_id:
                project = self._project(connection, actor, request.project_id)
                if (
                    project["workspace_id"] != request.workspace_id
                    or project["division_id"] != division_id
                ):
                    raise ProjectConflict(
                        "project does not belong to the requested division workspace"
                    )
            owner = request.owner_user_id
            if owner:
                self._require_user(connection, actor.organization_id, owner)
            row = connection.execute(
                """
                INSERT INTO portfolio.division_issues (
                    organization_id, workspace_id, division_id, project_id, title,
                    description, severity, owner_user_id, due_date, created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING issue_id, organization_id, workspace_id, division_id, project_id,
                          title, description, severity, status, owner_user_id, due_date,
                          created_by_user_id, created_at, updated_at
                """,
                (
                    actor.organization_id,
                    request.workspace_id,
                    division_id,
                    request.project_id,
                    request.title,
                    request.description,
                    request.severity,
                    owner,
                    request.due_date,
                    actor.user_id,
                ),
            ).fetchone()
            if row is None:
                raise ProjectOperationError("project issue could not be created")
            row["division_code"] = request.division_code
            self._audit(connection, actor, "PROJECT_ISSUE_CREATED", row["issue_id"], correlation_id)
            return ProjectIssueRecord(**row)

    def update_issue(
        self,
        actor: ActorContext,
        issue_id: UUID,
        request: ProjectIssueStatusRequest,
        correlation_id: UUID,
    ) -> ProjectIssueRecord:
        with self._transaction() as connection:
            current = connection.execute(
                """
                SELECT issue.*, division.code AS division_code
                FROM portfolio.division_issues AS issue
                JOIN identity.divisions AS division ON division.division_id = issue.division_id
                WHERE issue.issue_id = %s AND issue.organization_id = %s
                  AND issue.workspace_id = ANY(%s)
                FOR UPDATE OF issue
                """,
                (issue_id, actor.organization_id, actor.workspace_ids),
            ).fetchone()
            if current is None:
                raise ProjectNotFound("project issue was not found")
            require_business_access(
                actor,
                access_mode=AccessMode.UPDATE_SCOPED,
                workspace_id=current["workspace_id"],
                division_code=current["division_code"],
                owner_user_id=current["owner_user_id"],
            )
            row = connection.execute(
                """
                UPDATE portfolio.division_issues SET status = %s, updated_at = now()
                WHERE issue_id = %s
                RETURNING issue_id, organization_id, workspace_id, division_id, project_id,
                          title, description, severity, status, owner_user_id, due_date,
                          created_by_user_id, created_at, updated_at
                """,
                (request.status, issue_id),
            ).fetchone()
            if row is None:
                raise ProjectNotFound("project issue was not found")
            row["division_code"] = current["division_code"]
            self._audit(connection, actor, "PROJECT_ISSUE_UPDATED", issue_id, correlation_id)
            return ProjectIssueRecord(**row)

    def _project(
        self,
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        project_id: UUID,
        *,
        lock: bool = False,
    ) -> dict[str, Any]:
        suffix = " FOR UPDATE OF project" if lock else ""
        row = connection.execute(
            """
            SELECT project.*, division.code AS division_code
            FROM portfolio.projects AS project
            JOIN identity.divisions AS division ON division.division_id = project.division_id
            WHERE project.project_id = %s AND project.organization_id = %s
              AND project.workspace_id = ANY(%s)
            """ + suffix,
            (project_id, actor.organization_id, actor.workspace_ids),
        ).fetchone()
        if row is None:
            raise ProjectNotFound("project was not found")
        return cast(dict[str, Any], row)

    @staticmethod
    def _division_for_workspace(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        workspace_id: UUID,
        code: DivisionCode,
    ) -> UUID:
        row = connection.execute(
            """
            SELECT division.division_id
            FROM workspace.workspaces AS workspace
            JOIN identity.divisions AS division ON division.division_id = workspace.division_id
            WHERE workspace.workspace_id = %s AND workspace.organization_id = %s
              AND division.code = %s
            """,
            (workspace_id, actor.organization_id, code.value),
        ).fetchone()
        if row is None:
            raise ProjectNotFound("division workspace was not found")
        return UUID(str(row["division_id"]))

    @staticmethod
    def _require_user(
        connection: psycopg.Connection[Any], organization_id: UUID, user_id: UUID
    ) -> None:
        if connection.execute(
            """
            SELECT 1 FROM identity.users
            WHERE organization_id = %s AND user_id = %s AND status = 'ACTIVE'
            """,
            (organization_id, user_id),
        ).fetchone() is None:
            raise ProjectNotFound("project owner was not found")

    @staticmethod
    def _audit(
        connection: psycopg.Connection[Any],
        actor: ActorContext,
        action: str,
        entity_id: UUID,
        correlation_id: UUID,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit.events (
                organization_id, actor_kind, actor_user_id, action,
                entity_type, entity_id, correlation_id, reason, details
            ) VALUES (%s, 'HUMAN', %s, %s, 'PROJECT_OPERATION', %s, %s, %s, %s)
            """,
            (
                actor.organization_id,
                actor.user_id,
                action,
                entity_id,
                correlation_id,
                "Authorized project operation",
                Jsonb({}),
            ),
        )

    @contextmanager
    def _transaction(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
