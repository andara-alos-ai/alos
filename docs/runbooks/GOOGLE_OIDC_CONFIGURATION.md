# Konfigurasi Login Google OIDC

| Metadata | Nilai |
|---|---|
| Status | Baseline pengembangan dan pilot internal |
| Provider | Google OpenID Connect |
| Cakupan | Autentikasi pengguna; bukan akses Gmail atau Google Drive |

## Prinsip

ALOS memakai Authorization Code Flow dengan PKCE, `state`, dan `nonce`. Google hanya
memverifikasi identitas; role, divisi, project, status pengguna, dan seluruh izin tetap
bersumber dari database ALOS. Login tidak membuat akun secara otomatis. Pengguna harus
sudah berstatus `ACTIVE` dan memiliki email yang sama pada direktori pengguna ALOS.

Token Google tidak dikirim ke browser atau disimpan sebagai sesi ALOS. Callback menukar
hasil Google menjadi kode ALOS sekali pakai dengan masa berlaku singkat. Browser kemudian
menukar kode tersebut dengan bearer token ALOS.

## Konfigurasi Google Cloud untuk Lokal

Gunakan OAuth client bertipe **Web application** dengan nilai berikut:

```text
Authorized JavaScript origin:
http://localhost:3000

Authorized redirect URI:
http://localhost:8000/api/v1/auth/oidc/callback/google
```

Pertahankan publishing status **Testing** selama pengembangan dan tambahkan hanya akun
penguji yang diperlukan. Data Access cukup memakai scope:

```text
openid
https://www.googleapis.com/auth/userinfo.email
https://www.googleapis.com/auth/userinfo.profile
```

Google API key tidak diperlukan untuk login. Jangan menambahkan scope Gmail, Drive,
Calendar, atau layanan lain sebelum terdapat kebutuhan, review keamanan, dan persetujuan
pemilik data.

## Konfigurasi ALOS Lokal

Salin `.env.example` menjadi `.env`, lalu isi nilai berikut pada file `.env` lokal:

```dotenv
ALOS_OIDC_PROVIDER=google
ALOS_OIDC_CLIENT_ID=<client-id-dari-google>
ALOS_OIDC_CLIENT_SECRET=<client-secret-dari-google>
ALOS_OIDC_REDIRECT_URI=http://localhost:8000/api/v1/auth/oidc/callback/google
ALOS_OIDC_ALLOWED_DOMAIN=
```

Kosongkan `ALOS_OIDC_ALLOWED_DOMAIN` untuk pengujian dengan akun Gmail yang terdaftar
sebagai test user. Jika perusahaan kelak memakai Google Workspace atau Cloud Identity,
isi domain resmi perusahaan; ALOS akan memvalidasi klaim domain Google, bukan sekadar
akhiran alamat email.

File `.env` tidak boleh masuk Git. Client Secret tidak boleh ditempel ke percakapan,
dokumentasi, frontend, log, atau definisi agent. Jika pernah terekspos, buat secret baru
di Google Cloud dan cabut secret lama.

## Menjalankan dan Menguji

1. Terapkan migrasi database: `\.venv\Scripts\python.exe -m alos.persistence.migrations`.
2. Pastikan pengguna penguji telah dibuat di ALOS dengan email Google yang sama, status
   `ACTIVE`, role, divisi, dan akses project yang benar.
3. Jalankan API dan web, lalu buka `http://localhost:3000/login`.
4. Pilih **Masuk dengan Google** dan selesaikan persetujuan pada akun test user.
5. Pastikan pengguna kembali ke ALOS, konteks akses sesuai database, dan audit login
   tercatat.

Jika tombol Google tidak muncul, periksa `GET /api/v1/auth/oidc/status` dan pastikan API
membaca `.env` yang benar. Jika Google menolak redirect, bandingkan URI karakter demi
karakter. Jika login ditolak ALOS setelah Google berhasil, periksa status dan email
pengguna pada direktori ALOS; sistem sengaja menolak akun yang belum diprovisikan.

## Staging dan Production

- gunakan hostname HTTPS resmi untuk origin dan callback;
- simpan Client Secret pada secret manager dan pisahkan kredensial antarlingkungan;
- nonaktifkan login pilot lokal;
- batasi domain organisasi setelah domain resmi disahkan;
- wajibkan MFA melalui kebijakan Google Workspace/Cloud Identity;
- lakukan rotasi secret, uji pencabutan akses, dan review audit sebelum go-live;
- jangan memakai client lokal untuk staging atau production.

Publikasi OAuth ke production, domain organisasi, kebijakan MFA, dan pemilik operasional
masih memerlukan keputusan perusahaan. Fondasi ini tidak mengubah struktur organisasi
atau business ownership agent.
