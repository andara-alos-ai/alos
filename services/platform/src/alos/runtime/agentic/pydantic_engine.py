"""PydanticAI implementation of the ALOS agentic execution boundary."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from decimal import Decimal
from threading import Lock
from time import monotonic
from typing import Any
from uuid import UUID

from pydantic_ai import Agent, CancellationToken, StructuredDict, Tool, UsageLimits
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.models import Model

from alos.runtime.agentic.dependencies import AgenticToolInvoker
from alos.runtime.agentic.output import (
    AgenticExecutionRequest,
    AgenticExecutionResult,
    AgenticStep,
    CumulativeUsage,
    ExecutionStatus,
    StepType,
)


class PydanticAgenticEngine:
    """Run PydanticAI behind ALOS-owned requests, limits, and result types."""

    def __init__(self, model: Model, tool_invoker: AgenticToolInvoker | None = None) -> None:
        self._model = model
        self._tool_invoker = tool_invoker
        self._active: dict[UUID, CancellationToken] = {}
        self._active_lock = Lock()

    def execute(self, request: AgenticExecutionRequest) -> AgenticExecutionResult:
        started = monotonic()
        token = CancellationToken()
        with self._active_lock:
            if request.context.run_id in self._active:
                return _terminal_error(
                    request,
                    ExecutionStatus.BLOCKED,
                    "DUPLICATE_ACTIVE_RUN",
                    "An execution with this run_id is already active.",
                    started,
                )
            self._active[request.context.run_id] = token

        try:
            result = asyncio.run(self._run(request, token))
        except UsageLimitExceeded:
            return _terminal_error(
                request,
                ExecutionStatus.BLOCKED,
                "RUNTIME_LIMIT_EXCEEDED",
                "PydanticAI stopped before an ALOS execution limit was exceeded.",
                started,
            )
        except TimeoutError:
            token.cancel()
            return _terminal_error(
                request,
                ExecutionStatus.BLOCKED,
                "MAX_ELAPSED_SECONDS",
                "The execution reached its elapsed-time limit.",
                started,
            )
        except asyncio.CancelledError:
            return _terminal_error(
                request,
                ExecutionStatus.CANCELLED,
                "RUN_CANCELLED",
                "The execution was cancelled.",
                started,
            )
        except UnexpectedModelBehavior:
            return _terminal_error(
                request,
                ExecutionStatus.FAILED,
                "MODEL_BEHAVIOR_INVALID",
                "The model response could not satisfy the governed output contract.",
                started,
            )
        except Exception:
            return _terminal_error(
                request,
                ExecutionStatus.FAILED,
                "AGENTIC_EXECUTION_FAILED",
                "The agentic engine failed without exposing provider or credential details.",
                started,
            )
        finally:
            with self._active_lock:
                self._active.pop(request.context.run_id, None)

        elapsed_ms = _elapsed_milliseconds(started)
        usage = result.usage
        response = result.response
        return AgenticExecutionResult(
            run_id=request.context.run_id,
            correlation_id=request.context.correlation_id,
            status=ExecutionStatus.SUCCEEDED,
            output=dict(result.output),
            usage=CumulativeUsage(
                total_model_calls=usage.requests,
                total_input_tokens=usage.input_tokens,
                total_output_tokens=usage.output_tokens,
                total_tokens=usage.total_tokens,
                total_tool_calls=usage.tool_calls,
                total_cost=usage.cost or Decimal("0"),
                total_latency_milliseconds=elapsed_ms,
            ),
            steps=(
                AgenticStep(
                    sequence=1,
                    step_type=StepType.FINAL,
                    status=ExecutionStatus.SUCCEEDED,
                    duration_milliseconds=elapsed_ms,
                    model=response.model_name,
                    provider=response.provider_name,
                ),
            ),
        )

    def cancel(self, run_id: UUID) -> bool:
        with self._active_lock:
            token = self._active.get(run_id)
            if token is None:
                return False
            token.cancel()
            return True

    async def _run(self, request: AgenticExecutionRequest, token: CancellationToken) -> Any:
        output_type = StructuredDict(
            request.output_schema,
            name="alos_governed_output",
            description="Output governed by the versioned ALOS Agent Contract.",
        )
        agent = Agent(
            self._model,
            output_type=output_type,
            instructions=request.instructions,
            retries=request.limits.max_retries,
            tools=self._tools(request),
            tool_timeout=request.limits.max_elapsed_seconds,
            max_concurrency=request.limits.max_concurrency,
        )
        usage_limits = UsageLimits(
            cost_limit=request.limits.max_cost_per_run,
            request_limit=request.limits.max_model_steps,
            tool_calls_limit=request.limits.max_tool_calls,
            input_tokens_limit=request.limits.max_input_tokens,
            output_tokens_limit=request.limits.max_output_tokens,
            total_tokens_limit=request.limits.max_total_tokens,
        )
        async with asyncio.timeout(request.limits.max_elapsed_seconds):
            return await agent.run(
                request.input_text,
                usage_limits=usage_limits,
                cancellation_token=token,
                run_id=str(request.context.run_id),
            )

    def _tools(self, request: AgenticExecutionRequest) -> list[Tool[Any]]:
        if request.tools and self._tool_invoker is None:
            raise RuntimeError("configured tools require an ALOS tool invoker")
        tools: list[Tool[Any]] = []
        for definition in request.tools:
            handler = self._tool_handler(request, definition.tool_key)
            tools.append(
                Tool.from_schema(
                    handler,
                    name=definition.tool_key,
                    description=definition.description,
                    json_schema=definition.input_schema,
                    sequential=True,
                )
            )
        return tools

    def _tool_handler(
        self, request: AgenticExecutionRequest, tool_key: str
    ) -> Callable[..., Any]:
        def invoke(**arguments: Any) -> Any:
            if self._tool_invoker is None:
                raise RuntimeError("ALOS tool invoker is unavailable")
            return self._tool_invoker.invoke(request.context, tool_key, arguments)

        return invoke


def _terminal_error(
    request: AgenticExecutionRequest,
    status: ExecutionStatus,
    error_code: str,
    reason: str,
    started: float,
) -> AgenticExecutionResult:
    elapsed_ms = _elapsed_milliseconds(started)
    return AgenticExecutionResult(
        run_id=request.context.run_id,
        correlation_id=request.context.correlation_id,
        status=status,
        usage=CumulativeUsage(total_latency_milliseconds=elapsed_ms),
        steps=(
            AgenticStep(
                sequence=1,
                step_type=StepType.FINAL,
                status=status,
                duration_milliseconds=elapsed_ms,
                error_code=error_code,
            ),
        ),
        error_code=error_code,
        reason=reason,
    )


def _elapsed_milliseconds(started: float) -> int:
    return max(0, int((monotonic() - started) * 1_000))
