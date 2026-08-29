# ALOS Internal v1

ALOS (Andara Leverage Operating System) adalah platform operasi internal PT Andara Rejo Makmur. Repository ini memuat satu aplikasi web, satu backend modular, satu shared Agent Runtime untuk 18 Core Agent logis, enam workflow awal, dan kontrol tata kelola yang dapat diaudit.

## Status

Tahap saat ini adalah **Backend Foundation / Pilot Internal**. Enam workflow backend, IAM dasar, query operasional, penyimpanan dokumen berversi, work queue, worker/scheduler, notification outbox, dan adaptor n8n opsional telah tersedia. Seluruh contoh data wajib sintetis atau telah disanitasi. Integrasi produksi, keputusan material, dan penggunaan data perusahaan asli belum diaktifkan.

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

API tersedia pada `http://localhost:8000`, dokumentasi API pada `/docs`, dan web pada `http://localhost:3000`.

## Quality Gate

```powershell
pnpm lint
pnpm typecheck
pnpm test
```

Keputusan arsitektur, kontrak agent, workflow, keamanan, serta Definition of Done berada di [docs/README.md](docs/README.md).
