from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from alos.platform.read_models import PageRequest
from alos.security import Principal, Role


@dataclass(frozen=True)
class ResourceSpec:
    select_sql: str
    from_sql: str
    id_expression: str
    organization_expression: str
    project_expression: str | None
    division_expression: str | None
    status_expression: str | None
    search_expression: str | None
    sort_columns: dict[str, str]


RESOURCE_SPECS: dict[str, ResourceSpec] = {
    "work_items": ResourceSpec(
        select_sql="""
            wi.work_item_id, wi.project_id, d.code AS division_code, wi.title,
            wi.work_type, wi.priority, wi.status, wi.owner_user_id, wi.due_at,
            wi.correlation_id, wi.created_at, wi.updated_at
        """,
        from_sql="""
            platform.work_items wi
            JOIN identity.divisions d ON d.division_id = wi.division_id
        """,
        id_expression="wi.work_item_id",
        organization_expression="wi.organization_id",
        project_expression="wi.project_id",
        division_expression="d.code",
        status_expression="wi.status",
        search_expression="concat_ws(' ', wi.title, wi.work_type)",
        sort_columns={
            "created_at": "wi.created_at",
            "updated_at": "wi.updated_at",
            "due_at": "wi.due_at",
            "priority": "wi.priority",
            "status": "wi.status",
        },
    ),
    "leads": ResourceSpec(
        select_sql="""
            l.lead_id, l.project_id, l.work_item_id, wr.workflow_run_id,
            l.full_name, l.phone, l.email, l.source, l.consent_recorded,
            l.status, l.assigned_user_id, wr.current_step,
            wr.status AS workflow_status, l.created_at, l.updated_at
        """,
        from_sql="""
            sales.leads l
            JOIN workflow.workflow_runs wr ON wr.work_item_id = l.work_item_id
        """,
        id_expression="l.lead_id",
        organization_expression="l.organization_id",
        project_expression="l.project_id",
        division_expression=None,
        status_expression="l.status",
        search_expression="concat_ws(' ', l.full_name, l.phone, l.email, l.source)",
        sort_columns={
            "created_at": "l.created_at",
            "updated_at": "l.updated_at",
            "status": "l.status",
            "full_name": "l.full_name",
        },
    ),
    "sales_interactions": ResourceSpec(
        select_sql="""
            i.interaction_id, i.lead_id, i.workflow_run_id, i.actor_user_id,
            i.channel, i.outcome, i.notes, i.evidence_reference, i.occurred_at
        """,
        from_sql="""
            sales.interactions i
            JOIN sales.leads l ON l.lead_id = i.lead_id
        """,
        id_expression="i.interaction_id",
        organization_expression="l.organization_id",
        project_expression="l.project_id",
        division_expression=None,
        status_expression="i.outcome",
        search_expression="concat_ws(' ', i.channel, i.outcome, i.notes)",
        sort_columns={"created_at": "i.occurred_at", "outcome": "i.outcome"},
    ),
    "budgets": ResourceSpec(
        select_sql="""
            b.budget_id, b.project_id, b.code, b.name, b.currency,
            b.allocated_amount, b.committed_amount, b.spent_amount,
            b.allocated_amount - b.committed_amount - b.spent_amount AS available_amount,
            b.status, b.created_at, b.updated_at
        """,
        from_sql="finance.budgets b",
        id_expression="b.budget_id",
        organization_expression="b.organization_id",
        project_expression="b.project_id",
        division_expression=None,
        status_expression="b.status",
        search_expression="concat_ws(' ', b.code, b.name)",
        sort_columns={
            "created_at": "b.created_at",
            "updated_at": "b.updated_at",
            "code": "b.code",
            "status": "b.status",
        },
    ),
    "payment_requests": ResourceSpec(
        select_sql="""
            pr.payment_request_id, pr.project_id, pr.budget_id, pr.work_item_id,
            pr.workflow_run_id, pr.approval_request_id, pr.document_version_id,
            pr.requester_user_id, pr.payee_name, pr.purpose, pr.amount, pr.currency,
            pr.requested_payment_date, pr.status, pr.budget_available,
            wr.current_step, wr.status AS workflow_status, pr.created_at, pr.updated_at
        """,
        from_sql="""
            finance.payment_requests pr
            JOIN workflow.workflow_runs wr ON wr.workflow_run_id = pr.workflow_run_id
        """,
        id_expression="pr.payment_request_id",
        organization_expression="pr.organization_id",
        project_expression="pr.project_id",
        division_expression=None,
        status_expression="pr.status",
        search_expression="concat_ws(' ', pr.payee_name, pr.purpose)",
        sort_columns={
            "created_at": "pr.created_at",
            "updated_at": "pr.updated_at",
            "payment_date": "pr.requested_payment_date",
            "amount": "pr.amount",
            "status": "pr.status",
        },
    ),
    "site_evidence": ResourceSpec(
        select_sql="""
            se.site_evidence_id, se.project_id, se.work_item_id, se.workflow_run_id,
            se.document_version_id, se.submitted_by_user_id, se.work_package_code,
            se.claim_date, se.claimed_progress, se.measured_progress, se.variance,
            se.status, se.reviewer_user_id, se.verified_progress, se.reviewed_at,
            se.created_at, se.updated_at
        """,
        from_sql="property.site_evidence se",
        id_expression="se.site_evidence_id",
        organization_expression="se.organization_id",
        project_expression="se.project_id",
        division_expression=None,
        status_expression="se.status",
        search_expression="concat_ws(' ', se.work_package_code, se.measurement_note)",
        sort_columns={
            "created_at": "se.created_at",
            "updated_at": "se.updated_at",
            "claim_date": "se.claim_date",
            "variance": "se.variance",
            "status": "se.status",
        },
    ),
    "kpi_snapshots": ResourceSpec(
        select_sql="""
            ks.kpi_snapshot_id, ks.project_id, ks.metric_code, ks.period_start,
            ks.period_end, ks.value, ks.unit, ks.source_entity_type,
            ks.source_entity_id, ks.verification_status, ks.created_at
        """,
        from_sql="executive.kpi_snapshots ks",
        id_expression="ks.kpi_snapshot_id",
        organization_expression="ks.organization_id",
        project_expression="ks.project_id",
        division_expression=None,
        status_expression="ks.verification_status",
        search_expression="concat_ws(' ', ks.metric_code, ks.unit, ks.source_entity_type)",
        sort_columns={
            "created_at": "ks.created_at",
            "period_end": "ks.period_end",
            "metric_code": "ks.metric_code",
            "status": "ks.verification_status",
        },
    ),
    "legal_cases": ResourceSpec(
        select_sql="""
            lc.legal_case_id, lc.project_id, lc.work_item_id, lc.workflow_run_id,
            lc.document_version_id, lc.document_type, lc.reference_code, lc.title,
            lc.counterparty, lc.source_authority, lc.effective_date, lc.expiry_date,
            lc.status, lc.legal_status, lc.official_source_verified,
            lc.reviewer_user_id, lc.reviewed_at, lc.created_at, lc.updated_at
        """,
        from_sql="legal.cases lc",
        id_expression="lc.legal_case_id",
        organization_expression="lc.organization_id",
        project_expression="lc.project_id",
        division_expression=None,
        status_expression="lc.status",
        search_expression="concat_ws(' ', lc.reference_code, lc.title, lc.counterparty)",
        sort_columns={
            "created_at": "lc.created_at",
            "updated_at": "lc.updated_at",
            "expiry_date": "lc.expiry_date",
            "reference_code": "lc.reference_code",
            "status": "lc.status",
        },
    ),
    "recruitment_requests": ResourceSpec(
        select_sql="""
            rr.recruitment_request_id, rr.project_id, rr.work_item_id,
            rr.workflow_run_id, rr.position_title, rr.requesting_division_code,
            rr.employment_type, rr.headcount, rr.justification, rr.criteria_version,
            rr.status, rr.reviewer_user_id, rr.decided_at, rr.created_at, rr.updated_at
        """,
        from_sql="hr.recruitment_requests rr",
        id_expression="rr.recruitment_request_id",
        organization_expression="rr.organization_id",
        project_expression="rr.project_id",
        division_expression=None,
        status_expression="rr.status",
        search_expression="concat_ws(' ', rr.position_title, rr.requesting_division_code)",
        sort_columns={
            "created_at": "rr.created_at",
            "updated_at": "rr.updated_at",
            "position_title": "rr.position_title",
            "status": "rr.status",
        },
    ),
    "documents": ResourceSpec(
        select_sql="""
            d.document_id, d.project_id, d.logical_name, d.classification,
            dv.document_version_id, dv.version_number, dv.object_key, dv.sha256,
            dv.media_type, dv.size_bytes, dv.verification_status,
            dv.created_at, d.updated_at
        """,
        from_sql="""
            platform.documents d
            JOIN LATERAL (
                SELECT document_version_id, version_number, object_key, sha256,
                       media_type, size_bytes, verification_status, created_at
                FROM platform.document_versions
                WHERE document_id = d.document_id
                ORDER BY version_number DESC LIMIT 1
            ) dv ON true
        """,
        id_expression="d.document_id",
        organization_expression="d.organization_id",
        project_expression="d.project_id",
        division_expression=None,
        status_expression="dv.verification_status",
        search_expression="concat_ws(' ', d.logical_name, d.classification, dv.media_type)",
        sort_columns={
            "created_at": "dv.created_at",
            "updated_at": "d.updated_at",
            "logical_name": "d.logical_name",
            "status": "dv.verification_status",
        },
    ),
    "evidence": ResourceSpec(
        select_sql="""
            e.evidence_id, e.work_item_id, wi.project_id, d.code AS division_code,
            e.document_version_id, e.claim_type, e.status, e.created_at
        """,
        from_sql="""
            platform.evidence e
            JOIN platform.work_items wi ON wi.work_item_id = e.work_item_id
            JOIN identity.divisions d ON d.division_id = wi.division_id
        """,
        id_expression="e.evidence_id",
        organization_expression="wi.organization_id",
        project_expression="wi.project_id",
        division_expression="d.code",
        status_expression="e.status",
        search_expression="e.claim_type",
        sort_columns={"created_at": "e.created_at", "status": "e.status"},
    ),
    "approvals": ResourceSpec(
        select_sql="""
            ar.approval_request_id, ar.work_item_id, wi.project_id,
            d.code AS division_code, ar.requester_user_id, ar.policy_code,
            ar.policy_version, ar.status, ar.material_fingerprint, ar.created_at,
            ar.decided_at, ad.approver_user_id, ad.reason AS decision_reason
        """,
        from_sql="""
            governance.approval_requests ar
            JOIN platform.work_items wi ON wi.work_item_id = ar.work_item_id
            JOIN identity.divisions d ON d.division_id = wi.division_id
            LEFT JOIN governance.approval_decisions ad
              ON ad.approval_request_id = ar.approval_request_id
        """,
        id_expression="ar.approval_request_id",
        organization_expression="wi.organization_id",
        project_expression="wi.project_id",
        division_expression="d.code",
        status_expression="ar.status",
        search_expression="ar.policy_code",
        sort_columns={
            "created_at": "ar.created_at",
            "decided_at": "ar.decided_at",
            "status": "ar.status",
        },
    ),
    "exceptions": ResourceSpec(
        select_sql="""
            ex.exception_id, ex.work_item_id, wi.project_id, d.code AS division_code,
            ex.category, ex.severity, ex.status, ex.owner_user_id, ex.due_at,
            ex.created_at
        """,
        from_sql="""
            governance.exceptions ex
            LEFT JOIN platform.work_items wi ON wi.work_item_id = ex.work_item_id
            LEFT JOIN identity.divisions d ON d.division_id = wi.division_id
        """,
        id_expression="ex.exception_id",
        organization_expression="ex.organization_id",
        project_expression="wi.project_id",
        division_expression="d.code",
        status_expression="ex.status",
        search_expression="concat_ws(' ', ex.category, ex.severity)",
        sort_columns={
            "created_at": "ex.created_at",
            "due_at": "ex.due_at",
            "severity": "ex.severity",
            "status": "ex.status",
        },
    ),
    "capas": ResourceSpec(
        select_sql="""
            c.capa_id, c.exception_id, ex.work_item_id, wi.project_id,
            d.code AS division_code, c.status, c.root_cause, c.corrective_action,
            c.preventive_action, c.reviewer_user_id, c.due_at, c.closed_at, c.created_at
        """,
        from_sql="""
            governance.capas c
            JOIN governance.exceptions ex ON ex.exception_id = c.exception_id
            LEFT JOIN platform.work_items wi ON wi.work_item_id = ex.work_item_id
            LEFT JOIN identity.divisions d ON d.division_id = wi.division_id
        """,
        id_expression="c.capa_id",
        organization_expression="ex.organization_id",
        project_expression="wi.project_id",
        division_expression="d.code",
        status_expression="c.status",
        search_expression="concat_ws(' ', c.root_cause, c.corrective_action, c.preventive_action)",
        sort_columns={
            "created_at": "c.created_at",
            "due_at": "c.due_at",
            "status": "c.status",
        },
    ),
    "executive_briefs": ResourceSpec(
        select_sql="""
            eb.executive_brief_id, es.project_id, eb.workflow_run_id,
            es.period_start, es.period_end, eb.title, eb.narrative,
            eb.source_references, eb.status, eb.reviewer_user_id, eb.review_notes,
            eb.reviewed_at, eb.created_at, eb.updated_at
        """,
        from_sql="""
            executive.briefs eb
            JOIN executive.snapshots es
              ON es.executive_snapshot_id = eb.executive_snapshot_id
        """,
        id_expression="eb.executive_brief_id",
        organization_expression="es.organization_id",
        project_expression="es.project_id",
        division_expression=None,
        status_expression="eb.status",
        search_expression="concat_ws(' ', eb.title, eb.narrative)",
        sort_columns={
            "created_at": "eb.created_at",
            "updated_at": "eb.updated_at",
            "period_end": "es.period_end",
            "status": "eb.status",
        },
    ),
    "workflow_runs": ResourceSpec(
        select_sql="""
            wr.workflow_run_id, wrel.workflow_id, wrel.version AS workflow_version,
            wr.work_item_id, wi.project_id, d.code AS division_code, wr.current_step,
            wr.status, wr.correlation_id, wr.started_at, wr.completed_at
        """,
        from_sql="""
            workflow.workflow_runs wr
            JOIN workflow.workflow_releases wrel
              ON wrel.workflow_release_id = wr.workflow_release_id
            LEFT JOIN platform.work_items wi ON wi.work_item_id = wr.work_item_id
            LEFT JOIN identity.divisions d ON d.division_id = wi.division_id
        """,
        id_expression="wr.workflow_run_id",
        organization_expression="wi.organization_id",
        project_expression="wi.project_id",
        division_expression="d.code",
        status_expression="wr.status",
        search_expression="concat_ws(' ', wrel.workflow_id, wr.current_step)",
        sort_columns={
            "created_at": "wr.started_at",
            "completed_at": "wr.completed_at",
            "status": "wr.status",
            "workflow_id": "wrel.workflow_id",
        },
    ),
    "transition_events": ResourceSpec(
        select_sql="""
            te.transition_event_id, te.workflow_run_id, te.from_step, te.outcome,
            te.to_step, te.actor_type, te.actor_id, te.occurred_at
        """,
        from_sql="""
            workflow.transition_events te
            JOIN workflow.workflow_runs wr ON wr.workflow_run_id = te.workflow_run_id
            JOIN platform.work_items wi ON wi.work_item_id = wr.work_item_id
            JOIN identity.divisions d ON d.division_id = wi.division_id
        """,
        id_expression="te.transition_event_id",
        organization_expression="wi.organization_id",
        project_expression="wi.project_id",
        division_expression="d.code",
        status_expression=None,
        search_expression="concat_ws(' ', te.from_step, te.outcome, te.to_step, te.actor_type)",
        sort_columns={"created_at": "te.occurred_at", "outcome": "te.outcome"},
    ),
    "agent_runs": ResourceSpec(
        select_sql="""
            ar.agent_run_id, arel.agent_id, arel.version AS agent_version,
            ar.workflow_run_id, wi.project_id, ar.status, ar.input_reference,
            ar.output_reference, ar.correlation_id, ar.started_at, ar.completed_at
        """,
        from_sql="""
            agents.agent_runs ar
            JOIN agents.agent_releases arel ON arel.agent_release_id = ar.agent_release_id
            LEFT JOIN workflow.workflow_runs wr ON wr.workflow_run_id = ar.workflow_run_id
            LEFT JOIN platform.work_items wi ON wi.work_item_id = wr.work_item_id
            LEFT JOIN identity.divisions d ON d.division_id = wi.division_id
        """,
        id_expression="ar.agent_run_id",
        organization_expression="wi.organization_id",
        project_expression="wi.project_id",
        division_expression="d.code",
        status_expression="ar.status",
        search_expression="arel.agent_id",
        sort_columns={
            "created_at": "ar.started_at",
            "completed_at": "ar.completed_at",
            "status": "ar.status",
            "agent_id": "arel.agent_id",
        },
    ),
    "audit_entries": ResourceSpec(
        select_sql="""
            ae.audit_entry_id, ae.occurred_at, ae.actor_type, ae.actor_id,
            ae.active_role, ae.action, ae.entity_type, ae.entity_id, ae.reason,
            ae.before_masked, ae.after_masked, ae.correlation_id,
            ae.previous_hash, ae.entry_hash
        """,
        from_sql="audit.entries ae",
        id_expression="ae.audit_entry_id",
        organization_expression="ae.organization_id",
        project_expression=None,
        division_expression=None,
        status_expression=None,
        search_expression="concat_ws(' ', ae.action, ae.entity_type, ae.entity_id, ae.actor_id)",
        sort_columns={
            "created_at": "ae.occurred_at",
            "action": "ae.action",
            "entity_type": "ae.entity_type",
        },
    ),
}


