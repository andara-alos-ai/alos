"""Execute deterministic Agent status assertions through Pydantic Evals."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic_evals import Case, Dataset
from pydantic_evals.evaluators import EqualsExpected

from alos.runtime.service import AgentRunRequest, AgentRunResult

Executor = Callable[[str, AgentRunRequest, UUID], AgentRunResult]


class AgentEvalInput(BaseModel):
    """The exact version and bounded runtime request evaluated by one case."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    test_key: str
    agent_key: str
    agent_version_id: UUID
    request: AgentRunRequest


class AgentEvalOutcome(BaseModel):
    """Normalized evaluation output suitable for immutable persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["PASSED", "FAILED", "ERROR"]
    agent_run_id: UUID | None = None
    input_reference: dict[str, object]
    expected: dict[str, object]
    actual: dict[str, object]
    evaluator: str
    score: float | None = Field(default=None, ge=0, le=1)
    error_code: str | None = None
    block_reason: str | None = None
    started_at: datetime
    completed_at: datetime


class AgentStatusEvaluator:
    """Run an Agent and let Pydantic Evals assert its actual terminal status."""

    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def evaluate(self, evaluation: AgentEvalInput, expected_status: str) -> AgentEvalOutcome:
        started_at = datetime.now(UTC)
        runtime_results: list[AgentRunResult] = []

        def execute(inputs: AgentEvalInput) -> str:
            result = self._executor(
                inputs.agent_key,
                inputs.request,
                inputs.agent_version_id,
            )
            runtime_results.append(result)
            return result.status

        dataset = Dataset[AgentEvalInput, str, dict[str, str]](
            name=f"ALOS_AGENT_VERSION_{evaluation.agent_version_id}",
            cases=[
                Case(
                    name=evaluation.test_key,
                    inputs=evaluation,
                    expected_output=expected_status,
                    metadata={"agent_version_id": str(evaluation.agent_version_id)},
                )
            ],
            evaluators=[EqualsExpected()],
        )
        report = dataset.evaluate_sync(execute, progress=False)
        completed_at = datetime.now(UTC)
        input_reference: dict[str, object] = {
            "input_sha256": _digest(evaluation.request.input),
            "requested_tool_keys": sorted(evaluation.request.requested_tool_keys),
            "testing": evaluation.request.testing,
        }
        if report.failures or not report.cases or not runtime_results:
            message = report.failures[0].error_message if report.failures else "evaluation failed"
            return AgentEvalOutcome(
                status="ERROR",
                input_reference=input_reference,
                expected={"status": expected_status},
                actual={"status": None},
                evaluator="EqualsExpected",
                error_code="EVALUATION_EXECUTION_ERROR",
                block_reason=message[:1000],
                started_at=started_at,
                completed_at=completed_at,
            )

        result = runtime_results[0]
        report_case = report.cases[0]
        assertion = report_case.assertions.get("EqualsExpected")
        passed = assertion is not None and assertion.value is True
        block_reason = next(
            (
                decision.reason
                for decision in result.tool_decisions
                if decision.decision == "BLOCKED" and decision.reason
            ),
            None,
        )
        return AgentEvalOutcome(
            status="PASSED" if passed else "FAILED",
            agent_run_id=result.agent_run_id,
            input_reference=input_reference,
            expected={"status": expected_status},
            actual={
                "status": result.status,
                "error_code": result.error_code,
                "output_sha256": _digest(result.output) if result.output is not None else None,
                "total_model_calls": result.total_model_calls,
                "total_tool_calls": result.total_tool_calls,
                "total_tokens": result.total_tokens,
            },
            evaluator="EqualsExpected",
            score=1.0 if passed else 0.0,
            error_code=result.error_code,
            block_reason=block_reason,
            started_at=started_at,
            completed_at=completed_at,
        )


def _digest(value: object) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
