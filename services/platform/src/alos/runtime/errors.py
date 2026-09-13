"""Runtime-specific exception types."""


class AgentRuntimeError(RuntimeError):
    """A safe, deterministic runtime failure."""


class AgentRuntimeBlocked(AgentRuntimeError):
    """The runtime refused a run before contacting the provider."""


class InputSchemaError(AgentRuntimeError):
    """The supplied fixture does not match the Contract input schema."""


class OutputSchemaError(AgentRuntimeError):
    """The provider output does not match the Contract output schema."""
