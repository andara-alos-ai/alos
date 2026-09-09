"""Access-scoped read models for the Divisions and Projects dashboards."""

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

ProjectStatus = Literal["ON_TRACK", "AT_RISK", "CRITICAL", "COMPLETED"]
DivisionHealth = Literal["HEALTHY", "ATTENTION", "CRITICAL", "NOT_CONNECTED"]
IssueSeverity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
IssueStatus = Literal["OPEN", "IN_PROGRESS", "RESOLVED"]

_MONTH_LABELS = ("Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des")
_DIVISION_ORDER = ("PROPERTY", "SALES_MARKETING", "FINANCE", "HR", "IT", "LEGAL")


class PortfolioTrendPoint(BaseModel):
    period: str
    label: str
    value: float | None


class DivisionOverviewCard(BaseModel):
    division_id: UUID
    division_code: str
    division_name: str
    health: DivisionHealth
    active_projects: int
    average_progress: float | None
    overdue_tasks: int
    pending_approvals: int
    open_issues: int
    critical_projects: int
    at_risk_projects: int
    trend: list[PortfolioTrendPoint]


class DivisionIssueRecord(BaseModel):
    issue_id: UUID
    division_code: str
    division_name: str
    title: str
    severity: IssueSeverity
    owner_name: str | None
    status: IssueStatus
    due_date: date | None


class DivisionAttentionRecord(BaseModel):
    division_id: UUID
    division_code: str
    division_name: str
    health: Literal["ATTENTION", "CRITICAL"]
    summary: str
    trend: list[PortfolioTrendPoint]


class DivisionsOverviewSnapshot(BaseModel):
    generated_at: datetime
    divisions: list[DivisionOverviewCard]
    comparison: list[DivisionOverviewCard]
    issues: list[DivisionIssueRecord]
    attention: list[DivisionAttentionRecord]


class ProjectPortfolioMetrics(BaseModel):
    total: int
    on_track: int
    at_risk: int
    critical: int
    completed: int


class ProjectDistributionItem(BaseModel):
    status: ProjectStatus
    label: str
    count: int


class ProjectPortfolioRecord(BaseModel):
    project_id: UUID
    workspace_id: UUID
    code: str
    name: str
    division_code: str
    division_name: str
    workspace_name: str
    category: str
    owner_name: str | None
    progress_percent: float
    deadline: date | None
    status: ProjectStatus
    budget_planned: float | None
    budget_spent: float | None
    currency: str
    overdue_tasks: int


class ProjectMilestoneRecord(BaseModel):
    milestone_id: UUID
    project_id: UUID
    project_name: str
    title: str
    due_date: date
    status: ProjectStatus


class ProjectRiskSummary(BaseModel):
    status: Literal["ON_TRACK", "AT_RISK", "CRITICAL"]
    count: int
    description: str


class ProjectFilterOptions(BaseModel):
    divisions: list[str]
    categories: list[str]
    statuses: list[ProjectStatus]


