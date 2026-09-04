# H5 — Local Backend Stability Report

## Scope completed

ALOS tetap satu modular monolith, satu PostgreSQL, satu Genesis, dan satu
shared Agent Runtime. Tidak ada service atau database per agent.

Backend lokal sekarang menyediakan:

- Source Registry append-only: source versi teks memiliki SHA-256, locator,
  chunk citation, audit event, dan status `SOURCE_RECEIVED` → `VERIFIED`.
- Runtime hanya dapat membaca evidence dari source yang telah diverifikasi,
  berada dalam workspace yang sama, dan dipanggil melalui tool `READ_ONLY`
  yang telah `APPROVED`.
- Permission guardrail: setiap `permission_key` pada Agent Contract harus
  memiliki policy `ALLOW` + `APPROVED` untuk version yang dieksekusi.
- Citation guardrail: bila Runtime memberi model retrieved evidence, output
  harus mengembalikan citation yang benar-benar berasal dari retrieval itu;
  citation kosong atau citation buatan menyebabkan run `FAILED`.
- Observability API untuk metadata run dan daily usage ledger; input/output
  mentah tidak dipaparkan pada endpoint operasi.
- Audit API read-only untuk role Director, IT Lead, atau QA Security.
- Genesis conversation, human requirement, Change Request, Blueprint, dan
  Contract artifact history yang immutable dan beraudit.
- Tool Registry dan Permission Policy Registry: maker hanya membuat draft,
  sedangkan maker tersebut tidak boleh menjadi approver tool maupun policy-nya.
- Release test gate wajib memiliki hasil `POSITIVE`, `NEGATIVE`, `REGRESSION`,
  `SECURITY`, dan `RECOVERY` yang lulus sebelum masuk review.

## Evidence quality gate

Pada 3 September 2026, quality gate lokal menghasilkan:

| Gate | Hasil |
| --- | --- |
| PostgreSQL integration, unit, dan API-domain test | `43 passed` |
| Ruff lint | PASS |
| mypy strict | PASS |
| Fresh migration | PASS termasuk `006_h5_source_evidence.sql` |
| 3 validation agents × 6 konteks divisi | 18 run `SUCCEEDED` dengan fake provider deterministik |
| Source belum diverifikasi | tidak dapat diretrieval |
| Permission tidak approved | run `BLOCKED` sebelum provider dipanggil |
| Citation buatan model | run `FAILED` dengan `OUTPUT_SCHEMA_INVALID` |
| Tool di luar allowlist | `BLOCKED` dan diaudit |
| Cost cap, malformed output, provider failure, kill switch, rollback | test otomatis tersedia dan lulus |

Matriks enam konteks menggunakan fixture sintetis berlabel `FINANCE`,
`SALES_MARKETING`, `PROPERTY`, `HR`, `LEGAL`, dan `IT`. Ini merupakan
validasi teknis backend; bukan pengganti UAT pemilik bisnis tiap divisi.

## API yang siap menjadi basis dashboard

| Kebutuhan dashboard | API backend |
| --- | --- |
| Genesis conversation | `POST /api/v1/genesis/conversations` |
| Message/history | `POST` dan `GET /api/v1/genesis/conversations/{id}/messages` |
| Artifact history | `GET /api/v1/genesis/conversations/{id}/artifacts` |
| Register source text | `POST /api/v1/sources` |
| Verifikasi source | `POST /api/v1/sources/{source_key}/verify` |
| Inspect citation | `GET /api/v1/workspaces/{id}/sources/evidence` |
| Agent run history | `GET /api/v1/workspaces/{id}/runs` |
| Token/cost harian | `GET /api/v1/workspaces/{id}/usage/daily` |
| Audit trail | `GET /api/v1/audit-events` |
| Tool Registry | `POST/GET /api/v1/tools`, `POST /api/v1/tools/{key}/approve` |
| Permission Policy | `POST/GET /api/v1/permission-policies`, `POST /api/v1/permission-policies/{id}/approve` |

Semua endpoint bisnis tetap memerlukan bearer token dan workspace scope.

## Status tiga validation Agent Contract

`DAILY_BRIEF`, `EVIDENCE_CHECKER`, dan `PERMIT_OVERDUE_MONITOR` telah ada
sebagai record `DRAFT` lokal dari Genesis. Tidak satu pun diubah atau diaktifkan
otomatis oleh H5.

Catalog versi berikutnya telah menentukan tool `SOURCE_REGISTRY_SEARCH` dan
permission `SOURCE_READ_INTERNAL`. Sebelum tiga draft saat ini dipromosikan,
maker harus membuat version draft berikutnya, Tool Registry harus menyetujui
tool read-only tersebut, dan permission policy harus disetujui. Setelah itu
lifecycle normal tetap wajib dijalankan:

```text
DRAFT → test 5 kategori → business review → technical review
→ Director approval → release → explicit activation
```

Untuk Gemini 3.7 Flash pada local test, Contract validation agent membatasi
output hingga 1.200 token dan environment lokal harus memiliki
`ALOS_LLM_MAX_OUTPUT_TOKENS` minimal `1200`. Ini tetap batas keras per-run;
angka tersebut diperlukan karena token thinking Gemini ikut memakai budget
output dan dapat membuat respons JSON ber-citation berstatus `incomplete` bila
batasnya terlalu rendah.

## Known limitations / HOLD

- Ingest sekarang menerima textual extract; parser DOCX/PDF, OCR, chunker
  dokumen kompleks, dan object storage production belum diaktifkan.
- Tidak ada scheduler harian/mingguan/bulanan. Agent hanya manual run atau
  test-run sampai scheduler memiliki approval, timezone, retry, dan audit.
- Matrix memakai provider palsu agar deterministik. Gemini local smoke telah
  terbukti sebelumnya, namun tidak dipanggil ulang oleh suite ini. Adapter
  OpenAI Responses sudah tersedia di shared Model Gateway, tetapi belum
  menerima traffic dan masih HOLD pada smoke test VPS staging.
- Dashboard web untuk Tool Registry, Permission Policy, lifecycle review, dan
  observability belum dibuat; seluruh API pendukungnya sudah tersedia.
- Tidak ada dashboard web, SSO/identity provider, VPS staging, backup restore
  drill, maupun UAT manusia enam divisi pada checkpoint lokal ini.

Karena batas tersebut, status yang benar adalah **LOCAL BACKEND READY FOR
CONTROLLED VALIDATION**, bukan production-ready.
