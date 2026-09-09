# ALOS — Andara Leaverage Operating Sistem

ALOS adalah satu aplikasi internal dengan satu **Genesis** sebagai AI Executive
Operating Layer dan satu shared Agent Runtime. Genesis membuat serta mengelola
logical agent melalui Agent Contract dan Agent Registry yang sama; agent tidak
menjadi aplikasi, database, atau microservice tersendiri.

## Ruang lingkup aktif

ALOS menyediakan identitas dan data scope, capability/tool terkontrol, Agent
Contract/release/runtime, GENESIS, dokumen kanonis, task, temuan, approval,
laporan, proyek, audit append-only, dan antrean job tahan restart. GENESIS
membuat proposal aksi terikat digest untuk persetujuan manusia; ia tidak
melakukan aksi material secara otomatis.

Enam konteks divisi adalah `FINANCE`, `SALES_MARKETING`, `PROPERTY`, `HR`,
`LEGAL`, dan `IT`. Genesis adalah system actor lintas divisi, bukan divisi
atau role manusia.

## Local bootstrap

1. Salin `.env.example` menjadi `.env` dan isi password lokal yang sama pada
   `ALOS_POSTGRES_PASSWORD` serta `ALOS_DATABASE_URL`.
2. Jalankan `docker compose -f infra/compose/compose.yaml up -d postgres`.
3. Aktifkan virtual environment lalu jalankan
   `python -m alos.persistence.migrations` dari `services/platform`.
4. Jalankan API dengan `python -m uvicorn alos.main:app --app-dir src --port 8000`.
5. Dari root repository jalankan web dengan `pnpm --filter @andara/alos-web dev`.

Migrasi bersifat append-only. Tambahkan versi baru di `infra/database/`; jangan
mengubah migrasi yang telah diterapkan.

## Quality dan deployment

Jalankan lint, typecheck, test frontend/backend, dan build sebelum merge. CI
menjalankan semua pemeriksaan itu, fresh PostgreSQL migration, serta dependency
audit pada pull request dan `main`.

Staging/production memakai PostgreSQL terkelola, S3-compatible object storage,
systemd, dan Caddy native pada VPS. Kredensial, domain, signing secret, dan
provider LLM adalah input eksternal dan tidak disimpan di Git. Gunakan
[runbook VPS native](docs/operations/VPS_NATIVE_DEPLOYMENT.md) dan
[backup/restore](docs/operations/BACKUP_RESTORE.md).

Mulai dari [peta dokumentasi ALOS](docs/README.md).
