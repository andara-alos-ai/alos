"""Release governance: no agent becomes active without independently recorded evidence."""

from __future__ import annotations

from collections.abc import Callable
from uuid import UUID, uuid4

from alos.evals.runner import AgentEvalInput, AgentStatusEvaluator
from alos.release.errors import (
    LifecycleConflictError,
    ReleaseGovernanceError,
    SegregationOfDutiesError,
)
from alos.release.models import (
    LifecycleEventRecord,
    LocalReleaseDuty,
    LocalReleaseParticipant,
    LocalReleaseTeam,
    ReasonRequest,
    ReleaseRequestDetail,
    ReleaseRequestInput,
    ReleaseRequestRecord,
    ReleaseState,
    ReviewDecision,
    ReviewGate,
    ReviewRecord,
    ReviewRequest,
    RollbackRequest,
    TestCaseRecord,
    TestCaseRequest,
    TestCategory,
    TestExecutionResult,
    TestRunEvidence,
)
from alos.release.repository import ReleaseGovernanceRepository
from alos.runtime.service import AgentRunRequest, AgentRunResult

Executor = Callable[[str, AgentRunRequest, UUID], AgentRunResult]


class AgentTestRunner:
    """Execute registered fixtures and persist result evidence before review."""

    def __init__(self, repository: ReleaseGovernanceRepository, executor: Executor) -> None:
        self._repository = repository
        self._evaluator = AgentStatusEvaluator(executor)

    def execute(
        self,
        change_request_id: UUID,
        test_key: str,
        *,
        checker_user_id: UUID,
        tenant_ids: tuple[UUID, ...] = (),
        correlation_id: UUID | None = None,
    ) -> TestExecutionResult:
        correlation_id = correlation_id or uuid4()
        self._repository.require_workspace_actor(
            change_request_id, checker_user_id, tenant_ids=tenant_ids
        )
        case = self._repository.get_test_case(
            change_request_id, test_key, tenant_ids=tenant_ids
        )
        requested_tools = case.input_fixture.get("requested_tool_keys", [])
        if not isinstance(requested_tools, list) or not all(
            isinstance(tool_key, str) for tool_key in requested_tools
        ):
            raise ReleaseGovernanceError("test fixture requested_tool_keys must be a string list")
        input_data = case.input_fixture.get("input", case.input_fixture)
        if not isinstance(input_data, dict):
            raise ReleaseGovernanceError("test fixture input must be an object")
        expected_status = case.expected_assertions.get("status")
        if expected_status not in {"SUCCEEDED", "FAILED", "BLOCKED"}:
            raise ReleaseGovernanceError("test expected_assertions.status is required")
        division_id, project_id, tenant_id = self._repository.scope_for_change(
            change_request_id, tenant_ids=tenant_ids
        )
        evaluation = self._evaluator.evaluate(
            AgentEvalInput(
                test_key=case.test_key,
                agent_key=case.agent_key,
                agent_version_id=case.agent_version_id,
                request=AgentRunRequest(
                    workspace_id=self._repository.workspace_for_change(
                        change_request_id, tenant_ids=tenant_ids
                    ),
                    division_id=division_id,
                    project_id=project_id,
                    tenant_id=tenant_id,
                    input=input_data,
                    requested_tool_keys=requested_tools,
                    testing=True,
                ),
            ),
            expected_status=expected_status,
        )
        return self._repository.record_test_result(
            change_request_id,
            case,
            checker_user_id=checker_user_id,
            correlation_id=correlation_id,
            passed=evaluation.status == "PASSED",
            agent_run_id=evaluation.agent_run_id,
            result={
                "expected_status": expected_status,
                "actual_status": evaluation.actual.get("status"),
                "error_code": evaluation.error_code,
                "block_reason": evaluation.block_reason,
            },
            evaluation=evaluation,
            tenant_ids=tenant_ids,
        )


__all__ = [
    "AgentTestRunner",
    "Executor",
    "LifecycleConflictError",
    "LocalReleaseDuty",
    "LocalReleaseParticipant",
    "LocalReleaseTeam",
    "ReasonRequest",
    "ReleaseGovernanceError",
    "ReleaseRequestDetail",
    "ReleaseRequestInput",
    "ReleaseRequestRecord",
    "ReleaseState",
    "ReviewDecision",
    "ReviewGate",
    "ReviewRecord",
    "ReviewRequest",
    "RollbackRequest",
    "SegregationOfDutiesError",
    "TestCaseRecord",
    "TestCaseRequest",
    "TestCategory",
    "TestExecutionResult",
    "TestRunEvidence",
    "LifecycleEventRecord",
    "ReleaseGovernanceRepository",
]
