from decimal import Decimal

import pytest

from alos.identity.authentication import BootstrapError, hash_password, verify_password


def test_password_hash_is_salted_and_verifiable() -> None:
    password = "ALOS staging password with enough entropy"
    first = hash_password(password)
    second = hash_password(password)

    assert first != second
    assert verify_password(password, first)
    assert not verify_password("incorrect password", first)


def test_bootstrap_password_requires_a_long_secret() -> None:
    with pytest.raises(BootstrapError, match="at least 16"):
        hash_password("not-long-enough")


def test_cost_cap_keeps_decimal_precision() -> None:
    assert Decimal("0.125000") == Decimal("0.125")
