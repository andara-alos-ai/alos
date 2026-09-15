# Postman API Collection

Dokumentasi API ini dibuat langsung dari schema OpenAPI FastAPI yang ada di project.

## Import ke Postman

1. Buka Postman.
2. Klik `Import`.
3. Pilih file `docs/postman/ALOS-API.postman_collection.json`.
4. Pastikan environment `baseUrl` di-set ke `http://localhost:8000`.

> File ini dibuat otomatis dari schema OpenAPI FastAPI project, jadi selalu mengikuti endpoint yang aktif di server.

## Register user baru

Gunakan urutan berikut di Postman:

1. Jalankan `POST /api/v1/auth/login` menggunakan akun `DIRECTOR` atau `IT_ADMIN`.
2. Jalankan `POST /api/v1/users/register`. Postman akan mengirim cookie sesi dari request login.
3. Isi body JSON dengan email, password minimal 12 karakter, division, dan role baru.

Contoh body:

```json
{
	"email": "member@company.test",
	"display_name": "IT Team Member",
	"password": "StrongPassword123!",
	"confirm_password": "StrongPassword123!",
	"division_code": "IT",
	"roles": ["DIVISION_MEMBER"]
}
```

Endpoint register hanya menerima pendaftaran dari admin yang sudah terautentikasi. Akun yang dibuat tersimpan ke database dan dapat langsung digunakan untuk login.

## OpenAPI docs bawaan

FastAPI sudah menyediakan dokumentasi yang bisa dibuka langsung:

- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json

## Generate ulang collection

```bash
PYTHONPATH=services/platform/src python services/platform/scripts/export_postman_collection.py
```

File collection akan dibuat ulang di `docs/postman/ALOS-API.postman_collection.json`.
