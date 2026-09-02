# GENESIS MVP1 — Rencana Eksekusi Lima Hari

## Product boundary

**Decision ID:** `ALOS-GEN-MVP1-001`
**Status:** scope locked for controlled internal MVP1

Genesis adalah AI Executive Operating Layer ALOS. Ia menerima requirement,
menganalisis sumber, membuat draft Blueprint/Agent Contract, menjalankan
validasi dan test, lalu mengajukan release untuk human review. Genesis bukan
divisi dan tidak memiliki authority final. Satu shared Agent Runtime menjalankan
logical agent lintas enam divisi: Finance, Sales & Marketing, Property, HR,
Legal, dan IT.

MVP1 hanya menggunakan data sintetis dan staging. Tidak ada auto-approval,
auto-activation berisiko, perubahan production, tool tanpa review, atau bypass
permission/audit/rollback.

## Hari 1 — Foundation

1. Scope lock, decision log, dan security boundary.
2. Satu PostgreSQL database baseline dengan identity, workspace, source,
   Genesis history, Agent Contract/Registry, release, runtime, audit, cost,
   kill switch, dan rollback schema.
3. API health/readiness, configuration local/staging, dan frontend shell.
4. Lint, type-check, unit test, fresh migration PostgreSQL, secret scan, dan
   smoke test.

**Exit gate:** database disposable dapat dimigrasikan dari nol, `/health`
merespons, dan tidak ada provider/production secret yang aktif.

## Hari 2 — Genesis design-time

Source Registry, version/hash, citation, conversation history, natural-language
requirement, Blueprint, Agent Contract `DRAFT`, serta audit creation.

## Hari 3 — Runtime guardrail

Model Gateway (OpenAI primary, Claude fallback, Ollama local/test only),
versioned model/prompt/tool/permission policy, cost ledger, tool allowlist, dan
shared runtime read-only.

## Hari 4 — Lifecycle

Validation, test runner, diff, human business/technical review, staging,
release, explicit activation, suspend, kill switch, dan rollback. Buktikan
satu alur `CREATE → RUN` untuk Daily Brief Agent.

## Hari 5 — Validation and decision

Genesis membuat Daily Brief, Evidence Checker, dan Permit/Overdue Monitor
melalui contract yang sama. Jalankan UAT enam divisi, test positif/negatif,
provider failure, cost cap, malformed output, tool/permission denial,
kill switch, rollback, backup/restore sintetis, lalu tetapkan `GO`, `HOLD`,
atau `NO-GO`.

## Definition of Done MVP1

- Satu shared runtime dan satu database; tidak ada service/database per agent.
- Requirement sampai staging/release/run berjalan dengan human gate dan audit.
- Semua agent memiliki contract, owner, risk, permission, tools, evidence,
  forbidden actions, version, test result, dan rollback target.
- Tidak ada rule deterministik (permission, status, approval, deadline,
  arithmetic, audit) yang diserahkan kepada LLM.
- Semua quality gate Hari 5 lulus atau keputusan `HOLD` memiliki evidence dan
  known limitation eksplisit.
