from decimal import Decimal
from pathlib import Path

from alos.governance.approval_policy import ApprovalPolicyStatus, PaymentApprovalPolicyRegistry

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_payment_approval_policy_is_versioned_and_routes_deterministically() -> None:
    policy = PaymentApprovalPolicyRegistry(REPOSITORY_ROOT / "definitions").load()

    assert policy.status == ApprovalPolicyStatus.PILOT
    assert policy.production_effect is False
    assert policy.route_for(Decimal("25000000")).route == "FINANCE_REVIEWER"
    assert policy.route_for(Decimal("25000000.01")).route == "FINANCE_HEAD"
    assert policy.route_for(Decimal("250000000.01")).route == "DIRECTOR"
