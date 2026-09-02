from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from alos.audit import compute_audit_entry_hash
from alos.security import Principal
from alos.uat.models import (
    SignoffDecision,
    UatCatalog,
    UatEvidenceView,
    UatRunCreate,
    UatRunStatus,
    UatRunView,
    UatScenarioRecord,
    UatScenarioResultView,
    UatSignoffCreate,
    UatSignoffView,
)


class PostgresUatRepository:
    """Transactional persistence for controlled-pilot UAT and human acceptance."""

    def __init__(self, engine: Engine, catalog: UatCatalog) -> None:
        self._engine = engine
        self._catalog = catalog

    def list_runs(self, organization_id: UUID, project_id: UUID) -> tuple[UatRunView, ...]:
        with self._engine.connect() as connection:
            run_ids = tuple(
                connection.execute(
                    text(
                        """
                        SELECT uat_run_id FROM uat.runs
                        WHERE organization_id = :organization_id
                          AND project_id = :project_id
                        ORDER BY cycle_number DESC
                        """
                    ),
                    {"organization_id": organization_id, "project_id": project_id},
                ).scalars()
            )
            return tuple(self._load_run(connection, run_id, organization_id) for run_id in run_ids)

    def get_run(self, uat_run_id: UUID, organization_id: UUID) -> UatRunView:
        with self._engine.connect() as connection:
            return self._load_run(connection, uat_run_id, organization_id)

    def create_run(self, command: UatRunCreate, principal: Principal) -> UatRunView:
        uat_run_id = uuid4()
        now = datetime.now(UTC)
        correlation_id = uuid4()
        with self._engine.begin() as connection:
            project_status = connection.execute(
                text(
                    """
                    SELECT status FROM platform.projects
                    WHERE project_id = :project_id AND organization_id = :organization_id
                    FOR UPDATE
                    """
                ),
                {
                    "project_id": command.project_id,
                    "organization_id": principal.organization_id,
                },
            ).scalar_one_or_none()
            if project_status is None:
                raise KeyError("Proyek UAT tidak ditemukan")
            if project_status != "ACTIVE":
                raise ValueError("UAT hanya dapat dibuat untuk proyek ACTIVE")
            cycle_number = int(
                connection.execute(
                    text(
                        """
                        SELECT COALESCE(max(cycle_number), 0) + 1
                        FROM uat.runs WHERE project_id = :project_id
                        """
                    ),
                    {"project_id": command.project_id},
                ).scalar_one()
            )
            actor_id = self._existing_actor_id(connection, principal)
            connection.execute(
                text(
                    """
                    INSERT INTO uat.runs
                        (uat_run_id, organization_id, project_id, title, cycle_number,
                         status, data_policy, created_by_user_id, created_at, updated_at)
                    VALUES
                        (:uat_run_id, :organization_id, :project_id, :title, :cycle_number,
                         'DRAFT', 'SYNTHETIC_OR_SANITIZED', :actor_id, :now, :now)
                    """
                ),
                {
                    "uat_run_id": uat_run_id,
                    "organization_id": principal.organization_id,
                    "project_id": command.project_id,
                    "title": command.title.strip(),
                    "cycle_number": cycle_number,
                    "actor_id": actor_id,
                    "now": now,
                },
            )
            for scenario in self._catalog.scenarios:
                connection.execute(
                    text(
                        """
                        INSERT INTO uat.scenario_results
                            (scenario_result_id, uat_run_id, scenario_id, status,
                             created_at, updated_at)
                        VALUES (:scenario_result_id, :uat_run_id, :scenario_id,
                                'NOT_STARTED', :now, :now)
                        """
                    ),
                    {
                        "scenario_result_id": uuid4(),
                        "uat_run_id": uat_run_id,
                        "scenario_id": scenario.scenario_id,
                        "now": now,
                    },
                )
            self._append_audit(
                connection,
                principal,
                "uat.run_created",
                "uat_run",
                uat_run_id,
                correlation_id,
                None,
                {
                    "project_id": str(command.project_id),
                    "cycle_number": cycle_number,
                    "status": UatRunStatus.DRAFT.value,
                    "data_policy": "SYNTHETIC_OR_SANITIZED",
                },
            )
            return self._load_run(connection, uat_run_id, principal.organization_id)

    def start_run(self, uat_run_id: UUID, principal: Principal) -> UatRunView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            current = self._run_row_for_update(connection, uat_run_id, principal.organization_id)
            if current["status"] != UatRunStatus.DRAFT.value:
                raise ValueError("Hanya UAT DRAFT yang dapat dimulai")
            connection.execute(
                text(
                    """
                    UPDATE uat.runs
                    SET status = 'IN_PROGRESS', started_at = :now, updated_at = :now,
                        version = version + 1
                    WHERE uat_run_id = :uat_run_id
                    """
                ),
                {"uat_run_id": uat_run_id, "now": now},
            )
            self._append_audit(
                connection,
                principal,
                "uat.run_started",
                "uat_run",
                uat_run_id,
                uuid4(),
                {"status": current["status"]},
                {"status": UatRunStatus.IN_PROGRESS.value},
            )
            return self._load_run(connection, uat_run_id, principal.organization_id)

    def record_scenario(
        self,
        uat_run_id: UUID,
        scenario_id: str,
        command: UatScenarioRecord,
        principal: Principal,
    ) -> UatRunView:
        now = datetime.now(UTC)
        with self._engine.begin() as connection:
            run = self._run_row_for_update(connection, uat_run_id, principal.organization_id)
            if run["status"] == UatRunStatus.READY_FOR_SIGNOFF.value:
                signoff_count = int(
                    connection.execute(
                        text(
                            "SELECT count(*) FROM uat.signoffs "
                            "WHERE uat_run_id = :uat_run_id"
                        ),
                        {"uat_run_id": uat_run_id},
                    ).scalar_one()
                )
                if signoff_count:
                    raise ValueError("Hasil tidak dapat diubah setelah sign-off dimulai")
            elif run["status"] != UatRunStatus.IN_PROGRESS.value:
                raise ValueError(
                    "Hasil hanya dapat dicatat saat UAT IN_PROGRESS atau sebelum sign-off dimulai"
                )
            result = (
                connection.execute(
                    text(
                        """
                        SELECT * FROM uat.scenario_results
                        WHERE uat_run_id = :uat_run_id AND scenario_id = :scenario_id
                        FOR UPDATE
                        """
                    ),
                    {"uat_run_id": uat_run_id, "scenario_id": scenario_id},
                )
                .mappings()
                .one_or_none()
            )
            if result is None:
                raise KeyError("Skenario UAT tidak ditemukan")
            actor_id = self._existing_actor_id(connection, principal)
            connection.execute(
                text(
                    """
                    UPDATE uat.scenario_results
                    SET status = :status, tester_user_id = :tester_user_id,
                        actual_result = :actual_result, defect_severity = :defect_severity,
                        defect_summary = :defect_summary, tested_at = :tested_at,
                        updated_at = :now, version = version + 1
                    WHERE scenario_result_id = :scenario_result_id
                    """
                ),
                {
                    "scenario_result_id": result["scenario_result_id"],
                    "status": command.status.value,
                    "tester_user_id": actor_id,
                    "actual_result": self._clean_optional(command.actual_result),
                    "defect_severity": (
                        command.defect_severity.value if command.defect_severity else None
                    ),
                    "defect_summary": self._clean_optional(command.defect_summary),
                    "tested_at": now,
                    "now": now,
                },
            )
            connection.execute(
                text(
                    "DELETE FROM uat.evidence_references "
                    "WHERE scenario_result_id = :scenario_result_id"
                ),
                {"scenario_result_id": result["scenario_result_id"]},
            )
            for evidence in command.evidence:
                if evidence.document_version_id is not None:
                    exists = connection.execute(
                        text(
                            """
                            SELECT 1
                            FROM platform.document_versions dv
                            JOIN platform.documents d ON d.document_id = dv.document_id
                            WHERE dv.document_version_id = :document_version_id
                              AND d.organization_id = :organization_id
                              AND d.project_id = :project_id
                              AND dv.scan_status IN ('NOT_CONFIGURED', 'CLEAN')
                              AND dv.verification_status <> 'REJECTED'
                            """
                        ),
                        {
                            "document_version_id": evidence.document_version_id,
                            "organization_id": principal.organization_id,
                            "project_id": run["project_id"],
                        },
                    ).scalar_one_or_none()
                    if exists is None:
                        raise KeyError("Dokumen evidence tidak tersedia pada proyek UAT")
                connection.execute(
                    text(
                        """
                        INSERT INTO uat.evidence_references
                            (evidence_reference_id, scenario_result_id, document_version_id,
                             reference, created_by_user_id, created_at)
                        VALUES (:evidence_reference_id, :scenario_result_id,
                                :document_version_id, :reference, :actor_id, :now)
                        """
                    ),
                    {
                        "evidence_reference_id": uuid4(),
                        "scenario_result_id": result["scenario_result_id"],
                        "document_version_id": evidence.document_version_id,
                        "reference": self._clean_optional(evidence.reference),
                        "actor_id": actor_id,
                        "now": now,
                    },
                )
            completed_count = int(
                connection.execute(
                    text(
                        """
                        SELECT count(*) FROM uat.scenario_results
                        WHERE uat_run_id = :uat_run_id
                          AND status IN ('PASSED', 'PASSED_WITH_RISK')
                        """
                    ),
                    {"uat_run_id": uat_run_id},
                ).scalar_one()
            )
            next_status = (
                UatRunStatus.READY_FOR_SIGNOFF
                if completed_count == len(self._catalog.scenarios)
                else UatRunStatus.IN_PROGRESS
            )
            connection.execute(
                text(
                    """
                    UPDATE uat.runs
                    SET status = :status, updated_at = :now, version = version + 1
                    WHERE uat_run_id = :uat_run_id
                    """
                ),
                {"uat_run_id": uat_run_id, "status": next_status.value, "now": now},
            )
            self._append_audit(
                connection,
                principal,
                "uat.scenario_recorded",
                "uat_scenario_result",
                result["scenario_result_id"],
                uuid4(),
                {"status": result["status"]},
                {
                    "scenario_id": scenario_id,
                    "status": command.status.value,
                    "evidence_count": len(command.evidence),
                    "defect_severity": (
                        command.defect_severity.value if command.defect_severity else None
                    ),
                },
            )
            return self._load_run(connection, uat_run_id, principal.organization_id)

    def signoff(
        self,
        uat_run_id: UUID,
        command: UatSignoffCreate,
        signer_role: str,
        principal: Principal,
    ) -> UatRunView:
        now = datetime.now(UTC)
        signoff_id = uuid4()
        with self._engine.begin() as connection:
            run = self._run_row_for_update(connection, uat_run_id, principal.organization_id)
            if run["status"] != UatRunStatus.READY_FOR_SIGNOFF.value:
                raise ValueError("Sign-off hanya dapat diberikan saat UAT READY_FOR_SIGNOFF")
            actor_id = self._existing_actor_id(connection, principal)
            connection.execute(
                text(
                    """
                    INSERT INTO uat.signoffs
                        (signoff_id, uat_run_id, signoff_scope, decision,
                         risk_severity, signer_user_id, signer_role, notes, signed_at)
                    VALUES (:signoff_id, :uat_run_id, :signoff_scope, :decision,
                            :risk_severity, :signer_user_id, :signer_role, :notes, :signed_at)
                    """
                ),
                {
                    "signoff_id": signoff_id,
                    "uat_run_id": uat_run_id,
                    "signoff_scope": command.signoff_scope.value,
                    "decision": command.decision.value,
                    "risk_severity": (
                        command.risk_severity.value if command.risk_severity else None
                    ),
                    "signer_user_id": actor_id,
                    "signer_role": signer_role,
                    "notes": command.notes.strip(),
                    "signed_at": now,
                },
            )
            signoff_rows = tuple(
                connection.execute(
                    text("SELECT decision FROM uat.signoffs WHERE uat_run_id = :uat_run_id"),
                    {"uat_run_id": uat_run_id},
                ).scalars()
            )
            next_status = UatRunStatus.READY_FOR_SIGNOFF
            completed_at: datetime | None = None
            if SignoffDecision.REJECTED.value in signoff_rows:
                next_status = UatRunStatus.REJECTED
                completed_at = now
            elif len(signoff_rows) == len(self._catalog.required_signoff_scopes):
                scenario_risk = connection.execute(
                    text(
                        """
                        SELECT 1 FROM uat.scenario_results
                        WHERE uat_run_id = :uat_run_id AND status = 'PASSED_WITH_RISK'
                        LIMIT 1
                        """
                    ),
                    {"uat_run_id": uat_run_id},
                ).scalar_one_or_none()
                has_risk = (
                    SignoffDecision.ACCEPTED_WITH_RISK.value in signoff_rows
                    or scenario_risk is not None
                )
                next_status = (
                    UatRunStatus.ACCEPTED_WITH_RISK if has_risk else UatRunStatus.ACCEPTED
                )
                completed_at = now
            connection.execute(
                text(
                    """
                    UPDATE uat.runs
                    SET status = :status, completed_at = :completed_at,
                        updated_at = :now, version = version + 1
                    WHERE uat_run_id = :uat_run_id
                    """
                ),
                {
                    "uat_run_id": uat_run_id,
                    "status": next_status.value,
                    "completed_at": completed_at,
                    "now": now,
                },
            )
            self._append_audit(
                connection,
                principal,
                "uat.signoff_recorded",
                "uat_signoff",
                signoff_id,
                uuid4(),
                None,
                {
                    "uat_run_id": str(uat_run_id),
                    "scope": command.signoff_scope.value,
                    "decision": command.decision.value,
                    "risk_severity": (
                        command.risk_severity.value if command.risk_severity else None
                    ),
                    "run_status": next_status.value,
                },
                command.notes.strip(),
            )
            return self._load_run(connection, uat_run_id, principal.organization_id)

    def _load_run(
        self, connection: Any, uat_run_id: UUID, organization_id: UUID
    ) -> UatRunView:
        run = (
            connection.execute(
                text(
                    """
                    SELECT * FROM uat.runs
                    WHERE uat_run_id = :uat_run_id AND organization_id = :organization_id
                    """
                ),
                {"uat_run_id": uat_run_id, "organization_id": organization_id},
            )
            .mappings()
            .one_or_none()
        )
        if run is None:
            raise KeyError("Siklus UAT tidak ditemukan")
        scenario_definitions = {
            item.scenario_id: item for item in self._catalog.scenarios
        }
        scenario_rows = tuple(
            connection.execute(
                text(
                    """
                    SELECT * FROM uat.scenario_results
                    WHERE uat_run_id = :uat_run_id ORDER BY scenario_id
                    """
                ),
                {"uat_run_id": uat_run_id},
            ).mappings()
        )
        scenarios: list[UatScenarioResultView] = []
        for row in scenario_rows:
            definition = scenario_definitions.get(row["scenario_id"])
            if definition is None:
                raise RuntimeError(f"Skenario tidak ada pada katalog: {row['scenario_id']}")
            evidence_rows = tuple(
                connection.execute(
                    text(
                        """
                        SELECT evidence_reference_id, document_version_id, reference, created_at
                        FROM uat.evidence_references
                        WHERE scenario_result_id = :scenario_result_id
                        ORDER BY created_at, evidence_reference_id
                        """
                    ),
                    {"scenario_result_id": row["scenario_result_id"]},
                ).mappings()
            )
            scenarios.append(
                UatScenarioResultView(
                    scenario_result_id=row["scenario_result_id"],
                    scenario_id=row["scenario_id"],
                    workspace=definition.workspace,
                    division_code=definition.division_code,
                    title=definition.title,
                    objective=definition.objective,
                    allowed_roles=definition.allowed_roles,
                    status=row["status"],
                    tester_user_id=row["tester_user_id"],
                    actual_result=row["actual_result"],
                    defect_severity=row["defect_severity"],
                    defect_summary=row["defect_summary"],
                    tested_at=row["tested_at"],
                    evidence=tuple(UatEvidenceView(**dict(item)) for item in evidence_rows),
                    version=row["version"],
                )
            )
        signoff_rows = tuple(
            connection.execute(
                text(
                    """
                    SELECT signoff_id, signoff_scope, decision, risk_severity, signer_user_id,
                           signer_role, notes, signed_at
                    FROM uat.signoffs WHERE uat_run_id = :uat_run_id
                    ORDER BY signed_at, signoff_scope
                    """
                ),
                {"uat_run_id": uat_run_id},
            ).mappings()
        )
        return UatRunView(
            **dict(run),
            scenarios=tuple(scenarios),
            signoffs=tuple(UatSignoffView(**dict(item)) for item in signoff_rows),
            required_signoff_scopes=self._catalog.required_signoff_scopes,
        )

    @staticmethod
    def _run_row_for_update(
        connection: Any, uat_run_id: UUID, organization_id: UUID
    ) -> Mapping[str, Any]:
        row = (
            connection.execute(
                text(
                    """
                    SELECT * FROM uat.runs
                    WHERE uat_run_id = :uat_run_id AND organization_id = :organization_id
                    FOR UPDATE
                    """
                ),
                {"uat_run_id": uat_run_id, "organization_id": organization_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise KeyError("Siklus UAT tidak ditemukan")
        return cast(Mapping[str, Any], row)

    @staticmethod
    def _existing_actor_id(connection: Any, principal: Principal) -> UUID | None:
        return cast(
            UUID | None,
            connection.execute(
            text(
                """
                SELECT user_id FROM identity.users
                WHERE user_id = :user_id AND organization_id = :organization_id
                """
            ),
            {
                "user_id": principal.user_id,
                "organization_id": principal.organization_id,
            },
            ).scalar_one_or_none(),
        )

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _append_audit(
        connection: Any,
        principal: Principal,
        action: str,
        entity_type: str,
        entity_id: UUID,
        correlation_id: UUID,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        reason: str | None = None,
    ) -> None:
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(CAST(:organization_id AS text)))"),
            {"organization_id": principal.organization_id},
        )
        previous_hash = connection.execute(
            text(
                """
                SELECT candidate.entry_hash
                FROM audit.entries AS candidate
                WHERE candidate.organization_id = :organization_id
                  AND NOT EXISTS (
                      SELECT 1
                      FROM audit.entries AS child
                      WHERE child.organization_id = candidate.organization_id
                        AND child.previous_hash = candidate.entry_hash
                  )
                ORDER BY candidate.occurred_at DESC, candidate.audit_entry_id DESC
                LIMIT 1
                FOR UPDATE OF candidate
                """
            ),
            {"organization_id": principal.organization_id},
        ).scalar_one_or_none()
        occurred_at = datetime.now(UTC)
        entry_hash = compute_audit_entry_hash(
            organization_id=principal.organization_id,
            actor_id=str(principal.user_id),
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            correlation_id=correlation_id,
            reason=reason,
            before=before,
            after=after,
            occurred_at=occurred_at,
            previous_hash=previous_hash,
        )
        connection.execute(
            text(
                """
                INSERT INTO audit.entries
                    (organization_id, occurred_at, actor_type, actor_id, active_role,
                     action, entity_type, entity_id, reason, before_masked, after_masked,
                     correlation_id, previous_hash, entry_hash)
                VALUES
                    (:organization_id, :occurred_at, 'HUMAN', :actor_id, :active_role,
                     :action, :entity_type, :entity_id, :reason, CAST(:before AS jsonb),
                     CAST(:after AS jsonb), :correlation_id, :previous_hash, :entry_hash)
                """
            ),
            {
                "organization_id": principal.organization_id,
                "occurred_at": occurred_at,
                "actor_id": str(principal.user_id),
                "active_role": sorted(role.value for role in principal.roles)[0],
                "action": action,
                "entity_type": entity_type,
                "entity_id": str(entity_id),
                "reason": reason,
                "before": json.dumps(before, default=str) if before is not None else None,
                "after": json.dumps(after, default=str) if after is not None else None,
                "correlation_id": correlation_id,
                "previous_hash": previous_hash,
                "entry_hash": entry_hash,
            },
        )
