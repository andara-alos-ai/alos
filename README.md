# ALOS — Andara Leaverage Operating Sistem

ALOS adalah satu aplikasi internal dengan satu **Genesis** sebagai AI Executive
Operating Layer dan satu shared Agent Runtime. Genesis membuat serta mengelola
logical agent melalui Agent Contract dan Agent Registry yang sama; agent tidak
menjadi aplikasi, database, atau microservice tersendiri.

## Scope saat ini

Hari 1 membangun fondasi local/staging-only: satu database PostgreSQL,
identity enam divisi, audit baseline, health check, dan migration runner.
Tidak ada agent aktif, akses production, atau provider LLM aktif pada tahap ini.

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

Mulai dari [peta dokumentasi ALOS](docs/README.md). Target lima hari serta
quality gate pembuktian ada di
[delivery plan](docs/implementation/ALOS_MVP1_DELIVERY_PLAN.md); baseline H0
tetap tercatat di `docs/implementation/GENESIS_MVP1_EXECUTION_PLAN.md`.
