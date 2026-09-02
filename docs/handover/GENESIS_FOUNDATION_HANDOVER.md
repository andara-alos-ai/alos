# Handover Genesis, Capability Registry, dan Shared Runtime

| Metadata | Nilai |
|---|---|
| Status | Technical Foundation Complete / Synthetic UAT Ready |
| Pembaruan terakhir | 30 Agustus 2026 |
| Batas | Belum merupakan persetujuan production atau data asli |

## Hasil

- seluruh agent tetap berupa konfigurasi logis pada satu shared runtime; 18 definisi lama dipertahankan sementara untuk kompatibilitas workflow pilot;
- Agent Contract universal berlaku untuk Core, Sub-Agent, dan Sub-Sub-Agent;
- 61 capability dan 38 tool berada pada registry berversi;
- keenam workflow melakukan dispatch melalui capability handler, bukan branch per agent;
- setiap run menyimpan handler, evidence, warning, verification, provider metadata, digest Agent/Capability Contract, correlation, dan audit;
- TIA, MCA_MKT, dan agent lain dapat dievaluasi melalui endpoint runtime yang sama tanpa efek eksternal;
- LLM Gateway mendukung OpenAI/Anthropic, default nonaktif, structured output, redaction, klasifikasi, budget, retry, dan fail-closed;
- Genesis menjalankan REUSE/EXTEND/CREATE sampai dua review, staging, dan release package immutable;
- Genesis tidak dapat mengubah struktur organisasi, registry production, atau deployment; agent baru hanya dapat masuk melalui contract, governance, review, staging, dan release;
- migrasi, API, worker, web, dan PostgreSQL memiliki konfigurasi deployment yang dapat diulang.

## Validasi Serah Terima

```powershell
docker compose -f infra/compose/compose.yaml up -d
.\.venv\Scripts\python.exe -m alos.persistence.migrations
$env:ALOS_RUN_POSTGRES_TESTS="1"
.\.venv\Scripts\python.exe -m pytest services/platform/tests -p no:cacheprovider
.\.venv\Scripts\python.exe -m ruff check services/platform
.\.venv\Scripts\python.exe -m mypy services/platform/src
pnpm --filter @andara/alos-web test
pnpm --filter @andara/alos-web lint
pnpm --filter @andara/alos-web typecheck
pnpm --filter @andara/alos-web build
```

Fresh-database test wajib lulus. UAT mengikuti `docs/uat/SYNTHETIC_PILOT_UAT.md`.

## Gate yang Masih Memerlukan Perusahaan

- data, SOP, KPI, SLA, approval matrix, dan business owner final;
- UAT dan sign-off dari enam divisi serta Direktur Utama;
- identity provider, hosting, domain, TLS, secret manager, RTO/RPO, backup/restore, dan incident response;
- vendor LLM, model, batas biaya, lokasi pemrosesan, retensi, dan klasifikasi data yang diizinkan;
- credential serta sandbox API n8n, Meta Ads, CRM, bank, pajak, OSS, HRIS, dan layanan eksternal lain;
- security review dan persetujuan penggunaan data perusahaan asli.

Seluruh gate di atas tetap `TBD` atau dinonaktifkan. Sistem aman digunakan untuk pengujian sintetis, tetapi belum boleh disebut production-ready sebelum gate tersebut ditutup.