class PostgresQueryStore:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def list_records(
        self,
        resource: str,
        request: PageRequest,
        principal: Principal,
        extra_conditions: dict[str, Any] | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        spec = self._spec(resource)
        conditions, parameters = self._scope(spec, request, principal)
        self._apply_extra_conditions(conditions, parameters, extra_conditions)
        if parameters.pop("empty_scope", False):
            return [], 0
        sort_expression = spec.sort_columns.get(request.sort_by)
        if sort_expression is None:
            allowed = ", ".join(sorted(spec.sort_columns))
            raise ValueError(f"Kolom sort tidak valid. Pilihan: {allowed}")
        where_sql = " AND ".join(conditions)
        order = request.sort_order.value.upper()
        query = text(
            f"""
            SELECT {spec.select_sql}
            FROM {spec.from_sql}
            WHERE {where_sql}
            ORDER BY {sort_expression} {order} NULLS LAST, {spec.id_expression} ASC
            LIMIT :limit OFFSET :offset
            """  # noqa: S608 -- all structural SQL comes from the static whitelist above.
        )
        count_query = text(
            f"""
            SELECT count(*)
            FROM {spec.from_sql}
            WHERE {where_sql}
            """  # noqa: S608 -- all structural SQL comes from the static whitelist above.
        )
        parameters.update(limit=request.page_size, offset=request.offset)
        with self._engine.connect() as connection:
            total = int(connection.execute(count_query, parameters).scalar_one())
            rows = connection.execute(query, parameters).mappings().all()
        return [dict(row) for row in rows], total

    def get_record(self, resource: str, record_id: UUID, principal: Principal) -> dict[str, Any]:
        spec = self._spec(resource)
        request = PageRequest(page=1, page_size=1)
        conditions, parameters = self._scope(spec, request, principal)
        if parameters.pop("empty_scope", False):
            raise KeyError("Data tidak ditemukan")
        conditions.append(f"{spec.id_expression} = :record_id")
        parameters["record_id"] = record_id
        query = text(
            f"""
            SELECT {spec.select_sql}
            FROM {spec.from_sql}
            WHERE {" AND ".join(conditions)}
            """  # noqa: S608 -- all structural SQL comes from the static whitelist above.
        )
        with self._engine.connect() as connection:
            row = connection.execute(query, parameters).mappings().one_or_none()
        if row is None:
            raise KeyError("Data tidak ditemukan")
        return dict(row)

    def get_personnel_checklist(
        self, recruitment_request_id: UUID, principal: Principal
    ) -> dict[str, Any]:
        project_scope, parameters = self._project_scope(principal)
        if project_scope is None:
            raise KeyError("Checklist personalia tidak ditemukan")
        query = text(
            f"""
            SELECT pc.personnel_checklist_id, pc.recruitment_request_id,
                   pc.candidate_id, pc.status, pc.created_at,
                   COALESCE(
                       jsonb_agg(
                           jsonb_build_object(
                               'requirement_code', preq.requirement_code,
                               'status', preq.status
                           ) ORDER BY preq.requirement_code
                       ) FILTER (WHERE preq.personnel_requirement_id IS NOT NULL),
                       '[]'::jsonb
                   ) AS requirements
            FROM hr.personnel_checklists pc
            JOIN hr.recruitment_requests rr
              ON rr.recruitment_request_id = pc.recruitment_request_id
            LEFT JOIN hr.personnel_requirements preq
              ON preq.personnel_checklist_id = pc.personnel_checklist_id
            WHERE rr.organization_id = :organization_id
              AND pc.recruitment_request_id = :recruitment_request_id
              {project_scope}
            GROUP BY pc.personnel_checklist_id
            """  # noqa: S608 -- project_scope is selected from static clauses only.
        )
        parameters.update(
            organization_id=principal.organization_id,
            recruitment_request_id=recruitment_request_id,
        )
        with self._engine.connect() as connection:
            row = connection.execute(query, parameters).mappings().one_or_none()
        if row is None:
            raise KeyError("Checklist personalia tidak ditemukan")
        return dict(row)

    @staticmethod
    def _spec(resource: str) -> ResourceSpec:
        try:
            return RESOURCE_SPECS[resource]
        except KeyError as exc:
            raise ValueError("Resource query tidak terdaftar") from exc

    @staticmethod
    def _scope(
        spec: ResourceSpec, request: PageRequest, principal: Principal
    ) -> tuple[list[str], dict[str, Any]]:
        conditions = [f"{spec.organization_expression} = :organization_id"]
        parameters: dict[str, Any] = {"organization_id": principal.organization_id}
        organization_wide = principal.has_any_role(
            Role.DIRECTOR, Role.AI_EXECUTIVE, Role.IT_ADMIN, Role.AUDITOR
        )
        if request.project_id is not None:
            if spec.project_expression is None:
                raise ValueError("Resource ini tidak mendukung filter project_id")
            if not principal.can_access_project(request.project_id):
                parameters["empty_scope"] = True
                return conditions, parameters
            conditions.append(f"{spec.project_expression} = :project_id")
            parameters["project_id"] = request.project_id
        elif spec.project_expression is not None and not organization_wide:
            if not principal.project_ids:
                parameters["empty_scope"] = True
                return conditions, parameters
            conditions.append(f"{spec.project_expression} = ANY(CAST(:project_ids AS uuid[]))")
            parameters["project_ids"] = [str(value) for value in principal.project_ids]
        if spec.division_expression is not None and not organization_wide:
            if not principal.division_codes:
                parameters["empty_scope"] = True
                return conditions, parameters
            conditions.append(f"{spec.division_expression} = ANY(CAST(:division_codes AS text[]))")
            parameters["division_codes"] = sorted(principal.division_codes)
        if request.status is not None:
            if spec.status_expression is None:
                raise ValueError("Resource ini tidak mendukung filter status")
            conditions.append(f"{spec.status_expression} = :status")
            parameters["status"] = request.status
        if request.search is not None:
            if spec.search_expression is None:
                raise ValueError("Resource ini tidak mendukung pencarian")
            conditions.append(f"{spec.search_expression} ILIKE :search")
            parameters["search"] = f"%{request.search.strip()}%"
        return conditions, parameters

    @staticmethod
    def _apply_extra_conditions(
        conditions: list[str],
        parameters: dict[str, Any],
        extra_conditions: dict[str, Any] | None,
    ) -> None:
        if not extra_conditions:
            return
        allowed = {
            "lead_id": "i.lead_id",
            "workflow_run_id": "te.workflow_run_id",
        }
        for key, value in extra_conditions.items():
            expression = allowed.get(key)
            if expression is None:
                raise ValueError("Filter tambahan tidak terdaftar")
            conditions.append(f"{expression} = :extra_{key}")
            parameters[f"extra_{key}"] = value

    @staticmethod
    def _project_scope(principal: Principal) -> tuple[str | None, dict[str, Any]]:
        if principal.has_any_role(Role.DIRECTOR, Role.AI_EXECUTIVE, Role.IT_ADMIN, Role.AUDITOR):
            return "", {}
        if not principal.project_ids:
            return None, {}
        return (
            "AND rr.project_id = ANY(CAST(:project_ids AS uuid[]))",
            {"project_ids": [str(value) for value in principal.project_ids]},
        )
