from uuid import UUID, uuid4

from alos.evals.runner import AgentEvalInput, AgentStatusEvaluator
from alos.runtime.service import AgentRunRequest, AgentRunResult


def _evaluation() -> AgentEvalInput:
    return AgentEvalInput(
        test_key="FACTORY_POSITIVE_1",
        agent_key="GENERATED_AGENT",
        agent_version_id=uuid4(),
        request=AgentRunRequest(
            workspace_id=uuid4(),
            tenant_id=uuid4(),
            input={"record_id": "fixture-1"},
            testing=True,
        ),
    )


def test_pydantic_evals_passes_only_an_actual_matching_agent_run() -> None:
    evaluation = _evaluation()
    run_id = uuid4()
    evaluator = AgentStatusEvaluator(
        lambda agent_key, request, version_id: AgentRunResult(
            agent_run_id=run_id,
            agent_key=agent_key,
            semantic_version="1.0.0",
            status="SUCCEEDED",
            correlation_id=uuid4(),
            output={"summary": "fixture", "findings": []},
            total_model_calls=1,
            total_tokens=12,
        )
    )

    outcome = evaluator.evaluate(evaluation, "SUCCEEDED")

    assert outcome.status == "PASSED"
    assert outcome.agent_run_id == run_id
    assert outcome.evaluator == "EqualsExpected"
    assert outcome.score == 1.0
    assert outcome.actual["status"] == "SUCCEEDED"
    assert outcome.input_reference["input_sha256"]


def test_pydantic_evals_fails_a_non_matching_actual_status() -> None:
    evaluation = _evaluation()
    evaluator = AgentStatusEvaluator(
        lambda agent_key, request, version_id: AgentRunResult(
            agent_run_id=uuid4(),
            agent_key=agent_key,
            semantic_version="1.0.0",
            status="BLOCKED",
            correlation_id=uuid4(),
            error_code="POLICY_BLOCKED",
        )
    )

    outcome = evaluator.evaluate(evaluation, "SUCCEEDED")

    assert outcome.status == "FAILED"
    assert outcome.score == 0.0
    assert outcome.actual["status"] == "BLOCKED"
    assert outcome.error_code == "POLICY_BLOCKED"


def test_pydantic_evals_records_executor_failure_as_error() -> None:
    evaluation = _evaluation()

    def fail(agent_key: str, request: AgentRunRequest, version_id: UUID) -> AgentRunResult:
        raise RuntimeError("provider fixture unavailable")

    outcome = AgentStatusEvaluator(fail).evaluate(evaluation, "SUCCEEDED")

    assert outcome.status == "ERROR"
    assert outcome.agent_run_id is None
    assert outcome.error_code == "EVALUATION_EXECUTION_ERROR"
    assert "provider fixture unavailable" in (outcome.block_reason or "")
