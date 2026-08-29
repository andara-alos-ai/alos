from collections.abc import Callable, Mapping

from alos.agents.runtime.models import (
    AgentExecutionPlan,
    CapabilityDispatchResult,
    CapabilityHandlerOutput,
)

CapabilityHandler = Callable[
    [AgentExecutionPlan, Mapping[str, object]], CapabilityHandlerOutput
]


class CapabilityHandlerError(RuntimeError):
    """Raised when capability handler registration or dispatch is invalid."""


class CapabilityHandlerRegistry:
    """Explicit capability-to-handler mapping with no agent-specific branching."""

    def __init__(self) -> None:
        self._handlers: dict[str, tuple[str, CapabilityHandler]] = {}

    def register(
        self, capability: str, handler_id: str, handler: CapabilityHandler
    ) -> None:
        if capability in self._handlers:
            raise CapabilityHandlerError(f"Handler capability sudah terdaftar: {capability}")
        if not handler_id.strip() or handler_id != handler_id.strip():
            raise CapabilityHandlerError("handler_id tidak boleh kosong atau memiliki spasi tepi")
        self._handlers[capability] = (handler_id, handler)

    def dispatch(
        self,
        plan: AgentExecutionPlan,
        input_payload: Mapping[str, object],
    ) -> CapabilityDispatchResult:
        registration = self._handlers.get(plan.capability)
        if registration is None:
            raise CapabilityHandlerError(
                f"Handler belum terdaftar untuk capability: {plan.capability}"
            )
        handler_id, handler = registration
        output = handler(plan, input_payload)
        return CapabilityDispatchResult.from_handler(plan, handler_id, output)
