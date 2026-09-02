from alos.identity import DivisionCode, HumanRole, SystemActor


def test_organization_has_exactly_six_division_contexts() -> None:
    assert {division.value for division in DivisionCode} == {
        "FINANCE",
        "SALES_MARKETING",
        "PROPERTY",
        "HR",
        "LEGAL",
        "IT",
    }


def test_genesis_is_a_system_actor_not_a_human_role() -> None:
    assert SystemActor.GENESIS.value == "GENESIS"
    assert "AI_EXECUTIVE" not in {role.value for role in HumanRole}
