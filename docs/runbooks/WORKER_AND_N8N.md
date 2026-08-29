# Worker, Outbox, dan Integrasi n8n

## Tujuan

Worker ALOS menjalankan evaluasi deadline deterministik, membuat notification event, dan
mengirim transactional outbox. Worker tidak mengambil keputusan bisnis, memberi approval,
menutup CAPA, atau menjalankan LLM. PostgreSQL tetap menjadi sumber status resmi; n8n hanya
menjadi adaptor delivery atau orkestrasi integrasi yang telah disetujui.

## Menjalankan Worker

Pastikan PostgreSQL aktif dan seluruh migrasi telah diterapkan. Jalankan satu siklus untuk
verifikasi:

```powershell
pnpm worker:once
```

Jalankan mode layanan:

```powershell
pnpm worker
```

Satu siklus mengevaluasi deadline seluruh organisasi, membuat outbox secara idempotent,
mengambil batch dengan lease, lalu mengirim notification internal dan webhook aktif.
Beberapa worker dapat berjalan bersamaan karena event diklaim memakai row lock.

## Konfigurasi Minimum

| Environment variable | Default | Fungsi |
|---|---:|---|
| `ALOS_WORKER_POLL_SECONDS` | `5` | jeda antarsiklus worker |
| `ALOS_WORKER_BATCH_SIZE` | `50` | event maksimum per siklus |
| `ALOS_WORKER_LEASE_SECONDS` | `120` | batas lease sebelum event dipulihkan |
| `ALOS_WORKER_MAX_ATTEMPTS` | `5` | percobaan sebelum dead-letter |
| `ALOS_DEADLINE_HORIZON_MINUTES` | `1440` | horizon reminder due-soon |
| `ALOS_ESCALATION_INTERVAL_MINUTES` | `60` | jeda escalation overdue |

Retry memakai backoff eksponensial terbatas. Event yang melewati jumlah percobaan masuk
`DEAD_LETTER` dan tidak dicoba otomatis. Periksa kesehatan melalui
`GET /api/v1/system/operations-health`. Setelah penyebab diperbaiki, Direktur atau IT Admin
dapat menjalankan `POST /api/v1/system/outbox/{id}/requeue` dengan alasan yang dapat diaudit.

## Mengaktifkan n8n

n8n nonaktif secara default. Gunakan webhook khusus ALOS dan signing secret acak minimal
32 karakter:

```dotenv
ALOS_N8N_ENABLED=true
ALOS_N8N_WEBHOOK_URL=https://n8n.example.co.id/webhook/alos-events
ALOS_N8N_WEBHOOK_SECRET=ganti-dengan-secret-acak-minimal-32-karakter
ALOS_N8N_TIMEOUT_SECONDS=10
```

Staging dan production wajib memakai HTTPS. URL tidak boleh berisi username, password,
atau fragment. Secret hanya berada pada secret manager/environment API dan n8n; jangan
menyimpannya di repository atau workflow export.

## Kontrak Webhook

ALOS mengirim JSON yang memuat `event_id`, `event_type`, `occurred_at`, `organization_id`,
`correlation_id`, `idempotency_key`, dan `data`. Header penting:

- `X-ALOS-Event-ID` untuk trace;
- `X-ALOS-Idempotency-Key` untuk deduplikasi pada n8n;
- `X-ALOS-Signature: sha256=<hex>` sebagai HMAC-SHA256 atas body mentah.

n8n wajib menghitung ulang HMAC menggunakan body mentah, membandingkannya secara aman,
dan menolak signature yang tidak cocok. Workflow n8n harus menyimpan idempotency key agar
retry ALOS tidak menghasilkan notifikasi atau tindakan ganda. Response `2xx` berarti
delivery diterima; status lain, timeout, dan kegagalan koneksi diproses sebagai retry.
Jika n8n dinonaktifkan, worker tidak mengambil event ber-destination n8n; event tetap
tersimpan dan dapat dilanjutkan setelah adaptor diaktifkan kembali.

Payload reminder hanya berisi identifier dan metadata operasional minimum. Konten dokumen,
credential, token, dan data sensitif tidak dikirim. Penambahan field atau event baru wajib
melalui contract test, review keamanan, serta persetujuan business owner terkait.

## Batas Integrasi

- n8n tidak menulis langsung ke PostgreSQL ALOS;
- n8n tidak menentukan permission, deadline, status, approval routing, atau arithmetic;
- callback material ke ALOS belum diaktifkan sampai use case, autentikasi, replay protection,
  dan business owner disahkan;
- kegagalan n8n tidak menghapus event, reminder, audit, atau status workflow ALOS;
- token vendor downstream disimpan di credential store n8n dengan akses minimum.
