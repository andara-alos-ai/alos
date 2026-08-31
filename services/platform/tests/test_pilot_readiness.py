import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from alos.platform.readiness.models import (
    PilotReadinessCheck,
    PilotReadinessReport,
    ReadinessCheckStatus,
    ReadinessOverallStatus,
)
from alos.platform.readiness.service import load_pilot_readiness_profile

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_controlled_pilot_profile_is_versioned_and_has_no_production_effect() -> None:
    profile = load_pilot_readiness_profile(REPOSITORY_ROOT / "definitions")

    assert profile.profile_id == "ALOS-CONTROLLED-PILOT"
    assert profile.status == "PILOT"
    assert profile.data_policy == "SYNTHETIC_OR_SANITIZED"
    assert profile.production_effect is False
    assert profile.expected_core_agents == 18
    assert profile.expected_workflows == 6
    assert profile.required_divisions == {
        "FINANCE",
        "SALES_MARKETING",
        "PROPERTY",
        "HR",
        "LEGAL",
        "IT",
    }


def test_controlled_pilot_fixture_contains_only_declared_synthetic_identities() -> None:
    path = REPOSITORY_ROOT / "tests" / "fixtures" / "synthetic" / "controlled-pilot.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))

    assert fixture["data_policy"] == "SYNTHETIC_OR_SANITIZED"
    assert fixture["production_effect"] is False
    assert fixture["organization_code"] == "ARM"
    assert all(user["email"].endswith("@example.test") for user in fixture["users"])
    assert fixture["scenarios"]["hr"]["candidate_alias"].startswith("CAND-SYN-")
    assigned_domains = {
        user["division_code"]
        for user in fixture["users"]
        if user["project_assigned"]
    }
    assert assigned_domains == {"SALES_MARKETING", "FINANCE", "PROPERTY", "HR", "LEGAL"}
    assert set(fixture["scenarios"]) == {
        "sales",
        "finance",
        "property",
        "legal",
        "hr",
        "executive",
    }


def test_readiness_report_rejects_an_inconsistent_summary() -> None:
    passing_check = PilotReadinessCheck(
        check_id="PILOT-UNIT-CHECK",
        category="TEST",
        title="Unit readiness check",
        status=ReadinessCheckStatus.PASS,
        required=True,
        detail="Pemeriksaan unit lulus.",
    )

    with pytest.raises(ValidationError, match="Ringkasan readiness tidak cocok"):
        PilotReadinessReport(
            organization_id=uuid4(),
            project_id=uuid4(),
            environment="local",
            evaluated_at=datetime.now(UTC),
            overall_status=ReadinessOverallStatus.ATTENTION,
            passed_checks=0,
            warning_checks=1,
            blocked_checks=0,
            checks=(passing_check,),
        )
