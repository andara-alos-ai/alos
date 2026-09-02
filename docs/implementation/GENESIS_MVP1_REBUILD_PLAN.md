# GENESIS MVP1 — Rencana Rebuild Terkendali

**Status:** IMPLEMENTATION IN PROGRESS — persetujuan diterima, branch `develop` aktif
**Tanggal audit:** 2 September 2026  
**Baseline desain:** `C:\Users\User\Downloads\GENESIS_MVP1_Timeline_1_Minggu_Breakdown_Harian_v8.3_02-09-2026.docx` (berkas lampiran yang tersedia)  
**Otoritas:** permintaan pengguna pada task ini selalu mengalahkan isi baseline bila ada perbedaan.

## 1. Keputusan Arsitektur

ALOS MVP1 adalah **satu aplikasi internal berbentuk modular monolith**, dengan:

- satu frontend internal;
- satu API/backend dan satu database PostgreSQL;
- satu Genesis sebagai design-time Agent Factory;
- satu shared Agent Runtime untuk semua logical agent;
- satu Model Gateway untuk seluruh provider LLM;
- enam konteks divisi: Keuangan, Sales & Marketing, Property, HR, Legal, dan IT.

Direktur Utama dan AI Executive Operating Layer adalah lapisan lintas divisi. Keduanya tidak menjadi divisi atau aplikasi tambahan. Tidak ada target 18 aplikasi, 18 database, 18 microservice, atau service per agent.

`Core/Sub-Agent/Sub-Sub-Agent` tidak lagi menjadi taxonomy operasional permanen. Bila relasi induk diperlukan, ia direpresentasikan sebagai `parent_agent_version_id` opsional pada Agent Contract. Runtime, registry, test, approval, release, suspend, kill switch, dan rollback tetap menggunakan mekanisme yang sama untuk setiap agent.

## 2. Hasil Audit Repository (Tahap 0)

### 2.1 Snapshot yang diamati

- Branch saat audit: `main` pada commit `b3559d0`.
- Worktree **tidak bersih**: 109 file termodifikasi dan sejumlah file baru; diff berisi sekitar 9.802 penambahan serta 1.569 penghapusan. Semua perubahan tersebut diperlakukan sebagai milik pengguna dan tidak akan dihapus, di-reset, di-stash, atau ditimpa.
- Terdapat 42 migrasi SQL, 168 file Python (sekitar 34.509 baris), 49 file TypeScript/TSX, 36 definisi JSON, dan UI per divisi yang cukup besar.
- Pemeriksaan baseline yang sudah dijalankan berhasil: Python test suite lulus (tes PostgreSQL yang memang ditandai `skip` dilewati); Vitest lulus 6 file / 23 test; ESLint dan TypeScript type-check lulus; `git diff --check` tidak menemukan error whitespace.
- `.env` tidak dilacak Git dan `.env.example` saja yang dilacak. Audit pola secret pada file terlacak tidak menemukan key privat/API key nyata. Nilai secret di `.env` tidak dibaca atau ditampilkan.

### 2.2 Kemampuan yang sudah ada dan layak dimanfaatkan

| Area | Bukti audit | Keputusan |
| --- | --- | --- |
| Single application | Next.js + FastAPI sudah berada dalam satu monorepo | Pertahankan, sederhanakan permukaan UI/API |
| Shared Runtime | `alos.agents.runtime` membaca contract/capability/tool registry | Pertahankan dan kecilkan ke runtime generik |
| Genesis pipeline | source → proposal → test → review → staging → release package tersedia | Pertahankan konsepnya, perbaiki materialisasi contract dan lifecycle |
| Security | auth/RBAC, CSRF cookie, request limit, rate limit, OIDC, secret settings, audit integrity tersedia | Pertahankan sebagai fondasi dan uji ulang |
| Model boundary | OpenAI, Anthropic, local adapter dan schema validation sudah melalui `LLMGateway` | Pertahankan gateway, tambah model policy/fallback dan meter persisten |
| Audit/versioning | contract digest, release package immutable, Genesis history dan audit ledger tersedia | Pertahankan dan jadikan jalur wajib |
| Source metadata | source pack berversi, SHA-256, status/authority, allowed use tersedia | Pertahankan model lineage; tambahkan ingestion dan citation per artefak |
| Synthetic testing | fixtures, UAT dan test modules sudah tersedia | Pertahankan pola, ganti fixture yang terlalu domain-spesifik |

