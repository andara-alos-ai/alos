import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from alos.agents.registry import AgentRegistry
from alos.agents.runtime import AgentRunRequest, SharedAgentRuntime
from alos.config import get_settings
from alos.persistence import (
    AgentReleaseConflictError,
    Database,
    PostgresOperationalStore,
    WorkflowReleaseConflictError,
)
from alos.tools import ToolRegistry
from alos.workflow.registry import WorkflowRegistry

pytestmark = [
    pytest.mark.postgres,
    pytest.mark.skipif(
        os.getenv("ALOS_RUN_POSTGRES_TESTS") != "1",
        reason="set ALOS_RUN_POSTGRES_TESTS=1 to run PostgreSQL smoke tests",
    ),
]

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def test_agent_release_snapshot_is_complete_and_immutable() -> None:
    database = Database(get_settings().database_url)
    store = PostgresOperationalStore(database)
    definitions = REPOSITORY_ROOT / "definitions"
    runtime = SharedAgentRuntime(AgentRegistry(definitions), ToolRegistry(definitions))
    plan = runtime.prepare(
        AgentRunRequest(
            agent_id="BCA",
            agent_version="0.1.0",
            capability="check_budget_deterministically",
            input_references=["payment-request:agent-release-test"],
            requested_tools=["deterministic.calculator"],
            correlation_id=uuid4(),
            idempotency_key=f"agent-release-{uuid4().hex}",
        )
    )

    with database.engine.begin() as connection:
        release_id = store._upsert_agent_release(connection, plan)
        assert store._upsert_agent_release(connection, plan) == release_id
        release = connection.execute(
            text(
                """
                SELECT definition, status FROM agents.agent_releases
                WHERE agent_release_id = :agent_release_id
                """
            ),
            {"agent_release_id": release_id},
        ).mappings().one()
        definition = release["definition"]

        assert definition["agent_id"] == "BCA"
        assert definition["contract_version"] == "1.0.0"
        assert definition["agent_kind"] == "CORE"
        assert definition["capabilities"] == list(plan.contract_snapshot.capabilities)
        assert definition["contract_digest"] == plan.contract_digest
        assert "status" not in definition
        assert release["status"] == "STAGED"

        changed_contract = plan.contract_snapshot.model_copy(
            update={"purpose": "Tujuan sintetis berbeda untuk menguji konflik immutable."}
        )
        conflicting_plan = plan.model_copy(
            update={
                "contract_snapshot": changed_contract,
                "contract_digest": changed_contract.contract_digest,
            }
        )
        with pytest.raises(AgentReleaseConflictError, match="immutable berbeda"):
            store._upsert_agent_release(connection, conflicting_plan)

    with pytest.raises(DBAPIError, match="snapshot Agent Contract"), database.engine.begin(
    ) as connection:
        connection.execute(
            text(
                """
                UPDATE agents.agent_releases
                SET definition = jsonb_set(definition, '{purpose}', '"tampered"')
                WHERE agent_release_id = :agent_release_id
                """
            ),
            {"agent_release_id": release_id},
        )


def test_workflow_release_snapshot_is_complete_and_immutable() -> None:
    database = Database(get_settings().database_url)
    store = PostgresOperationalStore(database)
    workflow = WorkflowRegistry(REPOSITORY_ROOT / "definitions").get("FLOW-004")

    with database.engine.begin() as connection:
        release_id = store._upsert_workflow_release(connection, workflow)
        assert store._upsert_workflow_release(connection, workflow) == release_id
        release = connection.execute(
            text(
                """
                SELECT definition, status FROM workflow.workflow_releases
                WHERE workflow_release_id = :workflow_release_id
                """
            ),
            {"workflow_release_id": release_id},
        ).mappings().one()

        assert release["definition"]["definition_digest"] == workflow.definition_digest
        assert "status" not in release["definition"]
        assert release["status"] == "STAGED"

        changed = workflow.model_copy(
            update={"purpose": "Tujuan sintetis berbeda untuk menguji konflik immutable."}
        )
        with pytest.raises(WorkflowReleaseConflictError, match="immutable berbeda"):
            store._upsert_workflow_release(connection, changed)

    immutable_error = pytest.raises(
        DBAPIError, match="workflow release definition is immutable"
    )
    with immutable_error, database.engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE workflow.workflow_releases
                SET definition = jsonb_set(definition, '{purpose}', '"tampered"')
                WHERE workflow_release_id = :workflow_release_id
                """
            ),
            {"workflow_release_id": release_id},
        )
