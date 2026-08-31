# Runbook Pengembangan Lokal

## Tujuan

Menjalankan fondasi ALOS dengan data sintetis pada workstation pengembang. Prosedur ini tidak mengaktifkan integrasi produksi atau LLM.

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

### Masuk ke Web Pilot

Pastikan `NEXT_PUBLIC_ALOS_PILOT_LOGIN_ENABLED=true` hanya pada lingkungan lokal. Buka
`http://localhost:3000`, pilih **Profil pilot**, lalu isi Organization ID, User ID, role,
kode divisi, dan Project ID sintetis yang sesuai. Web meminta token lokal, memverifikasinya
melalui `GET /api/v1/auth/me`, dan menyimpan token hanya pada `sessionStorage` tab aktif.

Mode **Token akses** menerima token yang sudah diterbitkan sistem identitas. Jangan masukkan
kata sandi, API key, atau token produksi ke layar pilot. Pada staging/production, endpoint
token lokal dan flag login pilot wajib dinonaktifkan serta diganti integrasi OIDC/SSO.

### Masuk dengan Google

ALOS mendukung Google OIDC tanpa memberikan akses Gmail atau Google Drive. Aktifkan
`ALOS_OIDC_PROVIDER=google`, simpan Client ID dan Client Secret hanya di `.env`, lalu
pastikan callback lokal tepat sama dengan nilai yang terdaftar di Google Cloud. Pengguna
Google harus sudah diprovisikan sebagai pengguna `ACTIVE` di ALOS; role, divisi, project,
dan izin tidak diambil dari Google.

Panduan nilai Google Cloud, scope minimum, variabel environment, dan troubleshooting
tersedia pada [Konfigurasi Login Google OIDC](GOOGLE_OIDC_CONFIGURATION.md).

Menu mengikuti role dan divisi. Konteks proyek pada topbar membatasi dashboard, antrean,
dokumen, approval, serta exception/CAPA ke proyek yang dipilih. Backend tetap menjadi sumber
otorisasi; menyembunyikan menu di web bukan pengganti pemeriksaan izin API.

Jalankan worker scheduler/outbox pada terminal terpisah:

```powershell
pnpm worker
```

Untuk satu siklus pemeriksaan manual gunakan `pnpm worker:once`. Detail konfigurasi,
retry, dead-letter, dan n8n tersedia pada runbook Worker dan Integrasi n8n.

## Penyimpanan Dokumen Lokal

Konfigurasi default menyimpan berkas sintetis di `data/objects/alos-documents`. Direktori
tersebut tidak masuk Git. Pertahankan `ALOS_OBJECT_STORAGE_PROVIDER=filesystem` hanya untuk
local/test dan jangan memasukkan dokumen perusahaan asli.

Gunakan `POST /api/v1/documents/upload` untuk upload multipart, bukan endpoint metadata
lama. Tambahkan versi melalui `POST /api/v1/documents/{id}/versions` dan unduh melalui
`GET /api/v1/documents/{id}/content`. Batas awal dikendalikan oleh
`ALOS_OBJECT_STORAGE_MAX_UPLOAD_BYTES` dengan default 25 MB.

Staging/production menggunakan provider `s3`, bucket private dan terenkripsi, HTTPS, serta
kredensial terbatas dari secret manager atau IAM workload identity. Mode scan `external`
memerlukan scanner malware yang mengubah status menjadi `CLEAN`; dokumen pending tidak
dapat diunduh. Vendor object storage dan scanner production belum disahkan.

## Bootstrap Identitas Lokal

Endpoint `POST /api/v1/auth/local-token` hanya tersedia pada lingkungan `local` dan
`test`. Endpoint ini menerbitkan token bertanda tangan untuk pengujian RBAC tanpa
menyimpan kata sandi. Gunakan UUID organisasi dari PostgreSQL dan role pilot yang
sesuai. Endpoint tersebut tidak boleh diaktifkan pada staging atau production.

Login Google memakai endpoint OIDC yang sama pada seluruh lingkungan. Callback tidak
menaruh bearer token ALOS di URL; web hanya menerima kode sekali pakai yang segera
ditukar dan dihapus dari fragment browser. Token ALOS tetap disimpan pada
`sessionStorage` tab aktif selama baseline web saat ini.

Operasi project, workflow Sales, workflow Finance, dan work queue menggunakan header berikut:

```text
Authorization: Bearer <token-lokal>
Idempotency-Key: <nilai-unik-minimal-8-karakter>
X-Correlation-ID: <uuid-opsional>
```

Setelah pengguna dibuat, berikan akses project melalui
`POST /api/v1/users/{user_id}/project-assignments`. Penugasan role tambahan dan akses
project wajib menyertakan alasan. Endpoint query operasional menggunakan pagination
dan filter server-side; contoh pemeriksaan adalah
`GET /api/v1/leads?page=1&page_size=25&project_id=<uuid>`.

