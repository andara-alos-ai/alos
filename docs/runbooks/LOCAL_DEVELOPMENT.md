# Runbook Pengembangan Lokal

## Tujuan

Menjalankan fondasi ALOS Internal v1 dengan data sintetis pada workstation pengembang. Prosedur ini tidak mengaktifkan integrasi produksi atau LLM.

## Prasyarat

- Git dan GitHub CLI;
- Node.js 22 atau lebih baru dan pnpm 11;
- Python 3.12;
- Docker Desktop dengan Docker Compose.

## Persiapan

1. Clone repository privat dan masuk ke direktori root.
2. Salin `.env.example` menjadi `.env`; ganti seluruh nilai `change-me` untuk penggunaan lokal.
3. Jalankan `pnpm install`.
4. Buat virtual environment: `python -m venv .venv`.
5. Aktifkan environment dan jalankan `python -m pip install -e "services/platform[dev]"`.

Jangan menyimpan `.env`, kredensial, dokumen perusahaan, atau hasil ekspor ke Git.

## Menjalankan Layanan

```powershell
docker compose -f infra/compose/compose.yaml up -d
.\.venv\Scripts\python.exe -m alos.persistence.migrations
pnpm dev:api
pnpm dev:web
```

Periksa API melalui `http://localhost:8000/api/v1/health` dan web melalui `http://localhost:3000`.

## Bootstrap Identitas Lokal

Endpoint `POST /api/v1/auth/local-token` hanya tersedia pada lingkungan `local` dan
`test`. Endpoint ini menerbitkan token bertanda tangan untuk pengujian RBAC tanpa
menyimpan kata sandi. Gunakan UUID organisasi dari PostgreSQL dan role pilot yang
sesuai. Endpoint tersebut tidak boleh diaktifkan pada staging atau production.

Operasi project, lead, dan work queue menggunakan header berikut:

```text
Authorization: Bearer <token-lokal>
Idempotency-Key: <nilai-unik-minimal-8-karakter>
X-Correlation-ID: <uuid-opsional>
```

Alur lead menjalankan validasi deterministik melalui SLA, penugasan Sales Human,
penjadwalan follow-up oleh CFA, pencatatan interaksi, dan hasil pipeline/reservasi.
Tidak ada pesan pelanggan yang dikirim otomatis.

Perintah migrasi aman dijalankan berulang. Runner menyimpan versi dan checksum migrasi
sehingga file yang sudah diterapkan tidak dijalankan ulang atau diubah diam-diam. Setelah
paket backend dipasang ulang, alias `alos-migrate` dapat digunakan untuk perintah yang sama.

## Validasi

```powershell
pnpm validate:definitions
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Registry valid hanya jika tepat 18 Core Agent dan enam workflow dapat dimuat. Workflow harus menolak transisi yang tidak didefinisikan.

Untuk memverifikasi persistence PostgreSQL secara end-to-end dengan data sintetis:

```powershell
$env:ALOS_RUN_POSTGRES_TESTS="1"
.\.venv\Scripts\python.exe -m pytest services/platform/tests/test_postgres_smoke.py
Remove-Item Env:ALOS_RUN_POSTGRES_TESTS
```

Smoke test menjalankan Lead-to-Reservation secara end-to-end dan membersihkan kembali
pengguna, project, lead, follow-up, interaksi, reservasi, work item, workflow run,
agent run, transition event, serta audit entry sintetis.

## Menghentikan Layanan

```powershell
docker compose -f infra/compose/compose.yaml down
```

Tambahkan `--volumes` hanya jika data lokal memang boleh dihapus. Jangan gunakan opsi tersebut pada lingkungan bersama.

## Kendala Umum

- PostgreSQL ALOS menggunakan port host `5433` secara default agar tidak berbenturan dengan instalasi PostgreSQL lokal pada `5432`. Ubah `ALOS_POSTGRES_PORT` dan port pada `ALOS_DATABASE_URL` secara bersamaan jika diperlukan.
- Image PostgreSQL 18 memasang volume persisten pada `/var/lib/postgresql`; jangan mengubahnya kembali ke jalur lama `/var/lib/postgresql/data`.
- Jika registry gagal, periksa file `definitions/agents/core/*/agent.json` dan jangan mengosongkan bidang wajib.
- Jika aturan perusahaan masih `TBD`, pertahankan tindakan material dalam status `BLOCKED`; jangan mengisi nilai asumsi.
