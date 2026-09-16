import pytest
from fastapi import HTTPException
from uuid import uuid4
from datetime import datetime

from alos.identity import DataScope
from alos.identity.models import ContextBundle, SourceRequirement
from alos.operational.models import (
    BacklogCandidate,
    OperationalFindingRecord,
    ProductionBacklog,
    RAndDFinding,
    Recommendation,
    ResearchRequest,
)
from alos.security.tokens import ActorContext
from alos.authorization import verify_context_boundaries

def test_verify_context_boundaries_positive():
    actor = ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({"DIVISION_MEMBER"}),
        permissions=frozenset({"READ_DOCUMENTS", "WRITE_LOGS"}),
        data_scope=DataScope.DIVISION,
        tenant_ids=frozenset(),
        workspace_ids=frozenset(),
        division_codes=frozenset(),
        issued_at=datetime.now(),
        expires_at=datetime.now()
    )
    bundle = ContextBundle(
        version="1.0",
        lifecycle_status="ACTIVE",
        owner_user_id=actor.user_id,
        risk_level="LOW",
        scope=DataScope.DIVISION,
        tools=["DOC_SEARCH"],
        permissions=["READ_DOCUMENTS"],
        sources=[]
    )
    
    # Should not raise exception
    verify_context_boundaries(actor, bundle)

def test_verify_context_boundaries_fails_on_scope_escalation():
    actor = ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({"DIVISION_MEMBER"}),
        permissions=frozenset(),
        data_scope=DataScope.DIVISION,
        tenant_ids=frozenset(),
        workspace_ids=frozenset(),
        division_codes=frozenset(),
        issued_at=datetime.now(),
        expires_at=datetime.now()
    )
    bundle = ContextBundle(
        version="1.0",
        lifecycle_status="ACTIVE",
        owner_user_id=actor.user_id,
        risk_level="HIGH",
        scope=DataScope.COMPANY, # Exceeds actor scope
        tools=[],
        permissions=[],
        sources=[]
    )
    
    with pytest.raises(HTTPException) as exc:
        verify_context_boundaries(actor, bundle)
    assert exc.value.status_code == 403

def test_verify_context_boundaries_fails_on_permission_escalation():
    actor = ActorContext(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({"DIVISION_MEMBER"}),
        permissions=frozenset(),
        data_scope=DataScope.DIVISION,
        tenant_ids=frozenset(),
        workspace_ids=frozenset(),
        division_codes=frozenset(),
        issued_at=datetime.now(),
        expires_at=datetime.now()
    )
    bundle = ContextBundle(
        version="1.0",
        lifecycle_status="ACTIVE",
        owner_user_id=actor.user_id,
        risk_level="LOW",
        scope=DataScope.DIVISION,
        tools=[],
        permissions=["SUDO_ACCESS"], # Actor lacks this
        sources=[]
    )
    
    with pytest.raises(HTTPException) as exc:
        verify_context_boundaries(actor, bundle)
    assert exc.value.status_code == 403


def test_rnd_contract_separates_research_from_operational_finding():
    request = ResearchRequest(
        workspace_id=uuid4(),
        domain="HR",
        title="Improve recruiting intake quality",
        objective="Find repeated service bottlenecks in onboarding workflow.",
        evidence=[{"source": "survey", "reference": "Q1-report"}],
        priority="HIGH",
        suggested_owner="HR-OPS",
        approval_state="DRAFT",
    )
    finding = RAndDFinding(
        finding_id=uuid4(),
        workspace_id=request.workspace_id,
        domain="HR",
        title="Candidate intake workflow errors",
        description="Repeated delays are observed in recruitment intake.",
        evidence=[{"source": "survey", "reference": "Q1-report"}],
        impact={"severity": "HIGH", "business_effect": "Delays hiring"},
        priority="HIGH",
        suggested_owner="HR-OPS",
        approval_state="PENDING_REVIEW",
    )

    assert request.domain == "HR"
    assert finding.kind == "R_AND_D"
    assert finding.approval_state == "PENDING_REVIEW"
    assert finding.evidence[0]["source"] == "survey"


def test_production_backlog_and_operational_finding_have_distinct_contracts():
    backlog = BacklogCandidate(
        item_id=uuid4(),
        workspace_id=uuid4(),
        domain="OPS",
        title="Fix onboarding validation",
        description="Add validation before onboarding approval.",
        evidence=[{"source": "incident-log", "reference": "INC-99"}],
        impact={"severity": "MEDIUM", "business_effect": "Manual rework"},
        priority="MEDIUM",
        suggested_owner="OPS-LEAD",
        approval_state="QUEUED",
    )
    production = ProductionBacklog(
        item_id=uuid4(),
        workspace_id=backlog.workspace_id,
        domain="OPS",
        title="Production backlog: onboarding validation",
        description="Validated production change for onboarding approval.",
        evidence=[{"source": "incident-log", "reference": "INC-99"}],
        impact={"severity": "MEDIUM", "business_effect": "Manual rework"},
        priority="MEDIUM",
        suggested_owner="OPS-LEAD",
        approval_state="APPROVED",
    )
    operational = OperationalFindingRecord(
        finding_id=uuid4(),
        workspace_id=backlog.workspace_id,
        domain="OPS",
        title="Operational incident in onboarding",
        description="Operational incident repeated in production.",
        evidence=[{"source": "incident-log", "reference": "INC-99"}],
        impact={"severity": "MEDIUM", "business_effect": "Manual rework"},
        priority="MEDIUM",
        suggested_owner="OPS-LEAD",
        approval_state="APPROVED",
    )

    assert backlog.kind == "BACKLOG_CANDIDATE"
    assert production.kind == "PRODUCTION_BACKLOG"
    assert operational.kind == "OPERATIONAL_FINDING"
    assert production.approval_state == "APPROVED"
