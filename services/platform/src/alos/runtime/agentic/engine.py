"""Framework-neutral execution engine boundary owned by ALOS.

Code outside :mod:`alos.runtime.agentic` depends on this protocol, never on a
specific agent framework.  Implementations must route models and tools through
the authoritative ALOS gateways and return cumulative, auditable accounting.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable
from uuid import UUID

from alos.runtime.agentic.output import AgenticExecutionRequest, AgenticExecutionResult


@runtime_checkable
class AgenticExecutionEngine(Protocol):
    """Execute and cancel a bounded agentic run.

    ``execute`` is synchronous to match the existing ALOS runtime and gateway
    contracts.  An implementation may manage asynchronous provider SDKs behind
    this boundary, but that detail must not leak into callers.
    """

    def execute(self, request: AgenticExecutionRequest) -> AgenticExecutionResult:
        """Execute one governed request or return a controlled terminal result."""

    def cancel(self, run_id: UUID) -> bool:
        """Request cancellation; return whether a live run accepted the request."""
