from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text


@dataclass(frozen=True)
class ActiveRole:
    user_id: UUID
    role_code: str
    division_code: str | None
    project_assigned: bool


@dataclass(frozen=True)
class PilotReadinessFacts:
    project_status: str | None
    division_codes: frozenset[str]
    active_roles: tuple[ActiveRole, ...]
    document_count: int
    dead_letter_count: int
    last_worker_status: str | None
    last_worker_completed_at: datetime | None
    latest_uat_status: str | None = None
    latest_uat_scenario_count: int = 0
    latest_uat_signoff_count: int = 0
    recovery_evidence_count: int = 0


class PostgresPilotReadinessRepository:
    """Read-only fact collector for deterministic pilot readiness evaluation."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def collect(self, organization_id: UUID, project_id: UUID) -> PilotReadinessFacts:
        with self._engine.connect() as connection:
            project_status = connection.execute(
                text(
                    """
                    SELECT status FROM platform.projects
                    WHERE project_id = :project_id AND organization_id = :organization_id
                    """
                ),
                {"project_id": project_id, "organization_id": organization_id},
            ).scalar_one_or_none()
            division_codes = frozenset(
                connection.execute(
                    text(
                        """
                        SELECT code FROM identity.divisions
                        WHERE organization_id = :organization_id
                        """
                    ),
                    {"organization_id": organization_id},
                ).scalars()
            )
            role_rows = connection.execute(
                text(
                    """
                    SELECT u.user_id, ra.role_code, d.code AS division_code,
                           EXISTS (
                               SELECT 1 FROM identity.project_assignments pa
                               WHERE pa.user_id = u.user_id
                                 AND pa.project_id = :project_id
                                 AND pa.valid_from <= now()
                                 AND (pa.valid_until IS NULL OR pa.valid_until > now())
                           ) AS project_assigned
                    FROM identity.users u
                    JOIN identity.role_assignments ra ON ra.user_id = u.user_id
                    LEFT JOIN identity.divisions d ON d.division_id = ra.division_id
                    WHERE u.organization_id = :organization_id
                      AND u.status = 'ACTIVE'
                      AND ra.valid_from <= now()
                      AND (ra.valid_until IS NULL OR ra.valid_until > now())
                    """
                ),
                {"project_id": project_id, "organization_id": organization_id},
            ).mappings()
            active_roles = tuple(
                ActiveRole(
                    user_id=row["user_id"],
                    role_code=row["role_code"],
                    division_code=row["division_code"],
                    project_assigned=bool(row["project_assigned"]),
                )
                for row in role_rows
            )
            document_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*)
                        FROM platform.documents d
                        JOIN platform.document_versions dv ON dv.document_id = d.document_id
                        WHERE d.organization_id = :organization_id
                          AND d.project_id = :project_id
                          AND dv.verification_status <> 'REJECTED'
                          AND dv.scan_status <> 'INFECTED'
                        """
                    ),
                    {"organization_id": organization_id, "project_id": project_id},
                ).scalar_one()
            )
            dead_letter_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*) FROM integration.outbox_events
                        WHERE organization_id = :organization_id
                          AND status = 'DEAD_LETTER'
                        """
                    ),
                    {"organization_id": organization_id},
                ).scalar_one()
            )
            latest_worker: Any = (
                connection.execute(
                    text(
                        """
                        SELECT status, completed_at
                        FROM observability.worker_runs
                        ORDER BY started_at DESC
                        LIMIT 1
                        """
                    )
                )
                .mappings()
                .one_or_none()
            )
            latest_uat: Any = (
                connection.execute(
                    text(
                        """
                        SELECT uat_run_id, status
                        FROM uat.runs
                        WHERE organization_id = :organization_id
                          AND project_id = :project_id
                        ORDER BY cycle_number DESC
                        LIMIT 1
                        """
                    ),
                    {"organization_id": organization_id, "project_id": project_id},
                )
                .mappings()
                .one_or_none()
            )
            latest_uat_scenario_count = 0
            latest_uat_signoff_count = 0
            recovery_evidence_count = 0
            if latest_uat is not None:
                latest_uat_scenario_count = int(
                    connection.execute(
                        text(
                            """
                            SELECT count(*) FROM uat.scenario_results
                            WHERE uat_run_id = :uat_run_id
                              AND status IN ('PASSED', 'PASSED_WITH_RISK')
                            """
                        ),
                        {"uat_run_id": latest_uat["uat_run_id"]},
                    ).scalar_one()
                )
                latest_uat_signoff_count = int(
                    connection.execute(
                        text(
                            "SELECT count(*) FROM uat.signoffs "
                            "WHERE uat_run_id = :uat_run_id"
                        ),
                        {"uat_run_id": latest_uat["uat_run_id"]},
                    ).scalar_one()
                )
                recovery_evidence_count = int(
                    connection.execute(
                        text(
                            """
                            SELECT count(*)
                            FROM uat.evidence_references er
                            JOIN uat.scenario_results sr
                              ON sr.scenario_result_id = er.scenario_result_id
                            WHERE sr.uat_run_id = :uat_run_id
                              AND sr.scenario_id = 'UAT-07'
                              AND sr.status IN ('PASSED', 'PASSED_WITH_RISK')
                            """
                        ),
                        {"uat_run_id": latest_uat["uat_run_id"]},
                    ).scalar_one()
                )
        return PilotReadinessFacts(
            project_status=project_status,
            division_codes=division_codes,
            active_roles=active_roles,
            document_count=document_count,
            dead_letter_count=dead_letter_count,
            last_worker_status=latest_worker["status"] if latest_worker else None,
            last_worker_completed_at=latest_worker["completed_at"] if latest_worker else None,
            latest_uat_status=latest_uat["status"] if latest_uat else None,
            latest_uat_scenario_count=latest_uat_scenario_count,
            latest_uat_signoff_count=latest_uat_signoff_count,
            recovery_evidence_count=recovery_evidence_count,
        )
