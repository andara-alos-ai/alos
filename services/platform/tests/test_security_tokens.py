from uuid import uuid4

import pytest

from alos.security import AuthenticationError, Principal, Role, TokenCodec


def codec() -> TokenCodec:
    return TokenCodec("test-signing-secret-with-32-characters", "test-issuer", "test-audience")


def test_signed_token_round_trip_preserves_authorization_context() -> None:
    project_id = uuid4()
    principal = Principal(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({Role.SALES}),
        division_codes=frozenset({"SALES_MARKETING"}),
        project_ids=frozenset({project_id}),
    )

    decoded = codec().verify(codec().issue(principal, 600))

    assert decoded == principal
    assert decoded.can_access_project(project_id)


def test_signed_token_rejects_tampering() -> None:
    principal = Principal(
        user_id=uuid4(),
        organization_id=uuid4(),
        roles=frozenset({Role.IT_ADMIN}),
    )
    token = codec().issue(principal, 600)

    with pytest.raises(AuthenticationError):
        codec().verify(token + "tampered")
