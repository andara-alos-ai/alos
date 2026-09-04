# ALOS — Domain dan Lifecycle

## Bounded context universal

| Context | Entity utama | Fungsi |
| --- | --- | --- |
| Identity | Organization, User, Role, Division, Workspace | scope dan akuntabilitas manusia |
| Sources | Source, SourceVersion, Citation, Evidence | provenance, status actual/forecast, hak baca |
| Genesis | Conversation, Requirement, ResearchMission, Finding, Opportunity, Artifact | dari arahan manusia menjadi proposal yang dapat ditelusuri |
| Work | WorkPlan, WorkItem, Schedule, Assignment, Dependency, Escalation | pekerjaan ad-hoc, harian, mingguan, bulanan, event-driven |
| Agents | AgentContract, AgentVersion, AgentRegistry, PromptConfig, ToolManifest | agent/sub-agent generik dan policy-nya |
| Governance | ValidationResult, TestRun, Review, Approval, ReleaseProposal, KillSwitch, RollbackRecord | human gate dan perubahan terkendali |
| Runtime | AgentRun, ToolCall, RunOutput | satu executor bagi semua logical agent/work item |
| Observability | UsageLedger, CostLimit, Trace, Alert | token, provider, model, latency, cost, error |
| Audit | AuditEvent | immutable record untuk semua command dan transition |

Tidak ada context/tabel khusus untuk nama agent, proyek, atau divisi tertentu.
Tipe artifact dan policy membedakan kemampuan; scope workspace/division dan
permission membatasi pelaksanaannya.

## Model task dan jadwal

`WorkItem` adalah unit kerja universal. Ia dapat dihasilkan Genesis dari
Research Mission atau dibuat manusia secara langsung.

```text
WorkPlan
  ├─ WorkItem (one-off / event / recurring)
  │   ├─ Assignment: human, agent contract, atau queue
  │   ├─ Schedule: daily, weekly, monthly, cron-safe, atau event trigger
  │   ├─ Dependency: work item lain / approval / evidence requirement
  │   ├─ Run: eksekusi shared runtime
  │   └─ Evidence + result artifact + audit events
  └─ Escalation rule: deadline/SLA/risk/blocked
```

Genesis dapat membuat draft WorkPlan dan WorkItem. Scheduler hanya
mengaktifkan item yang telah lulus permission, lifecycle, budget, dependency,
dan approval. Jadwal tidak pernah memberi authority baru.

## Artifact universal

`Artifact` minimal menyimpan: type, title, version, content/schema digest,
source citations, evidence status, owner, risk level, producer, review state,
dan parent artifact.

Jenis awal: `RESEARCH_BRIEF`, `FINDING`, `OPPORTUNITY`, `FEASIBILITY`,
`DOCUMENT`, `WORKFLOW`, `TASK_PLAN`, `WEBSITE_PREVIEW`, `BLUEPRINT`,
`AGENT_CONTRACT`, `TEST_PLAN`, `DIFF`, dan `RELEASE_PROPOSAL`.

Artifact yang akan memiliki side effect tidak langsung dieksekusi: ia menjadi
proposal dan masuk lifecycle governance. `WEBSITE_PREVIEW` hanya sandbox/staging
sampai approval release; ia bukan publish otomatis.

## Agent Contract minimum

Setiap agent version wajib memiliki:

```text
identity: key, name, parent, owner, workspace/division scope
purpose: objective, input schema, output schema, KPI, evidence requirement
behavior: prompt config version, model policy, allowed tools, forbidden actions
control: risk level, permission policy, cost/time cap, approval requirement
delivery: test results, diff, release target, rollback target, lifecycle status
```

Sub-agent hanya dapat menyempitkan scope, tool, permission, classification,
budget, dan risk parent. Ia tidak boleh memperluasnya tanpa contract/version
baru dan human review.

## Lifecycle deterministik

```text
Requirement
  → ANALYZED → DRAFT → VALIDATED → TESTED → IN_REVIEW
  → APPROVED → STAGED → RELEASED → ACTIVE
                                 ↘ SUSPENDED → ROLLED_BACK / RETIRED
```

- Genesis boleh membuat `ANALYZED`, `DRAFT`, serta hasil validation/test.
- Hanya reviewer yang berwenang boleh membawa proposal ke `APPROVED`.
- Hanya release authority dapat `RELEASED`; activation memerlukan policy check
  terpisah.
- Kill switch dapat memindahkan run aktif ke `KILLED` dan menahan run baru
  secara segera; ia tidak menghapus evidence.
- Rollback selalu memilih version released sebelumnya, mencatat reason/actor,
  dan tidak menimpa contract snapshot.

## Status implementasi local saat ini

H2–H4 telah membuktikan `DRAFT → TESTED → IN_REVIEW → APPROVED → RELEASED →
ACTIVE → SUSPENDED → ROLLED_BACK` di PostgreSQL sementara dengan evidence
append-only, maker/checker/reviewer/approver terpisah, serta kill switch.
Shared Runtime local memprioritaskan fixture `DRAFT` untuk release testing dan
menjalankan versi `ACTIVE` pada Agent Registry bila tidak ada draft tertunda.
Scheduler dan execution active pada staging tetap menunggu provider policy dan
identity reviewer produksi.

## Vertical slice property R&D untuk MVP1

1. Dirut memasukkan requirement contoh: mencari peluang property berdasarkan
   sumber sintetis yang terdaftar.
2. Genesis membuat `ResearchMission`, membaca version source yang diizinkan,
   lalu menghasilkan cited `RESEARCH_BRIEF` dan `TASK_PLAN`.
3. Genesis mengusulkan satu Agent Contract low-risk/read-only untuk menjalankan
   pekerjaan tersebut; output harus strict schema.
4. Validator, test runner, dan reviewer memeriksa proposal sebelum staging.
5. Runtime menjalankan version yang active, mencatat evidence/cost/audit, dan
   menghormati schedule, tool denial, kill switch, serta rollback.

Daily Brief, Evidence Checker, dan Permit/Overdue Monitor digunakan pada
vertical slice yang sama untuk membuktikan pattern universal tersebut.