### 2.3 Gap terhadap GENESIS MVP1

| Prioritas | Gap | Dampak | Arah perbaikan |
| --- | --- | --- | --- |
| P0 | UI Genesis memiliki alur “instant activation” yang mencoba melakukan kedua review, staging, dan release secara otomatis. | Melanggar human approval dan separation of duties. | Hapus alur auto-approval dari UI; reviewer yang berbeda harus melakukan action eksplisit. |
| P0 | Agent Contract masih mewajibkan `CORE`, `SUB_AGENT`, atau `SUB_SUB_AGENT`, dan analysis fallback mengunci parent ke 18 agent lama. | Taxonomy lama tetap mempengaruhi agent baru. | Ganti dengan contract universal dan parent reference opsional; hapus ketergantungan runtime pada 18 ID. |
| P0 | Genesis release package tidak mematerialisasi version contract menjadi entri registry yang bisa langsung dirujuk runtime. | Jalur CREATE → RELEASE → RUN belum terbukti end-to-end. | Buat satu service transaction yang mencatat contract revision, release, activation, lalu runtime menjalankan revision aktif yang dipin. |
| P1 | Source registry saat ini berisi source pack JSON statis; ingestion file, extraction, comparison, finding, dan citation per artefak belum menjadi jalur vertikal tunggal. | Requirement source/document/version/gap/citation belum lengkap. | Tambah source ingestion berbasis metadata/hash, extraction record, citation locator, comparison dan finding minimal. |
| P1 | Gateway memilih satu provider per konfigurasi dan budget harian masih in-memory. | Tidak ada fallback policy yang dapat diaudit atau cap persisten per provider/model/agent. | Model policy: OpenAI primary, Claude fallback, Ollama test-only; catat token/cost/latency pada ledger persisten. |
| P1 | Lifecycle contract memakai `STAGED/RELEASED`, namun belum memiliki state `ACTIVE`, `SUSPENDED`, `KILL_SWITCHED`, dan `ROLLED_BACK` yang terpisah. | Status release dapat disalahartikan sebagai agent aktif. | Pisahkan design/release/activation lifecycle dan simpan rollback target. |
| P1 | Runtime memiliki banyak handler bisnis hard-coded dan migrasi/alur transaksi per divisi. | Scope MVP melebar, sulit dibuktikan sebagai engine generik. | Sisakan kernel runtime + tiga logical validation agent dan tool read-only generik. |
| P1 | UI berisi dashboard dan halaman operasional per divisi. | Mengalihkan delivery dari vertical slice Genesis. | Tahan/arsipkan UI legacy; MVP hanya perlu Genesis, registry, review, run, audit/cost. |
| P2 | Migrasi historis mencampur foundation, workflow bisnis, pilot, dan hardening. | Fresh bootstrap MVP sulit dibaca. | Jangan hapus migrasi historis; buat baseline baru yang additive/terdokumentasi setelah cleanup disetujui. |

## 3. Daftar Disposisi Awal dan Implementasi

Tidak ada file dalam daftar ini yang dihapus atau dipindahkan pada Tahap 0–1. “Hapus” berarti kandidat pembersihan aplikasi **setelah** persetujuan tertulis, branch baru, snapshot perubahan lokal, dan verifikasi bahwa tidak ada data produksi/credential di dalamnya.

### Dipertahankan

- `.git/`, seluruh riwayat Git, `.env`, `.env.example`, `.gitignore`, credential store, backup, skrip backup/restore, dan seluruh data non-sintetis.
- `apps/web/src/lib/session.ts`, `apps/web/src/lib/api.ts`, `apps/web/src/lib/identity.ts`, serta komponen session/shell yang masih dipakai setelah UI MVP disederhanakan.
- `services/platform/src/alos/security/`, `validation/`, `audit/`, `llm/`, dan bagian reusable dari `persistence/`.
- Kernel `services/platform/src/alos/agents/{contract,registry,runtime}/`, `genesis/`, `tools/`, dan `observability/`; seluruhnya akan direfactor, bukan dibuang secara membabi buta.
- `infra/database/001_foundation.sql` sampai `042_harden_genesis_history_actor_tenant_keys.sql` sebagai riwayat migrasi yang tidak boleh dimanipulasi.
- `infra/environments/`, `infra/docker/`, `infra/compose/`, `definitions/schemas/`, fixture sintetis, dan test harness yang masih relevan.

