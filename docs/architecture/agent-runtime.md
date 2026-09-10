# Agent Runtime

The shared `AgentRuntime` facade coordinates:

- contract loading and lifecycle checks;
- budget and usage controls;
- ModelGateway and ToolExecutor boundaries;
- persistent cancellation;
- tenant scope;
- Agent Run persistence and audit.

Agents do not get direct database, credential, filesystem, provider SDK, or
uncontrolled HTTP access.
