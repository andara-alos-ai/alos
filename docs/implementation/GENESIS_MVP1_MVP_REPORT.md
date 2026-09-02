# GENESIS MVP1 — Laporan Hasil Rebuild

**Status:** READY FOR CONTROLLED SYNTHETIC PILOT  
**Branch:** `develop`  
**Tanggal:** 2 September 2026

## Hasil Utama

ALOS sekarang berjalan sebagai satu aplikasi internal dengan satu shared Agent Runtime dan satu Genesis design-time. Struktur `18 Core Agent` lama tetap sebagai kontrak legacy yang terbaca, tetapi Genesis tidak lagi menjadikannya taxonomy atau parent wajib untuk agent baru.

- Genesis menerima requirement natural language dan source reference, lalu menyimpan conversation/artifact history.
- Analyzer menghasilkan Blueprint dan Logical Agent Contract DRAFT: division scope, owner, KPI, source/evidence requirement, forbidden actions, prompt/model/permission policy reference, risk, dan JSON schema. Referensi prompt, model policy, permission policy, dan efek tool divalidasi fail-closed sebelum registrasi.
- Pipeline mewajibkan human business review dan human technical review yang berbeda, kemudian staging dan release package. Pemohon tidak dapat mereview, stage, atau release sendiri.
- Release Genesis mematerialisasi contract immutable ke shared Agent Registry.
- Shared runtime menjalankan contract yang dipin, memeriksa capability, tool allowlist, status lifecycle, schema, evidence, dan scope divisi.
- Lifecycle tersedia: release, human activation, suspend/kill-switch, dan rollback ke versi lama. Aktivasi memilih satu versi ACTIVE per logical agent dan setiap operasi lifecycle mencatat audit event.
- Tiga logical validation agent dibuat melalui pipeline menggunakan source sintetis: `DAILY_BRIEF`, `EVIDENCE_CHECKER`, dan `PERMIT_OVERDUE_MONITOR`.
- Model Gateway adalah satu boundary provider: OpenAI primary, Claude fallback sesudah kegagalan primary, Ollama/local hanya local/test. Metadata menyimpan provider, model, token, latency, dan estimated cost.

## Bukti Verifikasi

| Pemeriksaan | Hasil |
| --- | --- |
| Python lint (Ruff) | PASS |
| Python type-check (mypy strict) | PASS — 118 source files |
| Python test suite | PASS — 165 passed, 31 skipped (PostgreSQL opt-in) |
| Frontend lint/type-check | PASS |
| Frontend unit test | PASS — 5 files, 16 tests |
| Frontend production build | PASS |
| Agent/source/config registry validation | PASS — 18 legacy top-level + 3 logical definitions; 3 source packs; 1 config register |
| Secret-pattern scan on tracked workspace content | PASS — no key pattern found; `.env` excluded/read untouched |
| Python and Node dependency audit | PASS |

The end-to-end isolated test proves: `CREATE → business review → technical review → stage → release → activate → run → tool denial → suspend → rollback`.

## Known Limitations / Follow-up Gate

- PostgreSQL migration/fresh-bootstrap, database integration, and backup/restore tests are opt-in and were skipped because Docker is not installed on this host. Run them with a disposable database after Docker/PostgreSQL is available: `ALOS_RUN_POSTGRES_TESTS=1`.
- Source packs enforce version, authority, SHA metadata, allowed use, and citation references. Full production document extraction/chunk-level locator is not yet implemented; do not use this MVP for production document ingestion.
- `estimated_cost_usd` depends on configured per-token rates. Default is `0.0` until finance/IT set approved rates; tokens, provider, model, and latency are still recorded.
- Lifecycle filesystem status is audited through the application ledger. Production deployment/activation remains deliberately outside Genesis and requires a separate controlled deployment procedure.

## Rollback

Use the pre-rebuild snapshot commit `7fdfed1` on `develop` to restore the repository state, or use the Agent Registry rollback endpoint/service to restore a prior logical-agent release. No credential, `.env`, Git history, migration, or production data was deleted.
