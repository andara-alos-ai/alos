"""Read-only, organization-scoped data for the Director executive dashboard."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime
from typing import Any, Literal
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from pydantic import BaseModel

from alos.persistence.database import psycopg_url

MetricState = Literal["LIVE", "NOT_CONNECTED"]
MetricTone = Literal["SUCCESS", "WARNING", "DANGER", "INFO"]
MetricUnit = Literal["COUNT", "PERCENT"]
DivisionHealth = Literal["HEALTHY", "ATTENTION", "NOT_CONNECTED"]
ApprovalUrgency = Literal["NORMAL", "DUE_SOON", "OVERDUE"]

_MONTH_LABELS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "Mei",
    "Jun",
    "Jul",
    "Agu",
    "Sep",
    "Okt",
    "Nov",
    "Des",
)
_DIVISION_ORDER = (
    "PROPERTY",
    "SALES_MARKETING",
    "FINANCE",
    "HR",
    "IT",
    "LEGAL",
)


class ExecutiveDashboardProfile(BaseModel):
    display_name: str
    organization_name: str
    role_label: Literal["Direktur Utama"] = "Direktur Utama"


class ExecutiveDashboardMetric(BaseModel):
    key: Literal[
        "active_projects",
        "average_progress",
        "overdue_tasks",
        "pending_approvals",
    ]
    label: str
    value: float | None
    unit: MetricUnit
    tone: MetricTone
    state: MetricState
    context: str


class ExecutivePerformancePoint(BaseModel):
    period: str
    label: str
    value: float | None
    decision_count: int


class ExecutivePerformanceSeries(BaseModel):
    title: str
    context: str
    points: list[ExecutivePerformancePoint]


class ExecutiveProjectDistributionItem(BaseModel):
    key: Literal["COMPLETED", "ON_TRACK", "AT_RISK", "CRITICAL"]
    label: str
    count: int
    tone: Literal["BLUE", "GREEN", "AMBER", "RED"]


class ExecutiveProjectDistribution(BaseModel):
    available: bool
    total: int
    context: str
    items: list[ExecutiveProjectDistributionItem]


class ExecutiveDivisionSummary(BaseModel):
    division_code: str
    division_name: str
    health: DivisionHealth
    document_count: int
    pending_approvals: int
    active_genesis_workflows: int


class ExecutiveAttentionProject(BaseModel):
    project_id: UUID
    name: str
    progress_percent: float
    status: Literal["ON_TRACK", "AT_RISK", "CRITICAL"]


class ExecutivePendingApproval(BaseModel):
    approval_id: UUID
    kind: Literal["DOCUMENT", "AGENT_RELEASE"]
    title: str
    requested_by: str
    workspace_name: str
    submitted_at: datetime
    age_days: int
    urgency: ApprovalUrgency


class ExecutiveDashboardSnapshot(BaseModel):
    generated_at: datetime
    profile: ExecutiveDashboardProfile
    metrics: list[ExecutiveDashboardMetric]
    performance: ExecutivePerformanceSeries
    project_distribution: ExecutiveProjectDistribution
    divisions: list[ExecutiveDivisionSummary]
    attention_projects: list[ExecutiveAttentionProject]
    pending_approvals: list[ExecutivePendingApproval]


class ExecutiveDashboardRepository:
    """Aggregate only persisted, access-scoped facts; never synthesize business KPIs."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def snapshot(
        self,
        *,
        organization_id: UUID,
        actor_user_id: UUID,
        workspace_ids: list[UUID],
    ) -> ExecutiveDashboardSnapshot:
        accessible_workspaces = workspace_ids or [UUID(int=0)]
        now = datetime.now(UTC)
        month_starts = _recent_month_starts(now.date(), count=7)
        with self._connection() as connection:
            identity = connection.execute(
                """
                SELECT actor.display_name, organization.name AS organization_name
                FROM identity.users AS actor
                JOIN identity.organizations AS organization
                  ON organization.organization_id = actor.organization_id
                WHERE actor.user_id = %s AND actor.organization_id = %s
                  AND actor.status = 'ACTIVE'
                """,
                (actor_user_id, organization_id),
            ).fetchone()
            if identity is None:
                raise LookupError("active dashboard identity is not available")

            approval_counts = connection.execute(
                """
                SELECT
                    (
                        SELECT count(*)
                        FROM documents.review_requests AS review
                        JOIN documents.records AS document
                          ON document.document_id = review.document_id
                        WHERE document.organization_id = %s
                          AND document.workspace_id = ANY(%s::uuid[])
                          AND review.status = 'PENDING'
                    ) AS document_pending,
                    (
                        SELECT count(*)
                        FROM governance.agent_change_requests AS agent_change
                        JOIN genesis.change_requests AS change
                          ON change.change_request_id = agent_change.change_request_id
                        WHERE change.organization_id = %s
                          AND change.workspace_id = ANY(%s::uuid[])
                          AND agent_change.state = 'IN_REVIEW'
                    ) AS agent_pending
                """,
                (
                    organization_id,
                    accessible_workspaces,
                    organization_id,
                    accessible_workspaces,
                ),
            ).fetchone()
            assert approval_counts is not None
            pending_count = int(approval_counts["document_pending"]) + int(
                approval_counts["agent_pending"]
            )

            division_rows = connection.execute(
                """
                SELECT division.code AS division_code,
                       division.name AS division_name,
                       count(DISTINCT document.document_id) AS document_count,
                       count(DISTINCT review.document_review_request_id)
                           FILTER (WHERE review.status = 'PENDING') AS pending_approvals,
                       count(DISTINCT workflow.workflow_id) AS active_genesis_workflows
                FROM identity.divisions AS division
                LEFT JOIN workspace.workspaces AS workspace
                  ON workspace.division_id = division.division_id
                 AND workspace.organization_id = division.organization_id
                 AND workspace.workspace_id = ANY(%s::uuid[])
                 AND workspace.status = 'ACTIVE'
                LEFT JOIN documents.records AS document
                  ON document.workspace_id = workspace.workspace_id
                 AND document.organization_id = division.organization_id
                 AND document.status <> 'ARCHIVED'
                LEFT JOIN documents.review_requests AS review
                  ON review.document_id = document.document_id
                LEFT JOIN genesis.document_workflows AS workflow
                  ON workflow.workspace_id = workspace.workspace_id
                 AND workflow.organization_id = division.organization_id
                WHERE division.organization_id = %s
                GROUP BY division.code, division.name
                """,
                (accessible_workspaces, organization_id),
            ).fetchall()

            trend_rows = connection.execute(
                """
                SELECT to_char(date_trunc('month', event_at), 'YYYY-MM') AS period,
                       count(*) FILTER (WHERE decision = 'APPROVED') AS approved_count,
                       count(*) AS decision_count
                FROM (
                    SELECT review.decided_at AS event_at, review.status AS decision
                    FROM documents.review_requests AS review
                    JOIN documents.records AS document
                      ON document.document_id = review.document_id
                    WHERE document.organization_id = %s
                      AND document.workspace_id = ANY(%s::uuid[])
                      AND review.decided_at IS NOT NULL
                      AND review.decided_at >= %s

                    UNION ALL

                    SELECT review.created_at AS event_at, review.decision
                    FROM governance.reviews AS review
                    JOIN genesis.change_requests AS change
                      ON change.change_request_id = review.change_request_id
                    WHERE change.organization_id = %s
                      AND change.workspace_id = ANY(%s::uuid[])
                      AND review.created_at >= %s
                ) AS decisions
                GROUP BY date_trunc('month', event_at)
                ORDER BY date_trunc('month', event_at)
                """,
                (
                    organization_id,
                    accessible_workspaces,
                    month_starts[0],
                    organization_id,
                    accessible_workspaces,
                    month_starts[0],
                ),
            ).fetchall()

            pending_rows = connection.execute(
                """
                SELECT approval_id, kind, title, requested_by, workspace_name,
                       submitted_at
                FROM (
                    SELECT review.document_review_request_id AS approval_id,
                           'DOCUMENT'::text AS kind,
                           document.title,
                           submitter.display_name AS requested_by,
                           workspace.name AS workspace_name,
                           review.submitted_at
                    FROM documents.review_requests AS review
                    JOIN documents.records AS document
                      ON document.document_id = review.document_id
                    JOIN identity.users AS submitter
                      ON submitter.user_id = review.submitted_by_user_id
                    JOIN workspace.workspaces AS workspace
                      ON workspace.workspace_id = document.workspace_id
                    WHERE document.organization_id = %s
                      AND document.workspace_id = ANY(%s::uuid[])
                      AND review.status = 'PENDING'

                    UNION ALL

                    SELECT agent_change.change_request_id AS approval_id,
                           'AGENT_RELEASE'::text AS kind,
                           agent.name AS title,
                           maker.display_name AS requested_by,
                           workspace.name AS workspace_name,
                           change.created_at AS submitted_at
                    FROM governance.agent_change_requests AS agent_change
                    JOIN genesis.change_requests AS change
                      ON change.change_request_id = agent_change.change_request_id
                    JOIN agents.contracts AS agent
                      ON agent.agent_contract_id = agent_change.agent_contract_id
                    JOIN identity.users AS maker
                      ON maker.user_id = agent_change.maker_user_id
                    JOIN workspace.workspaces AS workspace
                      ON workspace.workspace_id = change.workspace_id
                    WHERE change.organization_id = %s
                      AND change.workspace_id = ANY(%s::uuid[])
                      AND agent_change.state = 'IN_REVIEW'
                ) AS pending
                ORDER BY submitted_at, approval_id
                LIMIT 5
                """,
                (
                    organization_id,
                    accessible_workspaces,
                    organization_id,
                    accessible_workspaces,
                ),
            ).fetchall()

        return ExecutiveDashboardSnapshot(
            generated_at=now,
            profile=ExecutiveDashboardProfile(
                display_name=identity["display_name"],
                organization_name=identity["organization_name"],
            ),
            metrics=_metrics(pending_count),
            performance=_performance_series(month_starts, trend_rows),
            project_distribution=_empty_project_distribution(),
            divisions=_division_summaries(division_rows),
            attention_projects=[],
            pending_approvals=[_pending_approval(row, now.date()) for row in pending_rows],
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection


def _metrics(pending_count: int) -> list[ExecutiveDashboardMetric]:
    return [
        ExecutiveDashboardMetric(
            key="active_projects",
            label="Total Proyek Aktif",
            value=None,
            unit="COUNT",
            tone="SUCCESS",
            state="NOT_CONNECTED",
            context="Sumber proyek belum terhubung",
        ),
        ExecutiveDashboardMetric(
            key="average_progress",
            label="Progress Rata-rata",
            value=None,
            unit="PERCENT",
            tone="WARNING",
            state="NOT_CONNECTED",
            context="Milestone proyek belum terhubung",
        ),
        ExecutiveDashboardMetric(
            key="overdue_tasks",
            label="Task Overdue",
            value=None,
            unit="COUNT",
            tone="DANGER",
            state="NOT_CONNECTED",
            context="Sumber task belum terhubung",
        ),
        ExecutiveDashboardMetric(
            key="pending_approvals",
            label="Approval Pending",
            value=float(pending_count),
            unit="COUNT",
            tone="INFO",
            state="LIVE",
            context="Dokumen dan release agent yang menunggu keputusan",
        ),
    ]


def _performance_series(
    month_starts: list[date], rows: list[dict[str, Any]]
) -> ExecutivePerformanceSeries:
    by_period = {str(row["period"]): row for row in rows}
    points: list[ExecutivePerformancePoint] = []
    for month_start in month_starts:
        period = month_start.strftime("%Y-%m")
        row = by_period.get(period)
        decision_count = int(row["decision_count"]) if row else 0
        value = (
            round(int(row["approved_count"]) / decision_count * 100, 1)
            if row and decision_count
            else None
        )
        points.append(
            ExecutivePerformancePoint(
                period=period,
                label=_MONTH_LABELS[month_start.month - 1],
                value=value,
                decision_count=decision_count,
            )
        )
    return ExecutivePerformanceSeries(
        title="Rasio keputusan yang disetujui",
        context="Berdasarkan review dokumen dan release agent selama tujuh bulan terakhir.",
        points=points,
    )


def _empty_project_distribution() -> ExecutiveProjectDistribution:
    return ExecutiveProjectDistribution(
        available=False,
        total=0,
        context="Distribusi akan aktif setelah sumber proyek kanonis terhubung.",
        items=[
            ExecutiveProjectDistributionItem(
                key="COMPLETED", label="Selesai", count=0, tone="BLUE"
            ),
            ExecutiveProjectDistributionItem(
                key="ON_TRACK", label="On Track", count=0, tone="GREEN"
            ),
            ExecutiveProjectDistributionItem(
                key="AT_RISK", label="At Risk", count=0, tone="AMBER"
            ),
            ExecutiveProjectDistributionItem(
                key="CRITICAL", label="Critical", count=0, tone="RED"
            ),
        ],
    )


def _division_summaries(rows: list[dict[str, Any]]) -> list[ExecutiveDivisionSummary]:
    summaries: list[ExecutiveDivisionSummary] = []
    for row in rows:
        document_count = int(row["document_count"])
        pending_approvals = int(row["pending_approvals"])
        active_workflows = int(row["active_genesis_workflows"])
        health: DivisionHealth
        if pending_approvals:
            health = "ATTENTION"
        elif document_count or active_workflows:
            health = "HEALTHY"
        else:
            health = "NOT_CONNECTED"
        summaries.append(
            ExecutiveDivisionSummary(
                division_code=row["division_code"],
                division_name=row["division_name"],
                health=health,
                document_count=document_count,
                pending_approvals=pending_approvals,
                active_genesis_workflows=active_workflows,
            )
        )
    order = {code: index for index, code in enumerate(_DIVISION_ORDER)}
    return sorted(summaries, key=lambda item: order.get(item.division_code, len(order)))


def _pending_approval(row: dict[str, Any], today: date) -> ExecutivePendingApproval:
    submitted_at: datetime = row["submitted_at"]
    age_days = max(0, (today - submitted_at.date()).days)
    urgency: ApprovalUrgency = (
        "OVERDUE" if age_days >= 7 else "DUE_SOON" if age_days >= 3 else "NORMAL"
    )
    return ExecutivePendingApproval(
        approval_id=row["approval_id"],
        kind=row["kind"],
        title=row["title"],
        requested_by=row["requested_by"],
        workspace_name=row["workspace_name"],
        submitted_at=submitted_at,
        age_days=age_days,
        urgency=urgency,
    )


def _recent_month_starts(current: date, *, count: int) -> list[date]:
    first_of_month = date(current.year, current.month, 1)
    return [
        _shift_month(first_of_month, offset) for offset in range(1 - count, 1)
    ]


def _shift_month(value: date, offset: int) -> date:
    month_index = value.year * 12 + value.month - 1 + offset
    year, zero_based_month = divmod(month_index, 12)
    return date(year, zero_based_month + 1, 1)
