# Dokumentasi teknis ALOS

Dokumentasi ini adalah source of truth teknis untuk tim yang mengembangkan dan
mengoperasikan ALOS/GENESIS. Klaim status memakai tiga label:

- **CURRENT IMPLEMENTATION** — dapat ditunjuk ke kode, schema, atau test pada
  branch `epic/genesis-agent-factory`.
- **TARGET ARCHITECTURE** — arah kanonik yang belum tentu selesai diterapkan.
- **HISTORICAL / MVP1** — bukti lama yang dipertahankan untuk traceability,
  bukan petunjuk implementasi aktif.

## Urutan baca kanonik

1. [System overview](architecture/system-overview.md)
2. [GENESIS Capability/Agent Factory](architecture/genesis-agent-factory.md)
3. [Agent Runtime](architecture/agent-runtime.md)
4. [Governance model](governance/governance-model.md)
5. [Roles and access](governance/roles-and-access.md)
6. [Agent lifecycle](governance/agent-lifecycle.md)
7. [Team ownership](development/team-ownership.md)
8. [Architecture change policy](development/architecture-change-policy.md)
9. [Branch strategy](development/branch-strategy.md)

## Status ringkas

| Area | Status | Batas penting |
| --- | --- | --- |
| ALOS platform | CURRENT IMPLEMENTATION | Next.js, FastAPI, PostgreSQL, job worker/scheduler, audit, registry, governance, dan runtime tersedia |
| ARA workspace | CURRENT + TARGET | Presentation tersedia; integrasi produksi penuh dengan backend masih target |
| Factory analysis/resolution | CURRENT + TARGET | Resolver aktif memilih `AGENT`, `SKILL`, `WORKFLOW`, `RULE`, `VALIDATOR`, `REPORT`, `HUMAN_TASK`, `SCHEDULE`, `EVENT_HANDLER`, atau `COMPOSITE`; connector/tool requirement sudah ada pada enum/dependency model tetapi belum dipilih sebagai implementation type |
| Generic capability release | TARGET ARCHITECTURE | Lifecycle release branch ini baru end-to-end untuk proposal yang memuat Agent Contract |
| Governance IT → Director | TARGET ARCHITECTURE | Backend release saat ini masih memakai duty/reviewer legacy untuk compatibility |
| Shared Agent Runtime | CURRENT IMPLEMENTATION | Active-version, test-mode draft, budget, scope, permission, tool, evidence, audit, kill, dan cancellation controls tersedia |
| Explicit resume | TARGET ARCHITECTURE | Suspend, clear kill switch, dan rollback ada; transition `RESUME` belum ada |
| Deployment | CURRENT IMPLEMENTATION | Local Compose, staging Compose, production Compose, dan native production artifacts tersedia; pilih satu mode secara eksplisit |

## Index

- [Architecture](architecture/README.md)
- [Governance](governance/README.md)
- [Development](development/README.md)
- [Operations](operations/README.md)
- [Security](security/README.md)
- [Product context](product/ALOS_OPERATING_MODEL.md)
- [Historical MVP1 archive](archive/2026-mvp1/README.md)

Runbook dan laporan archive tidak boleh dipakai untuk menyatakan readiness saat
ini tanpa evidence baru yang terikat environment, commit, actor, dan waktu.
