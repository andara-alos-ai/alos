from pathlib import Path

import pytest
from pydantic import ValidationError

from alos.uat.catalog import load_uat_catalog
from alos.uat.models import UatScenarioRecord, UatSignoffCreate

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_controlled_pilot_uat_catalog_covers_eight_scenarios_and_signoffs() -> None:
    catalog = load_uat_catalog(REPOSITORY_ROOT / "definitions")

    assert [scenario.scenario_id for scenario in catalog.scenarios] == [
        "UAT-01",
        "UAT-02",
        "UAT-03",
        "UAT-04",
        "UAT-05",
        "UAT-06",
        "UAT-07",
        "UAT-08",
    ]
    assert len(catalog.required_signoff_scopes) == 8
    assert catalog.data_policy == "SYNTHETIC_OR_SANITIZED"


def test_passed_uat_scenario_requires_human_result_and_evidence() -> None:
    with pytest.raises(ValidationError, match="hasil aktual"):
        UatScenarioRecord(status="PASSED", evidence=({"reference": "AUDIT-001"},))

    with pytest.raises(ValidationError, match="minimal satu evidence"):
        UatScenarioRecord(status="PASSED", actual_result="Skenario berhasil sesuai SOP")


def test_high_risk_cannot_be_silently_accepted() -> None:
    with pytest.raises(ValidationError, match="hanya boleh LOW atau MEDIUM"):
        UatScenarioRecord(
            status="PASSED_WITH_RISK",
            actual_result="Skenario selesai dengan temuan",
            defect_severity="HIGH",
            defect_summary="Temuan high belum diperbaiki",
            evidence=({"reference": "EVIDENCE-HIGH-001"},),
        )

    with pytest.raises(ValidationError, match="hanya boleh LOW atau MEDIUM"):
        UatSignoffCreate(
            signoff_scope="DIRECTOR",
            decision="ACCEPTED_WITH_RISK",
            risk_severity="HIGH",
            notes="High risk tidak boleh diterima melalui sign-off.",
        )