class ProjectPagination(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class ProjectPortfolioSnapshot(BaseModel):
    generated_at: datetime
    metrics: ProjectPortfolioMetrics
    progress: list[PortfolioTrendPoint]
    distribution: list[ProjectDistributionItem]
    projects: list[ProjectPortfolioRecord]
    milestones: list[ProjectMilestoneRecord]
    risk_summary: list[ProjectRiskSummary]
    filter_options: ProjectFilterOptions
    pagination: ProjectPagination


class PortfolioRepository:
    """Read portfolio facts only from workspaces visible in the signed actor context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = psycopg_url(database_url)

    def divisions_overview(
        self, *, organization_id: UUID, workspace_ids: list[UUID]
    ) -> DivisionsOverviewSnapshot:
        accessible = workspace_ids or [UUID(int=0)]
        now = datetime.now(UTC)
        months = _recent_month_starts(now.date(), 7)
        with self._connection() as connection:
            rows = connection.execute(
                """
                WITH accessible_workspaces AS (
                    SELECT workspace_id, division_id
                    FROM workspace.workspaces
                    WHERE organization_id = %s
                      AND workspace_id = ANY(%s::uuid[])
                      AND status = 'ACTIVE'
                ),
                project_stats AS (
                    SELECT project.division_id,
                           count(*) AS project_count,
                           count(*) FILTER (WHERE project.status <> 'COMPLETED') AS active_projects,
                           avg(project.progress_percent)
                               FILTER (WHERE project.status <> 'COMPLETED') AS average_progress,
                           count(*) FILTER (WHERE project.status = 'CRITICAL') AS critical_projects,
                           count(*) FILTER (WHERE project.status = 'AT_RISK') AS at_risk_projects
                    FROM portfolio.projects AS project
                    JOIN accessible_workspaces AS workspace
                      ON workspace.workspace_id = project.workspace_id
                    WHERE project.organization_id = %s AND project.status <> 'ARCHIVED'
                    GROUP BY project.division_id
                ),
                task_stats AS (
                    SELECT task.division_id, count(*) AS overdue_tasks
                    FROM operational.tasks AS task
                    JOIN accessible_workspaces AS workspace
                      ON workspace.workspace_id = task.workspace_id
                    WHERE task.organization_id = %s
                      AND task.due_date < current_date
                      AND task.status NOT IN ('DONE', 'CANCELLED')
                    GROUP BY task.division_id
                ),
                issue_stats AS (
                    SELECT issue.division_id,
                           count(*) FILTER (WHERE issue.status <> 'RESOLVED') AS open_issues,
                           count(*) FILTER (
                               WHERE issue.status <> 'RESOLVED' AND issue.severity = 'CRITICAL'
                           ) AS critical_issues,
                           count(*) FILTER (
                               WHERE issue.status <> 'RESOLVED' AND issue.severity = 'HIGH'
                           ) AS high_issues
                    FROM portfolio.division_issues AS issue
                    JOIN accessible_workspaces AS workspace
                      ON workspace.workspace_id = issue.workspace_id
                    WHERE issue.organization_id = %s
                    GROUP BY issue.division_id
                ),
                approval_stats AS (
                    SELECT document.division_id,
                           count(DISTINCT review.document_review_request_id)
                               FILTER (WHERE review.status = 'PENDING') AS pending_approvals,
                           count(DISTINCT document.document_id) AS document_count
                    FROM documents.records AS document
                    JOIN accessible_workspaces AS workspace
                      ON workspace.workspace_id = document.workspace_id
                    LEFT JOIN documents.review_requests AS review
                      ON review.document_id = document.document_id
                    WHERE document.organization_id = %s AND document.status <> 'ARCHIVED'
                    GROUP BY document.division_id
                )
                SELECT division.division_id, division.code AS division_code,
                       division.name AS division_name,
                       coalesce(project.project_count, 0) AS project_count,
                       coalesce(project.active_projects, 0) AS active_projects,
                       project.average_progress,
                       coalesce(task.overdue_tasks, 0) AS overdue_tasks,
                       coalesce(project.critical_projects, 0) AS critical_projects,
                       coalesce(project.at_risk_projects, 0) AS at_risk_projects,
                       coalesce(issue.open_issues, 0) AS open_issues,
                       coalesce(issue.critical_issues, 0) AS critical_issues,
                       coalesce(issue.high_issues, 0) AS high_issues,
                       coalesce(approval.pending_approvals, 0) AS pending_approvals,
                       coalesce(approval.document_count, 0) AS document_count
                FROM identity.divisions AS division
                LEFT JOIN project_stats AS project ON project.division_id = division.division_id
                LEFT JOIN task_stats AS task ON task.division_id = division.division_id
                LEFT JOIN issue_stats AS issue ON issue.division_id = division.division_id
                LEFT JOIN approval_stats AS approval ON approval.division_id = division.division_id
                WHERE division.organization_id = %s
                """,
                (
                    organization_id,
                    accessible,
                    organization_id,
                    organization_id,
                    organization_id,
                    organization_id,
                    organization_id,
                ),
            ).fetchall()
            trend_rows = connection.execute(
                """
                SELECT project.division_id,
                       to_char(date_trunc('month', history.recorded_on), 'YYYY-MM') AS period,
                       avg(history.progress_percent) AS average_progress
                FROM portfolio.project_progress_history AS history
                JOIN portfolio.projects AS project ON project.project_id = history.project_id
                WHERE project.organization_id = %s
                  AND project.workspace_id = ANY(%s::uuid[])
                  AND history.recorded_on >= %s
                  AND project.status <> 'ARCHIVED'
                GROUP BY project.division_id, date_trunc('month', history.recorded_on)
                ORDER BY date_trunc('month', history.recorded_on)
                """,
                (organization_id, accessible, months[0]),
            ).fetchall()
            issue_rows = connection.execute(
                """
                SELECT issue.issue_id, division.code AS division_code,
                       division.name AS division_name, issue.title, issue.severity,
                       owner.display_name AS owner_name, issue.status, issue.due_date
                FROM portfolio.division_issues AS issue
                JOIN identity.divisions AS division ON division.division_id = issue.division_id
                LEFT JOIN identity.users AS owner ON owner.user_id = issue.owner_user_id
                WHERE issue.organization_id = %s
                  AND issue.workspace_id = ANY(%s::uuid[])
                  AND issue.status <> 'RESOLVED'
                ORDER BY CASE issue.severity
                    WHEN 'CRITICAL' THEN 1 WHEN 'HIGH' THEN 2
                    WHEN 'MEDIUM' THEN 3 ELSE 4 END,
                    issue.due_date NULLS LAST, issue.created_at
                LIMIT 8
                """,
                (organization_id, accessible),
            ).fetchall()

        trends = _division_trends(rows, trend_rows, months)
        cards = [_division_card(row, trends[row["division_id"]]) for row in rows]
        order = {code: index for index, code in enumerate(_DIVISION_ORDER)}
        cards.sort(key=lambda item: order.get(item.division_code, len(order)))
        attention = [
            _division_attention(card)
            for card in cards
            if card.health in {"ATTENTION", "CRITICAL"}
        ]
        return DivisionsOverviewSnapshot(
            generated_at=now,
            divisions=cards,
            comparison=cards,
            issues=[DivisionIssueRecord.model_validate(row) for row in issue_rows],
            attention=attention,
        )

    def project_portfolio(
        self,
        *,
        organization_id: UUID,
        workspace_ids: list[UUID],
        division_code: str | None = None,
        project_status: ProjectStatus | None = None,
        category: str | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> ProjectPortfolioSnapshot:
        accessible = workspace_ids or [UUID(int=0)]
        now = datetime.now(UTC)
        where_sql, where_params = _project_filters(
            organization_id=organization_id,
            workspace_ids=accessible,
            division_code=division_code,
            project_status=project_status,
            category=category,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        project_from = """
            FROM portfolio.projects AS project
            JOIN identity.divisions AS division ON division.division_id = project.division_id
            JOIN workspace.workspaces AS workspace ON workspace.workspace_id = project.workspace_id
            LEFT JOIN identity.users AS owner ON owner.user_id = project.owner_user_id
        """
        with self._connection() as connection:
            status_query = (
                f"SELECT project.status, count(*) AS count {project_from} "
                f"WHERE {where_sql} GROUP BY project.status"
            )
            status_rows = connection.execute(status_query, where_params).fetchall()
            project_rows = connection.execute(
                f"""
                SELECT project.project_id, project.workspace_id, project.code, project.name,
                       division.code AS division_code, division.name AS division_name,
                       workspace.name AS workspace_name, project.category,
                       owner.display_name AS owner_name, project.progress_percent,
                       project.deadline, project.status, project.budget_planned,
                       project.budget_spent, project.currency,
                       (SELECT count(*) FROM operational.tasks AS task
                        WHERE task.project_id = project.project_id
                          AND task.due_date < current_date
                          AND task.status NOT IN ('DONE', 'CANCELLED')) AS overdue_tasks
                {project_from}
                WHERE {where_sql}
                ORDER BY CASE project.status
                    WHEN 'CRITICAL' THEN 1 WHEN 'AT_RISK' THEN 2
                    WHEN 'ON_TRACK' THEN 3 ELSE 4 END,
                    project.deadline NULLS LAST, project.name
                LIMIT %s OFFSET %s
                """,
                (*where_params, page_size, (page - 1) * page_size),
            ).fetchall()
            history_rows = connection.execute(
                f"""
                SELECT to_char(date_trunc('month', history.recorded_on), 'YYYY-MM') AS period,
                       avg(history.progress_percent) AS average_progress
                FROM portfolio.project_progress_history AS history
                JOIN portfolio.projects AS project ON project.project_id = history.project_id
                JOIN identity.divisions AS division ON division.division_id = project.division_id
                JOIN workspace.workspaces AS workspace
                  ON workspace.workspace_id = project.workspace_id
                LEFT JOIN identity.users AS owner ON owner.user_id = project.owner_user_id
                WHERE {where_sql} AND extract(year FROM history.recorded_on) = %s
                GROUP BY date_trunc('month', history.recorded_on)
                ORDER BY date_trunc('month', history.recorded_on)
                """,
                (*where_params, now.year),
            ).fetchall()
            milestone_rows = connection.execute(
                f"""
                SELECT milestone.milestone_id, milestone.project_id,
                       project.name AS project_name, milestone.title,
                       milestone.due_date, milestone.status
                FROM portfolio.project_milestones AS milestone
                JOIN portfolio.projects AS project ON project.project_id = milestone.project_id
                JOIN identity.divisions AS division ON division.division_id = project.division_id
                JOIN workspace.workspaces AS workspace
                  ON workspace.workspace_id = project.workspace_id
                LEFT JOIN identity.users AS owner ON owner.user_id = project.owner_user_id
                WHERE {where_sql} AND milestone.status <> 'COMPLETED'
                ORDER BY milestone.due_date, milestone.milestone_id
                LIMIT 5
                """,
                where_params,
            ).fetchall()
            filter_row = connection.execute(
                """
                SELECT array_agg(DISTINCT division.code ORDER BY division.code) AS divisions,
                       array_agg(DISTINCT project.category ORDER BY project.category) AS categories,
                       array_agg(DISTINCT project.status ORDER BY project.status)
                           FILTER (WHERE project.status <> 'ARCHIVED') AS statuses
                FROM portfolio.projects AS project
                JOIN identity.divisions AS division ON division.division_id = project.division_id
                WHERE project.organization_id = %s
                  AND project.workspace_id = ANY(%s::uuid[])
                  AND project.status <> 'ARCHIVED'
                """,
                (organization_id, accessible),
            ).fetchone()

        counts = {str(row["status"]): int(row["count"]) for row in status_rows}
        total = sum(counts.values())
        metrics = ProjectPortfolioMetrics(
            total=total,
            on_track=counts.get("ON_TRACK", 0),
            at_risk=counts.get("AT_RISK", 0),
            critical=counts.get("CRITICAL", 0),
            completed=counts.get("COMPLETED", 0),
        )
        total_pages = max(1, (total + page_size - 1) // page_size)
        return ProjectPortfolioSnapshot(
            generated_at=now,
            metrics=metrics,
            progress=_year_progress(now.year, history_rows),
            distribution=_distribution(metrics),
            projects=[ProjectPortfolioRecord.model_validate(row) for row in project_rows],
            milestones=[ProjectMilestoneRecord.model_validate(row) for row in milestone_rows],
            risk_summary=_risk_summary(metrics),
            filter_options=ProjectFilterOptions(
                divisions=list(filter_row["divisions"] or []) if filter_row else [],
                categories=list(filter_row["categories"] or []) if filter_row else [],
                statuses=list(filter_row["statuses"] or []) if filter_row else [],
            ),
            pagination=ProjectPagination(
                page=page,
                page_size=page_size,
                total_items=total,
                total_pages=total_pages,
            ),
        )

    @contextmanager
    def _connection(self) -> Iterator[psycopg.Connection[Any]]:
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            yield connection


def _project_filters(
    *,
    organization_id: UUID,
    workspace_ids: list[UUID],
    division_code: str | None,
    project_status: ProjectStatus | None,
    category: str | None,
    date_from: date | None,
    date_to: date | None,
    search: str | None,
) -> tuple[str, tuple[Any, ...]]:
    conditions = [
        "project.organization_id = %s",
        "project.workspace_id = ANY(%s::uuid[])",
        "project.status <> 'ARCHIVED'",
    ]
    params: list[Any] = [organization_id, workspace_ids]
    if division_code:
        conditions.append("division.code = %s")
        params.append(division_code)
    if project_status:
        conditions.append("project.status = %s")
        params.append(project_status)
    if category:
        conditions.append("project.category = %s")
        params.append(category)
    if date_from:
        conditions.append("project.deadline >= %s")
        params.append(date_from)
    if date_to:
        conditions.append("project.deadline <= %s")
        params.append(date_to)
    if search:
        conditions.append("(project.name ILIKE %s OR project.code ILIKE %s)")
        query = f"%{search.strip()}%"
        params.extend((query, query))
    return " AND ".join(conditions), tuple(params)


def _division_trends(
    divisions: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    months: list[date],
) -> dict[UUID, list[PortfolioTrendPoint]]:
    by_key = {(row["division_id"], str(row["period"])): row for row in rows}
    return {
        division["division_id"]: [
            PortfolioTrendPoint(
                period=month.strftime("%Y-%m"),
                label=_MONTH_LABELS[month.month - 1],
                value=(
                    round(float(row["average_progress"]), 1)
                    if (row := by_key.get((division["division_id"], month.strftime("%Y-%m"))))
                    else None
                ),
            )
            for month in months
        ]
        for division in divisions
    }


def _division_card(
    row: dict[str, Any], trend: list[PortfolioTrendPoint]
) -> DivisionOverviewCard:
    connected = (
        int(row["project_count"]) > 0
        or int(row["document_count"]) > 0
        or int(row["open_issues"]) > 0
    )
    if int(row["critical_projects"]) or int(row["critical_issues"]):
        health: DivisionHealth = "CRITICAL"
    elif (
        int(row["at_risk_projects"])
        or int(row["high_issues"])
        or int(row["open_issues"])
        or int(row["pending_approvals"])
    ):
        health = "ATTENTION"
    elif connected:
        health = "HEALTHY"
    else:
        health = "NOT_CONNECTED"
    return DivisionOverviewCard(
        division_id=row["division_id"],
        division_code=row["division_code"],
        division_name=row["division_name"],
        health=health,
        active_projects=int(row["active_projects"]),
        average_progress=(
            round(float(row["average_progress"]), 1)
            if row["average_progress"] is not None
            else None
        ),
        overdue_tasks=int(row["overdue_tasks"]),
        pending_approvals=int(row["pending_approvals"]),
        open_issues=int(row["open_issues"]),
        critical_projects=int(row["critical_projects"]),
        at_risk_projects=int(row["at_risk_projects"]),
        trend=trend,
    )


def _division_attention(card: DivisionOverviewCard) -> DivisionAttentionRecord:
    health: Literal["ATTENTION", "CRITICAL"] = (
        "CRITICAL" if card.health == "CRITICAL" else "ATTENTION"
    )
    parts = []
    if card.critical_projects:
        parts.append(f"{card.critical_projects} proyek kritis")
    if card.at_risk_projects:
        parts.append(f"{card.at_risk_projects} proyek berisiko")
    if card.open_issues:
        parts.append(f"{card.open_issues} isu terbuka")
    if card.pending_approvals:
        parts.append(f"{card.pending_approvals} approval pending")
    return DivisionAttentionRecord(
        division_id=card.division_id,
        division_code=card.division_code,
        division_name=card.division_name,
        health=health,
        summary=" · ".join(parts),
        trend=card.trend,
    )


def _year_progress(year: int, rows: list[dict[str, Any]]) -> list[PortfolioTrendPoint]:
    by_period = {str(row["period"]): row for row in rows}
    return [
        PortfolioTrendPoint(
            period=f"{year}-{month:02d}",
            label=_MONTH_LABELS[month - 1],
            value=(
                round(float(row["average_progress"]), 1)
                if (row := by_period.get(f"{year}-{month:02d}"))
                else None
            ),
        )
        for month in range(1, 13)
    ]


def _distribution(metrics: ProjectPortfolioMetrics) -> list[ProjectDistributionItem]:
    return [
        ProjectDistributionItem(status="ON_TRACK", label="On Track", count=metrics.on_track),
        ProjectDistributionItem(status="AT_RISK", label="At Risk", count=metrics.at_risk),
        ProjectDistributionItem(status="CRITICAL", label="Critical", count=metrics.critical),
        ProjectDistributionItem(status="COMPLETED", label="Selesai", count=metrics.completed),
    ]


def _risk_summary(metrics: ProjectPortfolioMetrics) -> list[ProjectRiskSummary]:
    return [
        ProjectRiskSummary(
            status="CRITICAL",
            count=metrics.critical,
            description=(
                "Memerlukan perhatian segera untuk menghindari keterlambatan signifikan."
            ),
        ),
        ProjectRiskSummary(
            status="AT_RISK",
            count=metrics.at_risk,
            description="Risiko sedang perlu dimonitor dan memiliki tindakan mitigasi.",
        ),
        ProjectRiskSummary(
            status="ON_TRACK",
            count=metrics.on_track,
            description="Proyek berjalan sesuai status terakhir yang tercatat.",
        ),
    ]


def _recent_month_starts(current: date, count: int) -> list[date]:
    month_index = current.year * 12 + current.month - 1
    result = []
    for offset in range(1 - count, 1):
        year, month = divmod(month_index + offset, 12)
        result.append(date(year, month + 1, 1))
    return result
