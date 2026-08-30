# Runbook Deployment ALOS Internal v1

| Metadata | Nilai |
|---|---|
| Status | Siap untuk staging berbasis data sintetis |
| Scope | PostgreSQL, migration job, API, worker, dan web |

## Prasyarat

- Docker Engine dengan Compose v2;
- secret yang kuat untuk PostgreSQL dan token signing;
- object storage S3-compatible dan malware scanner untuk production;
- backup database serta restore test;
- hostname HTTPS dan reverse proxy perusahaan;
- identity provider, RTO/RPO, dan owner operasional yang telah disetujui.

## Menjalankan Staging

1. Salin `infra/environments/staging/app.env.example` ke file environment di luar repository.
2. Isi seluruh nilai secret melalui secret manager, bukan Git.
3. Validasi image dan dependency pada CI.
4. Jalankan:

```powershell
docker compose --env-file <path-env> -f infra/compose/compose.application.yaml up -d --build
```

Job `migrate` harus selesai sebelum API dan worker aktif. Image platform menetapkan repository root `/app` agar seluruh migration dan definition dapat ditemukan secara konsisten. Periksa `/api/v1/health`, `/api/v1/system/operations-health`, log worker, dan status outbox.

Status worker dinilai melalui heartbeat pada tabel `observability.worker_runs`, bukan endpoint HTTP API. Worker dinyatakan sehat jika memiliki siklus `COMPLETED`/`PARTIAL` atau status `RUNNING` yang masih baru sesuai batas healthcheck.

## Rollback dan Recovery

- migration bersifat forward-only; rollback aplikasi memakai image digest sebelumnya yang kompatibel dengan schema;
- hentikan worker sebelum restore database;
- restore hanya dari backup terverifikasi, lalu jalankan integrity check, migration, API health, dan satu worker cycle;
- LLM dan n8n dapat dinonaktifkan melalui environment tanpa mengubah workflow deterministik.

Deployment production belum diizinkan hanya berdasarkan runbook ini. UAT, review keamanan, backup/restore, observability, incident response, dan persetujuan manajemen tetap menjadi gate wajib.
