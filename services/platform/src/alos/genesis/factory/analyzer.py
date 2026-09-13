"""Natural-language requirement understanding through the governed engine."""

from __future__ import annotations

from alos.genesis.factory.models import RequirementUnderstanding
from alos.runtime.agentic import (
    AgenticExecutionEngine,
    AgenticExecutionRequest,
    ExecutionContext,
    ExecutionLimits,
    ExecutionStatus,
)


class RequirementAnalysisError(RuntimeError):
    """Requirement analysis failed without producing trusted structured facts."""


_ANALYSIS_INSTRUCTIONS = """Analyze the supplied business requirement semantically.
Extract objective, trigger, reusable capabilities, data, outputs, deterministic constraints,
material actions, evidence needs, ambiguity, and whether reasoning, research, validation, or
human judgment is required. Do not choose an implementation type. Do not invent company policy,
tools, credentials, data sources, thresholds, or approvals. Return only the required schema.
"""


class RequirementAnalyzer:
    def __init__(self, engine: AgenticExecutionEngine) -> None:
        self._engine = engine

    def analyze(
        self,
        requirement: str,
        *,
        context: ExecutionContext,
        limits: ExecutionLimits,
    ) -> RequirementUnderstanding:
        normalized = requirement.strip()
        if len(normalized) < 10:
            raise RequirementAnalysisError("requirement is too short to analyze safely")
        result = self._engine.execute(
            AgenticExecutionRequest(
                context=context,
                instructions=_ANALYSIS_INSTRUCTIONS,
                input_text=normalized,
                output_schema=RequirementUnderstanding.model_json_schema(),
                limits=limits,
            )
        )
        if result.status != ExecutionStatus.SUCCEEDED or result.output is None:
            raise RequirementAnalysisError(result.error_code or "REQUIREMENT_ANALYSIS_FAILED")
        try:
            return RequirementUnderstanding.model_validate(result.output)
        except ValueError as error:
            raise RequirementAnalysisError("requirement analysis output is invalid") from error