### Dipindahkan/diarsipkan (bukan dihapus)

- Dokumen taxonomy: `docs/agent-contracts/18_CORE_AGENT_REGISTRY.md`, dokumen GIIVEPRO/Master A–N, dan dokumen workflow lama dipindahkan ke `docs/archive/pre-genesis-mvp1/` dengan indeks provenance.
- Bukti UAT dan laporan audit lama disimpan sebagai evidence dengan tanggal, bukan diperlakukan sebagai spesifikasi current state.

### Pembersihan aplikasi yang sudah dieksekusi setelah persetujuan

- Route frontend legacy yang tidak mendukung vertical slice dihapus: `documents`, `executive`, `field`, `finance`, `governance`, `hr`, `legal`, `projects`, `property`, `risks`, `sales`, `system-health`, `uat`, `users`, `work-queue`, `workflows`, dan workspace division page.
- `apps/web/src/lib/catalog.ts` beserta test catalog lama dihapus; navigasi kini hanya Home, Genesis, Agents, dan Approvals.
- Halaman Genesis diganti menjadi draft-only. Ia hanya menyimpan conversation dan mengirim requirement; tidak ada lagi auto-review, auto-stage, auto-release, atau auto-activate dari frontend.
- Tidak ada `.git`, `.env`, credential, backup, data production, atau migrasi historis yang dihapus.
- Setelah instruksi eksplisit pengguna untuk menghapus artefak yang tidak diperlukan, seluruh `definitions/agents/core/**`, placeholder `sub`/`sub-sub`, dan placeholder package/test kosong dihapus. Snapshot `f725dea` tetap menjadi rollback sebelum cleanup ini.
- Registry runtime kini hanya menyimpan tiga tool read-only, tiga capability deterministik, dan tiga schema profile yang dipakai oleh validation agent. Handler runtime legacy dipangkas menjadi kernel tiga capability tersebut.

### Kandidat pembersihan lanjutan

- Dashboard dan route operasional yang tidak mendukung vertical slice MVP: `apps/web/src/app/{executive,finance,hr,legal,property,sales,work-queue,workflows,field,documents,projects,risks,uat,users,system-health}/` beserta feature module khususnya setelah screen pengganti tersedia.
- Workflow/domain implementation lama: `services/platform/src/alos/platform/{operations,dispatch,documents,readiness}/`, handler domain khusus di `services/platform/src/alos/agents/runtime/builtin_handlers.py`, dan module workflow/operasi khusus Finance, Sales, Property, HR, Legal, Executive.
- Definition workflow legacy: `definitions/workflows/{executive-brief,lead-to-reservation,payment-request,recruitment,site-evidence,permit-contract}/` dan capability/tool khususnya yang tidak dipakai tiga validation agent.
- Test dan fixture yang hanya memvalidasi workflow legacy setelah test pengganti MVP ada.

**Batas penting:** kandidat di atas beririsan dengan perubahan lokal pengguna saat ini. Tidak ada cleanup dapat dimulai sampai pengguna menyetujui daftar, menentukan bahwa perubahan lokal tersebut boleh dipindahkan/diarsipkan, dan branch kerja baru dibuat. Migrasi historis tidak termasuk kandidat penghapusan.

## 4. Struktur Folder Target yang Sederhana

Struktur ini adalah target akhir setelah pembersihan yang disetujui; implementasi dapat dilakukan bertahap tanpa menghapus riwayat database.

