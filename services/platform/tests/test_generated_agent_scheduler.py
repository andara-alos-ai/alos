from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from alos.identity import DataScope, HumanRole
from alos.jobs.repository import AgentJobContext, JobRecord
from alos.jobs.scheduler import DurableScheduler
from alos.jobs.worker import DurableWorker
from alos.runtime.service import AgentRunResult
from alos.security.tokens import ActorContext


def _job() -> JobRecord:
    now = datetime.now(UTC)
    return JobRecord(
        job_id=uuid4(),
        organization_id=uuid4(),
        workspace_id=uuid4(),
        job_type="AGENT_RUN",
        payload={
            "agent_schedule_id": str(uuid4()),
            "agent_version_id": str(uuid4()),
        },
        status="RUNNING",
        attempts=1,
        max_attempts=3,
        next_retry_at=now,
        correlation_id=uuid4(),
        owner_user_id=uuid4(),
        idempotency_key="agent:schedule:fixture",
        locked_by="worker-test",
        locked_at=now,
        started_at=now,
        completed_at=None,
        safe_error_code=None,
        created_at=now,
    )


def test_scheduler_enqueues_reports_and_generated_agents_in_one_tick() -> None:
    scheduler = DurableScheduler("postgresql+psycopg://ignored", scheduler_id="scheduler-test")
    queue = MagicMock()
    queue.schedule_due_reports.return_value = [MagicMock()]
    queue.schedule_due_agents.return_value = [MagicMock(), MagicMock()]
    scheduler._queue = queue

    assert scheduler.tick() == 3
    queue.schedule_due_reports.assert_called_once_with("scheduler-test")
    queue.schedule_due_agents.assert_called_once_with("scheduler-test")
    queue.heartbeat.assert_called_once_with("SCHEDULER", "scheduler-test")


def test_worker_invokes_exact_active_agent_version_and_persists_job_result() -> None:
    job = _job()
    context = AgentJobContext(
        agent_schedule_id=uuid4(),
        agent_key="GENESIS_GENERATED_AGENT",
        agent_version_id=uuid4(),
        organization_id=job.organization_id,
        workspace_id=job.workspace_id,
        division_id=None,
        project_id=None,
        tenant_id=uuid4(),
        owner_user_id=job.owner_user_id,
        input={"fixture": "scheduled"},
        requested_tool_keys=[],
    )
    actor = ActorContext(
        user_id=context.owner_user_id,
        organization_id=context.organization_id,
        roles=[HumanRole.AI_ADMIN],
        workspace_ids=[context.workspace_id],
        tenant_ids=[context.tenant_id],
        data_scope=DataScope.COMPANY,
        permissions=[],
        issued_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    runtime = MagicMock()
    runtime.execute.return_value = AgentRunResult(
        agent_run_id=uuid4(),
        agent_key=context.agent_key,
        semantic_version="1.0.0",
        status="SUCCEEDED",
        correlation_id=job.correlation_id,
        total_model_calls=1,
        total_tokens=20,
    )
    worker = DurableWorker(
        "postgresql+psycopg://ignored",
        worker_id="worker-test",
        runtime_factory=lambda: runtime,
    )
    queue = MagicMock()
    queue.claim.return_value = job
    queue.authorize_agent_job.return_value = context
    queue.succeed.return_value = job
    worker._queue = queue
    worker._actor = MagicMock(return_value=actor)

    assert worker.run_once() is job

    runtime.execute.assert_called_once()
    call = runtime.execute.call_args
    assert call.args[0] == context.agent_key
    assert call.kwargs["target_agent_version_id"] == context.agent_version_id
    assert call.kwargs["allow_draft"] is False
    assert call.kwargs["actor"] == actor
    assert call.args[1].tenant_id == context.tenant_id
    persisted = queue.succeed.call_args.kwargs["result"]
    assert persisted["agent_run_id"] == str(runtime.execute.return_value.agent_run_id)
    assert persisted["status"] == "SUCCEEDED"
