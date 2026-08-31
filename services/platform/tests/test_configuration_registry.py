from pathlib import Path

import pytest
from pydantic import ValidationError

from alos.governance.configuration import (
    CanonicalConfigurationRegistry,
    ConfigurationMapping,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def registry() -> CanonicalConfigurationRegistry:
    return CanonicalConfigurationRegistry(REPOSITORY_ROOT / "definitions")


def test_master_and_all_annexes_have_canonical_governed_mapping() -> None:
    register = registry().get("ALOS-CR-MASTER-AN", "0.1.0")

    assert register.production_effect is False
    assert len(register.mappings) == 16
    assert {mapping.document_key for mapping in register.mappings} >= {
        "MASTER",
        *tuple("ABCDEFGHIJKLMN"),
    }
    assert all(mapping.source_references for mapping in register.mappings)


def test_only_locked_organization_mapping_is_approved() -> None:
    register = registry().get("ALOS-CR-MASTER-AN")
    approved = [mapping for mapping in register.mappings if mapping.status == "APPROVED"]

    assert [mapping.mapping_id for mapping in approved] == [
        "ALOS-CFG-LOCKED-ORG-STRUCTURE"
    ]
    assert approved[0].source_references == ("ALOS-SRC-ORG-LOCKED-001",)
    assert approved[0].blocked_by_decisions == ()


def test_unratified_annex_values_are_blocked_or_design_only() -> None:
    register = registry().get("ALOS-CR-MASTER-AN")
    draft_mappings = [mapping for mapping in register.mappings if mapping.status == "DRAFT"]

    assert draft_mappings
    assert all(mapping.activation_mode in {"BLOCKED", "DESIGN_ONLY"} for mapping in draft_mappings)
    assert all(
        mapping.blocked_by_decisions
        for mapping in draft_mappings
        if mapping.activation_mode == "BLOCKED"
    )


def test_approved_mapping_cannot_keep_open_decision() -> None:
    with pytest.raises(ValidationError, match="APPROVED"):
        ConfigurationMapping.model_validate(
            {
                "mapping_id": "ALOS-CFG-INVALID-APPROVAL",
                "document_key": "A",
                "name": "Invalid approved mapping",
                "target_registry": "INVALID_REGISTRY",
                "business_owner": "IT",
                "source_references": ["ALOS-SRC-APP-A-V40"],
                "status": "APPROVED",
                "disposition": "REUSE",
                "activation_mode": "RELEASE_CONTROLLED",
                "implementation_scope": ["Invalid test fixture"],
                "blocked_by_decisions": ["DEC-A01"],
            }
        )