```text
apps/web/src/
  app/                 # login, genesis, agents, approvals, runs, settings
  components/          # shell dan komponen UI reusable
  lib/                 # API client, identity, session, format

services/platform/src/alos/
  api/                 # router tipis per bounded context
  identity/            # auth, user, role, division
  workspace/           # project/workspace context
  genesis/             # intake, source analysis, blueprint, diff, history
  agents/              # contract, registry, lifecycle, test runner
  runtime/             # shared dispatcher dan run control
  governance/          # permission, approval, policy, audit
  llm/                 # model gateway, routing, meter
  persistence/         # repositories dan migrations runner
  observability/       # health, telemetry, cost view

definitions/
  prompts/             # versioned prompt configuration
  tools/               # reviewed tool contracts
  policies/            # permission, risk, model policy
  fixtures/            # synthetic source and test data

infra/database/        # append-only migration history
tests/                 # contract, unit, integration, security, e2e
docs/                  # current design, runbook, audit, archived legacy
```

Tidak ada folder `services/<agent-name>` atau database per agent. Semua agent adalah record/contract/logical execution dalam satu runtime.

## 5. Domain Model dan Skema Database MVP

| Bounded context | Entitas minimum | Kontrol wajib |
| --- | --- | --- |
| Identity | `users`, `roles`, `role_assignments`, `divisions` | RBAC, division scope, separation of duties |
| Workspace | `workspaces`, `workspace_memberships` | organisasi/divisi/project context untuk setiap request/run |
| Sources | `sources`, `source_versions`, `extractions`, `citations`, `comparisons`, `findings` | hash, lineage, classifier, verification status, locator citation |
| Genesis history | `genesis_conversations`, `genesis_messages`, `genesis_artifacts`, `genesis_change_requests` | actor, source refs, prompt/model metadata, immutable history |
| Agent registry | `agent_contracts`, `agent_versions`, `agent_registry` | canonical digest, universal contract, current state pointer, parent optional |
| Configuration | `prompt_versions`, `model_policies`, `tool_contracts`, `permission_policies` | all versioned, reviewed, immutable after release |
| Testing | `test_cases`, `test_runs`, `test_evidence` | positive/negative results, expected vs actual, evidence link |
| Release/governance | `reviews`, `approvals`, `releases`, `activation_records`, `rollback_records` | maker/checker/approver separation, target version, explicit effect |
| Runtime | `agent_runs`, `tool_calls`, `usage_ledger`, `run_events` | correlation id, input/output reference, deterministic policy outcome |
| Audit/ops | `audit_events`, `kill_switches`, `cost_limits`, `health_checks` | append-only, actor, tenant/workspace, reason, timestamp |

Migrations yang ada tetap dipelihara. Perubahan skema baru bersifat additive dan setiap migrasi wajib lulus fresh migration test serta rollback/downgrade rehearsal pada database sintetis.

## 6. Agent Contract Universal

Setiap agent version menyimpan paling sedikit:

```yaml
agent_key: DAILY_BRIEF
version: 0.1.0
name: Daily Brief Agent
parent_agent_version_id: null           # opsional, tidak mengubah organisasi
division_scope: [FINANCE, SALES_MARKETING, PROPERTY, HR, LEGAL, IT]
purpose: ringkas tujuan dan batas kerja
input_schema: JSON Schema
output_schema: JSON Schema
source_requirements: [verified-source]
prompt_ref: genesis.daily-brief@0.1.0
model_policy_ref: standard-internal@0.1.0
allowed_tools: [source.read, evidence.read]
permission_policy_ref: read-only-internal@0.1.0
risk_level: LOW
owner_role: AI_EXECUTIVE
approval_policy: human-review-required
evidence_requirements: [citation-per-finding]
forbidden_actions: [write-production, self-approve, create-tool]
kpis: [test-pass-rate, citation-coverage, cost-per-run]
limits: {max_steps: 8, timeout_seconds: 30, token_cap: 1200}
rollback_target_version: null
```

Kontrak valid hanya bila semua reference versioned tersedia dan release tool/prompt/model/policy telah direview. LLM tidak menentukan izin, deadline, aritmetika, status transition, decision final, atau audit result.

## 7. Lifecycle Agent dan Genesis Pipeline

