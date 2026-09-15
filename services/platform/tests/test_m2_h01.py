import pytest
from fastapi import HTTPException
from uuid import uuid4
from datetime import datetime

from alos.identity import DataScope
from alos.identity.models import ContextBundle, SourceRequirement
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
