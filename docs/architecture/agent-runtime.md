# Shared Agent Runtime

Shared `AgentRuntime` adalah satu execution boundary untuk seluruh logical
Agent. Agent/sub-agent tidak memiliki process, database, credential, atau
provider connection tersendiri.

## CURRENT IMPLEMENTATION

```text
Agent Run request
→ authenticate + organization/workspace/tenant scope
→ select exact Agent Version
→ lifecycle + kill-switch check
→ input schema + classification + source/evidence check
→ permission policy + tool allowlist
→ reserve budget/limits
→ ModelGateway and/or ToolExecutor
→ output validation
→ usage, evidence, run status, audit
```

Runtime mendukung dua mode yang harus dibedakan:

- `LIVE` hanya memilih `active_version_id` dengan lifecycle `ACTIVE`;
- `TEST` dapat menargetkan exact version `DRAFT`.

Test-mode tidak menjadikan version active. Runtime tetap menyimpan Agent Run
agar evaluator dapat mengikat evidence ke execution aktual.

Factory tenant scope harus sama dengan scope run. Tenant-scoped tool execution
ditolak bila resource yang dipakai belum tenant-aware. Organization dan
workspace juga selalu divalidasi.

## ModelGateway

Adapter runtime yang tersedia hanya:

- OpenAI untuk environment yang mengizinkannya;
- Gemini untuk `local`/`test`.

Production hanya menerima `disabled` atau OpenAI. Nilai konfigurasi provider
lain tidak berarti adapter tersedia. Contract memilih route `light`,
`standard`, atau `critical`; mapping ke model mentah hanya berasal dari
configuration backend.

## ToolExecutor

Tool call harus typed, registered, approved, berada dalam Agent Contract
allowlist, dan memiliki permission policy `ALLOW` + `APPROVED` untuk exact
Agent Version. ToolExecutor juga mengecek actor scope dan input schema. Agent
tidak dapat memanggil database, credential, filesystem, SDK provider, atau HTTP
bebas secara langsung.

## Cancellation dan emergency control

Cancellation persisten memakai `CANCEL_REQUESTED` dan `CANCELLED`; engine
melakukan polling terhadap state backend. Kill switch bersifat deny-first,
mengosongkan active pointer, dan memblokir run berikutnya. Suspend tidak
menghapus contract, version, evidence, atau audit.

## TARGET ARCHITECTURE

Capability non-Agent harus memakai execution path yang sesuai tanpa membuat
security boundary baru. Semua path tetap membutuhkan exact version, scope,
policy, evidence, audit, serta kill/rollback semantics yang konsisten.

## Runtime invariants

- `LIVE` hanya untuk exact active version; `TEST` bukan activation.
- Release tidak otomatis menjadi Active.
- Tool, permission, model, dan budget tidak dapat dipilih bebas oleh UI/model.
- Output LLM adalah kandidat sampai schema dan policy lulus.
- Clear kill switch tidak otomatis resume atau activate.
- Rollback hanya ke version berbeda dari contract yang sama yang pernah
  released; bukan ke draft.