```text
source/specification
  -> analyze -> generate blueprint/contract -> validate -> test -> diff
  -> human business review -> human technical review -> staging
  -> release package -> explicit activation -> shared runtime run

DRAFT -> VALIDATED -> TESTED -> IN_REVIEW -> APPROVED -> STAGED -> RELEASED -> ACTIVE
                      |              |                       |          |
                    REJECTED <-------+                       |          +-> SUSPENDED
                                                              |                  |
                                                              +-> ROLLED_BACK <--+
                                                                         |
                                                                      RETIRED
```

Aturan deterministik:

1. Genesis hanya menghasilkan draft dan tidak dapat approve, stage, release, atau activate permintaannya sendiri.
2. Business reviewer, technical reviewer, stager, dan activator mengikuti separation-of-duties untuk perubahan material.
3. `RELEASED` adalah paket immutable; `ACTIVE` adalah pointer runtime eksplisit terhadap version yang telah dirilis.
4. Risk medium/high/critical memerlukan approval policy yang lebih ketat; risk material tidak pernah auto-active.
5. `SUSPENDED` menolak run baru. Kill switch menghentikan dispatch sebelum tool call berikutnya dan mencatat audit event. Rollback memindahkan pointer ke release terdahulu tanpa menghapus run/history.

## 8. Security Boundary

- Authentication dan authorization dilakukan server-side dengan user, role, division, dan workspace scope.
- Secret hanya melalui environment atau vault; tidak pernah dari frontend, Agent Contract payload, prompt, commit, atau log.
- Model Gateway adalah satu-satunya jalan ke LLM: OpenAI primary, Claude fallback yang eksplisit, Ollama local hanya pada environment test.
- Source classification, masking, provider allowlist, output JSON Schema, prompt injection defense, request limit, timeout/retry bounded, dan content provenance diperiksa sebelum/selama run.
- Tool registry menerapkan allowlist, capability/purpose binding, read/write/effect classification, timeout, idempotency, permission scope, dan human approval untuk side effect.
- Aritmetika, status transition, approval, deadline, permission decision, cost cap, audit append, kill switch, dan rollback dijalankan secara deterministik di backend.
- Production tidak dapat berubah melalui Genesis; staging memakai source/data sanitized. Tidak ada source pack atau agent release yang membuat production change secara langsung.

## 9. Three Validation Agents dan Enam Konteks Divisi

Ketiga logical agent dibuat melalui Genesis dengan Agent Contract dan lifecycle yang sama:

1. **Daily Brief Agent** — merangkum kondisi/alert dari source sintetis, mencantumkan citation dan menyatakan informasi yang tidak didukung source.
2. **Evidence Checker Agent** — memeriksa kelengkapan, hash/metadata, status verifikasi, dan citation evidence tanpa menyetujui transaksi/kasus.
3. **Permit/Overdue Monitor Agent** — menghitung due date/status secara deterministik dan membuat alert/read-only draft, tanpa mengubah data master.

Masing-masing diuji pada six division contexts melalui workspace scope. Direktur Utama dan AI Executive diuji sebagai role/layer lintas divisi, bukan test division tambahan.

## 10. Definition of Done MVP1

MVP1 dinyatakan siap untuk controlled internal pilot jika seluruh syarat ini lulus:

1. User berwenang dapat mengirim requirement natural language dengan workspace/source context.
2. Genesis menyimpan conversation, source version/hash, extraction/citation, analysis, finding/gap/conflict, blueprint, contract, diff, dan proposal release.
3. Satu Agent Contract universal terbentuk, tervalidasi, dan versi/ketergantungan config-nya immutable setelah release.
4. Setiap contract melewati schema, tool, permission, risk, owner, KPI, forbidden action, policy, positive/negative test validation.
5. Human review dan approval terpisah dari maker; tidak ada self-approval atau auto-activation pada risk material.
6. Agent lulus jalur CREATE → VALIDATE → TEST → REVIEW → STAGE → RELEASE → ACTIVATE → RUN pada shared runtime.
7. Tiga validation agent dibuat melalui Genesis, bukan code path bespoke.
8. Tool denial, scope denial, malformed output, provider failure, cost cap, test failure, suspend, kill switch, and rollback menghasilkan state/audit evidence yang benar.
9. Usage ledger mencatat provider, model, input token, output token, latency, estimated/actual cost dan correlation id per run; alert di 70/90% dan hard stop/downgrade policy pada 100% bekerja.
10. Audit trail append-only mencakup perubahan material, approval, policy/tool/config version, activation, run, tool denial, kill, dan rollback.
11. Lint, type-check, unit, contract, integration, migration fresh-test, security scan, smoke test, dan backup/restore test sintetis lulus.
12. Known limitations, runbook, hasil UAT enam divisi, dan keputusan GO/HOLD/NO-GO terdokumentasi.