### Onboarding Pengguna melalui Web

IT Admin dapat membuka menu **Pengguna & Akses** untuk membuat akun, menambah role,
menetapkan divisi, memberi akses project, mengatur masa berlaku, mengaktifkan atau
menangguhkan akun, dan mencabut penugasan. Email akun harus sama persis dengan email Google
yang akan digunakan untuk login. Direktur dan Auditor memperoleh akses baca tanpa tombol
perubahan.

Setiap perubahan atau pencabutan wajib memiliki alasan minimal delapan karakter dan dicatat
pada audit trail. Role domain hanya dapat ditempatkan pada divisi yang sesuai; role Direktur,
AI Executive, dan Auditor tidak ditempatkan pada divisi. Administrator tidak dapat mengubah
status atau mencabut akses akunnya sendiri. Login Google tetap menolak email yang belum
terdaftar atau akun yang berstatus `SUSPENDED`.

Alur lead menjalankan validasi deterministik melalui SLA, penugasan Sales Human,
penjadwalan follow-up oleh CFA, pencatatan interaksi, dan hasil pipeline/reservasi.
Tidak ada pesan pelanggan yang dikirim otomatis.

Alur pembayaran memerlukan dua pengguna Finance berbeda untuk membuktikan pemisahan
tugas. Requester menyiapkan budget, metadata dokumen, dan payment request. Approver
memberikan keputusan serta mencatat hasil pembayaran yang dilakukan di luar ALOS. FRA
merekonsiliasi data transaksi; ALOS tidak mengakses atau mengeksekusi transfer bank.

Alur Property memerlukan pengunggah dan reviewer berbeda. CEA memeriksa evidence, TPA
menghitung variance, lalu keputusan reviewer menghasilkan snapshot progres KDA atau
exception dan CAPA CRA. Data lokasi lapangan dan formula KPI final belum diwajibkan pada
pilot sintetis karena kebijakannya masih TBD.

Alur Legal memerlukan pengaju dan reviewer berbeda. DIA menyiapkan metadata dokumen,
LPA atau CLA memproses izin atau kontrak, dan CEA memeriksa evidence. Persetujuan izin
mewajibkan konfirmasi sumber resmi oleh Legal Human; agent tidak memberikan opini hukum
atau persetujuan kontrak.

Alur HR menggunakan dokumen kandidat yang telah disanitasi dan alias, bukan data pribadi
mentah. SEA membentuk rencana, HRA mencatat kelengkapan administratif, dan HR Human
memberi keputusan. HPA hanya membuat checklist untuk kandidat yang dipilih manusia.
Data kandidat asli tidak boleh digunakan sebelum kebijakan akses dan retensi disahkan.

Alur AI Executive membaca fakta terverifikasi dari seluruh modul, membuat snapshot
ber-hash, menjalankan KDA/CRA/ARA/MCA pada shared runtime, dan berhenti untuk review
Direktur. Role Direktur dan AI Executive dibuat dengan `division_code: null` karena
keduanya berada pada tingkat organisasi, bukan salah satu dari enam divisi.

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

Registry valid hanya jika tepat 18 Core Agent, 38 tool, enam workflow pilot wajib tersedia, dan seluruh source pack dapat dimuat. Workflow tambahan diperbolehkan setelah memiliki definisi valid; status selain `STAGED` atau `RELEASED` tidak dapat dijalankan. Setiap langkah agent wajib memiliki capability invocation yang valid dan workflow harus menolak transisi yang tidak didefinisikan.

Pemeriksaan web juga mencakup redirect tanpa sesi, login pilot, dashboard data nyata,
navigasi role/divisi, konteks proyek, tampilan kosong/error, serta breakpoint ponsel.

Untuk memverifikasi persistence PostgreSQL secara end-to-end dengan data sintetis:

```powershell
$env:ALOS_RUN_POSTGRES_TESTS="1"
.\.venv\Scripts\python.exe -m pytest -c services/platform/pyproject.toml
Remove-Item Env:ALOS_RUN_POSTGRES_TESTS
```

Smoke test menjalankan upload/version/download dokumen beserta pembatasan klasifikasinya,
Lead-to-Reservation, Payment-to-Reconciliation, dua cabang
Site-Evidence, Permit-and-Contract Review, Recruitment-to-Personnel-Checklist, serta
Executive-Brief-to-Director-Review secara end-to-end. Test juga memverifikasi query
list/detail, isolasi project, larangan baca lintas divisi, perubahan role/project/status,
claim/delegasi work item, reminder/escalation idempotent, approval claim dan SoD, serta
siklus Exception-CAPA dengan evidence. Seluruh pengguna, project,
transaksi domain, work item, workflow run, agent run, transition event, evidence,
approval, snapshot eksekutif, KPI snapshot, exception, CAPA, dan audit entry sintetis
dibersihkan kembali setelah pengujian.

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
