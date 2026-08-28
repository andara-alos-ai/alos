# API Foundation Operasional

| Metadata | Nilai |
|---|---|
| Status | Implementasi Pilot Internal |
| Versi | 0.3.0 |
| Cakupan | Identitas lokal, project, lead-to-reservation, work queue, agent registry, workflow registry |

## Prinsip

- Operasi bisnis menggunakan bearer token, konteks organisasi, role, dan akses project.
- Perintah yang dapat diulang wajib membawa `Idempotency-Key`.
- `X-Correlation-ID` menghubungkan work item, workflow run, agent run, dan audit.
- Endpoint autentikasi lokal tidak tersedia pada staging atau production.
- API key vendor dan token LLM tidak pernah diteruskan ke Core Agent atau browser.

## Endpoint

| Method | Path | Tujuan | Akses |
|---|---|---|---|
| `GET` | `/health` | status layanan | pemeriksaan sistem |
| `POST` | `/auth/local-token` | token pengembangan lokal | local/test saja |
| `GET` | `/agents` | registry 18 Core Agent | read-only |
| `GET` | `/workflows` | enam definisi workflow | read-only |
| `POST` | `/users` | provisioning pengguna dan role per divisi | IT Admin |
| `POST` | `/projects` | membuat project berstatus DRAFT | Director atau IT Admin |
| `GET` | `/projects` | project dalam organisasi pengguna | pengguna terautentikasi |
| `POST` | `/leads` | intake lead dan memulai `FLOW-001` | Sales, Division Head, IT Admin |
| `GET` | `/work-items` | antrean kerja terfilter organisasi/divisi/project | pengguna terautentikasi |
| `POST` | `/workflow-runs/{id}/sales-assignment` | menetapkan Sales PIC dan follow-up awal | Sales, Division Head, IT Admin |
| `POST` | `/workflow-runs/{id}/interactions` | mencatat interaksi dan hasil pipeline | Sales PIC, Division Head, IT Admin |

## Jalur Lead Saat Ini

`POST /leads` memeriksa kanal kontak, consent, role, dan akses project. Sistem kemudian:

1. menyiapkan eksekusi capability `SLA.validate_lead_fields`;
2. menyimpan lead, work item, workflow run, dan agent run dalam satu transaksi;
3. menetapkan tenggat respons awal 15 menit sebagai baseline pilot;
4. mencatat audit entry berantai hash;
5. berhenti pada langkah `sales-assignment` untuk keputusan manusia;
6. setelah Sales PIC ditetapkan, CFA membuat follow-up task tanpa mengirim pesan;
7. Sales PIC mencatat interaksi sebagai `follow_up`, `qualified`, `reserved`, atau
   `exception`;
8. reservasi menyelesaikan workflow hanya setelah dicatat Sales Human dan memiliki
   referensi reservasi.

Tidak ada komunikasi pelanggan, perubahan harga, pembayaran, atau aktivitas eksternal
yang dilakukan otomatis pada tahap foundation ini.

## Batas Pilot

Token lokal merupakan bootstrap provider untuk pengembangan, bukan pengganti identity
provider perusahaan. Formula SLA 15 menit, role final, serta kebijakan akses masih dapat
berubah melalui review dan rilis konfigurasi sebelum production.
