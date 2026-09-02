# ALOS — Genesis MVP1 Build and Release Plan

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

Agent Registry mendukung tree generic dengan `parent_agent_id`: root/Core Agent
dapat memiliki Sub-Agent dan Sub-Sub-Agent. Ini bukan taxonomy tetap, struktur
organisasi, service, atau database baru. Child hanya boleh mempersempit policy
parent; perluasan tool, permission, risk, atau budget harus menjadi proposal
baru untuk human review.

## Disiplin release

VPS dan OpenAI adalah release environment, bukan tempat pertama untuk
menemukan defect. Semua integrasi eksternal harus lulus versi lokalnya dengan
data sintetis, configuration explicit, test otomatis, dan commit SHA yang
immutable. Deployment tidak boleh berasal dari working tree yang belum bersih.

OpenAI smoke test pertama hanya memakai prompt sintetis non-sensitif,
server-side secret, `store=false`, low hard cost cap, timeout, correlation ID,
dan tanpa side effect. Kegagalan gate berarti `HOLD`, bukan bypass control.

## H0 — Build acceleration sebelum clock resmi lima hari

1. Pastikan foundation modular-monolith, satu database, baseline migration,
   health/readiness, auth/RBAC skeleton, dan frontend shell selalu lulus lokal.
2. Pastikan Compose staging, container image, fresh migration, service
   readiness, synthetic fixtures, placeholder-secret rejection, dan backup/
   restore script dapat diverifikasi tanpa credential vendor.
3. Definisikan test double Model Gateway serta contract untuk schema,
   lifecycle, permission, tool denial, cost cap, audit, dan rollback sebelum
   provider riil dipanggil.
4. Jalankan lint, type-check, unit test, disposable PostgreSQL migration test,
   container smoke test, secret scan, dan `git diff --check`; commit hanya
   checkpoint yang sudah terverifikasi.

**Exit gate H0:** kandidat dari commit bersih dapat berjalan dalam container
lokal, memakai data sintetis dan LLM disabled. Tidak ada secret eksternal yang
dibutuhkan untuk membuktikan foundation.

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

## Quality gate sebelum VPS/OpenAI

| Failure class | Gate sebelum external release | Evidence |
| --- | --- | --- |
| Configuration/secret | Compose config dan preflight placeholder rejection | output preflight ter-redaksi |
| Migration/data | fresh migration dan restore drill | migration/restore log |
| Provider/API | fake-provider contract test lalu low-cap synthetic smoke | correlation ID, token, latency, cost |
| Runtime safety | schema, permission, tool denial, idempotency, budget test | test report dan audit |
| Deployment | immutable image, health/readiness, proxy smoke | image SHA dan health evidence |
| Recovery | suspend, kill switch, release rollback, backup restore | UAT evidence |
