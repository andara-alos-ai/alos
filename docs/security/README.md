# Security

Security model kanonik berada pada:

- [Governance model](../governance/governance-model.md)
- [Roles and access](../governance/roles-and-access.md)
- [Agent lifecycle](../governance/agent-lifecycle.md)
- [Shared Agent Runtime](../architecture/agent-runtime.md)

Prinsip utama: backend adalah enforcement authority; LLM dan UI tidak
menentukan RBAC, scope, permission, lifecycle, approval, release, budget,
kill/rollback, atau audit. Baseline security MVP1 lama dipertahankan hanya di
[archive](../archive/2026-mvp1/GENESIS_MVP1_SECURITY_BASELINE.md).