## 11. Urutan Implementasi Lima Hari

| Hari | Fokus vertikal | Gate |
| --- | --- | --- |
| H1 | Freeze scope, branch, target schema, universal contract, lifecycle, auth/workspace, audit | Migration dan API skeleton lulus |
| H2 | Source/version/citation minimum, Genesis requirement → blueprint/contract DRAFT, registry | Satu DRAFT + version + audit dibuat tanpa edit DB |
| H3 | Model Gateway OpenAI primary, meter persisten, shared runtime, read-only tool/permission guardrail | Contract yang dirilis dapat run pada fixture dan unauthorized tool denied |
| H4 | Test runner, review/approval SoD, stage/release/activation, suspend/kill/rollback | Satu agent melewati CREATE sampai RUN tanpa auto-approve |
| H5 | Tiga validation agent, six-division UAT, negative tests, migration/security/smoke/restore test, report | GO/HOLD/NO-GO controlled internal pilot |

## 12. Rencana Perubahan Besar Setelah Persetujuan

Sebelum setiap batch perubahan akan disampaikan: tujuan, file/folder, risiko, cara rollback, dan test. Urutannya:

1. Branch `develop` telah dibuat dari state yang pengguna setujui; tidak ada `reset --hard` atau penghapusan data.
2. Snapshot/arsipkan definisi dan dokumentasi legacy, lalu sederhanakan UI/API ke vertical slice Genesis.
3. Refactor contract/registry/lifecycle dan migrasi additive untuk activation, cost ledger, source/citation, test evidence, and rollback pointer.
4. Implementasikan satu jalur end-to-end menggunakan synthetic data sampai bisa menjalankan satu agent.
5. Buat tiga validation agent melalui jalur tersebut, lakukan test full, perbaiki bug, dan siapkan laporan MVP1.

## 13. Known Limitations Saat Audit

- Render visual baseline DOCX tidak tersedia karena executable LibreOffice tidak ada di host ini. Seluruh 105 paragraf dan 27 tabel telah diekstrak/ditinjau secara struktural; tidak ada dokumen yang diedit.
- Test PostgreSQL yang sengaja membutuhkan service integrasi masih `skip` pada audit lokal; fresh migration, backup/restore, dan smoke test database tetap merupakan gate implementasi.
- Harga/infrastruktur pada baseline adalah planning estimate 2 September 2026. Ia tidak menjadi perubahan procurement atau konfigurasi production.

## 14. Catatan Implementasi Saat Ini

- Snapshot lokal pra-rebuild tersimpan pada commit `7fdfed1` di branch `develop`.
- Agent Contract mendukung logical agent, division scope, policy reference, risk, input/output schema, serta status ACTIVE/SUSPENDED/ROLLED_BACK.
- Genesis release sekarang mematerialisasi contract immutable ke shared Agent Registry. Runtime memilih versi ACTIVE bila caller tidak mem-pin versi.
- Tiga validation agent dibuat melalui pipeline Genesis pada data sintetis: `DAILY_BRIEF`, `EVIDENCE_CHECKER`, dan `PERMIT_OVERDUE_MONITOR`.
- Jalur test isolated membuktikan CREATE → two human reviews → stage → release → activate → run → tool denial → suspend → rollback.
- Model Gateway memakai OpenAI primary, Claude fallback opsional, local hanya environment local/test, dan menghitung token/latency/estimated cost dalam metadata runtime.
- Registry memvalidasi reference prompt, model policy, permission policy, dan effect tool terhadap artefak konfigurasi berversi sebelum logical contract dapat dirilis.
