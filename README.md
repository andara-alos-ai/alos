# ALOS

ALOS (Andara Leverage Operating System) adalah platform operasi internal PT Andara Rejo Makmur. Repository ini memuat satu aplikasi web, satu backend modular, satu shared Agent Runtime untuk 18 Core Agent logis, enam workflow awal, dan kontrol tata kelola yang dapat diaudit.

## Status

Tahap saat ini adalah **Controlled Pilot Technical Candidate**. Enam workflow telah tersedia melalui backend dan layar transaksi, disertai IAM, project lifecycle, readiness gate, penyimpanan dokumen berversi, work queue, worker/outbox, observability, recovery drill, shared runtime untuk 18 Core Agent, LLM Gateway provider-neutral, dan pipeline design-time Genesis. Seluruh contoh data wajib sintetis atau telah disanitasi. Aktivasi pilot tetap menunggu readiness proyek aktual, recovery evidence, UAT pemilik bisnis, dan keputusan manajemen; integrasi serta data production belum diaktifkan.

## Struktur Utama

```text
apps/web/                 aplikasi web internal
services/platform/        API, workflow, governance, dan shared Agent Runtime
definitions/              kontrak agent, workflow, serta kebijakan berversi
packages/                 kontrak dan komponen lintas aplikasi
infra/                    deployment lokal dan konfigurasi infrastruktur
data/                     skema, template, serta data sintetis
tests/                    pengujian lintas komponen
docs/                     dokumentasi arsitektur dan implementasi
```

## Menjalankan Secara Lokal

Prasyarat: Node.js 22+, pnpm 11+, Python 3.12+, dan Docker Desktop dengan Compose.

1. Salin `.env.example` menjadi `.env`.
2. Jalankan `pnpm install` pada root repository.
3. Buat virtual environment Python dan instal backend dengan `pip install -e "services/platform[dev]"`.
4. Jalankan layanan pendukung dengan `docker compose -f infra/compose/compose.yaml up -d`.
5. Jalankan API dengan `pnpm dev:api` dan web dengan `pnpm dev:web`.
6. Jalankan worker dengan `pnpm worker`; gunakan `pnpm worker:once` untuk satu siklus manual.

API tersedia pada `http://localhost:8000`, dokumentasi API pada `/docs`, dan web pada `http://localhost:3000`. Login Google OIDC bersifat opsional dan dikonfigurasi sesuai [runbook Google OIDC](docs/runbooks/GOOGLE_OIDC_CONFIGURATION.md); Client Secret tidak pernah ditempatkan pada frontend atau Git.

Untuk deployment seluruh stack yang dapat diulang, gunakan `infra/compose/compose.application.yaml` sesuai runbook deployment. File tersebut menjalankan migrasi, API, worker, web, dan PostgreSQL sebagai layanan terpisah tanpa memecah 18 agent menjadi microservice.

## Quality Gate

```powershell
pnpm lint
pnpm typecheck
pnpm test
```

Keputusan arsitektur, kontrak agent, workflow, keamanan, serta Definition of Done berada di [docs/README.md](docs/README.md).
