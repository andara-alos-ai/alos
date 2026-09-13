# Security model

Status: **CURRENT POLICY**.

Backend adalah enforcement authority. UI membantu workflow tetapi tidak memberi
permission; LLM menghasilkan kandidat tetapi bukan permission engine atau approver.
Identity, RBAC, organization/workspace/tenant, optional division/project scope, data
classification, lifecycle, version, tool allowlist, budget, dan output schema divalidasi
server-side.

Model egress hanya melalui ModelGateway dan Tool execution hanya melalui ToolExecutor.
PydanticAI tidak boleh mengakses database, SDK provider, MCP, HTTP, shell, filesystem,
atau credential secara langsung. Delegation harus memenuhi child scope/permission/tool
subset dan tidak boleh melebihi sisa budget parent.

Material change wajib menghasilkan evidence yang dapat diaudit, independent human
review, exact-version decision, release, dan activation terpisah. Incident tidak boleh
diselesaikan dengan melemahkan policy; gunakan disable, suspend, kill switch, atau
rollback yang tercatat.
