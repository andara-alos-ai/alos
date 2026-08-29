# Handover Fondasi Genesis ALOS

| Metadata | Nilai |
|---|---|
| Status | Selesai untuk Fondasi Pilot G1–G3 |
| Pembaruan terakhir | 30 Agustus 2026 |
| Cakupan | Agent Contract, registries, shared runtime, dan interface design-time Genesis |

## Hasil

- 18 Core Agent tetap utuh sebagai agent logis pada satu shared runtime;
- Agent Contract v1 berlaku untuk Core, Sub-Agent, dan Sub-Sub-Agent;
- Agent Registry memvalidasi versi, hierarchy, parent, extends, cycle, dan baseline 18 Core;
- 38 operasi terdaftar pada Tool Registry dan divalidasi terhadap allow-list agent;
- enam workflow memakai capability invocation berversi, termasuk selector Legal `PERMIT`/`CONTRACT`;
- runtime menyiapkan plan dari registry/workflow dan dispatch melalui handler capability generik;
- Agent Release dan Workflow Release memiliki snapshot/digest immutable;
- execution run menyimpan capability, mode, tool release, workflow step, dan contract digest;
- interface Genesis menghasilkan proposal `REUSE`, `EXTEND`, atau `CREATE` tanpa menulis production.

## Validasi Serah Terima

Jalankan dari root repository:

```powershell
docker compose -f infra/compose/compose.yaml up -d
.\.venv\Scripts\python.exe -m alos.persistence.migrations
$env:ALOS_RUN_POSTGRES_TESTS="1"
.\.venv\Scripts\python.exe -m pytest services/platform/tests
pnpm --filter @andara/alos-web test
pnpm --filter @andara/alos-web lint
pnpm --filter @andara/alos-web typecheck
pnpm --filter @andara/alos-web build
```

Migrasi terakhir adalah `018_registry_driven_execution.sql`. Fresh-database test wajib lulus agar snapshot, trigger immutability, dan metadata execution terbukti reproducible.

## Batas Saat Ini

- fondasi ini belum full Genesis;
- Genesis belum membaca dokumen, menggunakan LLM, menulis registry, staging, release, atau deploy;
- capability handler produksi belum tersedia untuk seluruh capability; interface dispatch dan release gate sudah tersedia;
- LLM provider dan integrasi eksternal tetap dinonaktifkan sampai kebijakan data, credential, serta UAT disetujui;
- nilai KPI, SLA, approval, retensi, dan vendor yang belum disahkan tetap `TBD`;
- data perusahaan asli belum boleh digunakan.

## Tahap Berikutnya

1. implementasikan handler capability prioritas dengan output schema dan evidence;
2. tambahkan pipeline Genesis `analyze → generate → validate → test → diff` pada sandbox;
3. bangun human review dan staging/release terotorisasi;
4. jalankan UAT enam divisi menggunakan data sintetis;
5. aktifkan provider/integrasi satu per satu setelah kontrol keamanan dan pemilik bisnis disahkan.
