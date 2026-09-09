"""Narrow dependency contracts available to agentic execution."""

from __future__ import annotations

from typing import Any, Protocol

from alos.runtime.agentic.output import ExecutionContext


class AgenticToolInvoker(Protocol):
    """Invoke a named tool through an ALOS-controlled adapter."""

    def invoke(
        self,
        context: ExecutionContext,
        tool_key: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Return a safe tool result or raise a controlled denial."""
