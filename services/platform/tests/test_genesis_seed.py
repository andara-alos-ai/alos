"""Tests for the Hari-1 validation-agent seed.

The three validation agents must (a) be created through the same GENESIS
factory as any other agent, (b) start as DRAFT so human review/activation
remains mandatory, and (c) seed idempotently without overwriting anything.
"""

from alos.genesis.catalog import VALIDATION_AGENT_KEYS
from alos.genesis.seed import GENESIS_SYSTEM_ACTOR, seed_validation_agents
from alos.genesis.service import GenesisService
from alos.genesis.store import InMemoryGenesisStore


def _service() -> GenesisService:
    return GenesisService(InMemoryGenesisStore())


def test_seed_creates_three_validation_agents_as_draft() -> None:
    service = _service()
    records = seed_validation_agents(service)

    assert {r.agent_key for r in records} == set(VALIDATION_AGENT_KEYS)
    assert len(records) == 3
    # Seeding drafts contracts; it never activates on a human's behalf.
    assert all(r.status == "DRAFT" for r in records)
    # Read-first agents never carry an irreversible tool.
    for record in records:
        contract = record.current.contract
        assert "TRANSFER_FUNDS" in {a.upper() for a in contract["forbidden_actions"]}
        assert "SELF_APPROVE" in {a.upper() for a in contract["forbidden_actions"]}


def test_seed_is_idempotent() -> None:
    service = _service()

    first = seed_validation_agents(service)
    second = seed_validation_agents(service)

    assert len(service.list_agents()) == 3
    assert {r.agent_key for r in second} == {r.agent_key for r in first}


def test_seed_does_not_overwrite_existing_agent() -> None:
    service = _service()
    seed_validation_agents(service)

    # Move an agent through the lifecycle; re-seeding must not reset it.
    service.submit_for_review("GEN_VAL_DAILY_BRIEF", GENESIS_SYSTEM_ACTOR)
    seed_validation_agents(service)

    record = service.get_agent("GEN_VAL_DAILY_BRIEF")
    assert record.status == "IN_REVIEW"
