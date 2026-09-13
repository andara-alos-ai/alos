# Domain Model — Hari 1

| Context | Entity inti | Tujuan |
| --- | --- | --- |
| Identity | Organization, Division, User, RoleAssignment | Human actor dan enam scope divisi |
| Workspace | Workspace, Membership | Context proyek/ruang kerja untuk setiap request dan run |
| Sources | Source, SourceVersion | Provenance, permission read-only, hash, dan locator citation |
| Genesis | Conversation, Message, Artifact, ChangeRequest | Requirement natural language sampai proposal perubahan |
| Agent Registry | AgentContract, AgentVersion, Registry | Logical agent universal dan parent optional tanpa hierarchy organisasi |
| Governance | Review, ReleaseProposal, CostLimit, KillSwitch, RollbackRecord | Human gate, lifecycle, cost control, dan recovery |
| Runtime | AgentRun, ToolCall | Eksekusi shared runtime dengan correlation ID |
| Observability | UsageLedger | Provider, model, token, latency, serta biaya |
| Audit | AuditEvent | Jejak append-only untuk human dan system actor Genesis |

Genesis dicatat sebagai `SYSTEM/GENESIS`. Ia tidak dapat menjadi user manusia,
role manusia, atau division code. Tidak ada table khusus per agent atau divisi;
semua contract/version/run memakai registry dan runtime yang sama.
