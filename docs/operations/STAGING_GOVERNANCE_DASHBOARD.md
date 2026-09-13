# Staging governance dashboard

Status: CURRENT IMPLEMENTATION runbook. UI memakai same-origin `HttpOnly`
session cookie dan tidak menampilkan provider credential. Backend PostgreSQL
identity dan authorization tetap menjadi authority.

## Bootstrap Director

Jalankan di container platform dari checkout staging. Password diminta secara
interaktif dan tidak diterima melalui argument/environment.

```bash
docker compose --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml run --rm --no-deps platform \
  python -m alos.identity.bootstrap_director
```

Command membuat/refresh account Director dan workspace `ALOS_GOVERNANCE`, lalu
mencatat audit tanpa password/hash di payload.

## Bootstrap IT operator compatibility account

Release API saat ini masih memakai role compatibility `IT_LEAD` pada beberapa
operator/maker path. Sampai migrasi target role selesai, buat akun manusia IT
terpisah:

```bash
docker compose --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml run --rm --no-deps platform \
  python -m alos.identity.bootstrap_it_lead --email it-operator@example.com
```

Ganti email placeholder. Jangan memakai akun Director sebagai operator IT.
Role `BUSINESS_REVIEWER`, `TECHNICAL_REVIEWER`, dan `QA_SECURITY` yang masih
diminta release workflow lama adalah compatibility roles, bukan target akun
organisasi. Jika flow lama harus diuji di staging, provision actor tersebut
secara change-controlled dan tandai evidence sebagai compatibility UAT.

## Verification

1. Sign in sebagai IT operator dan pastikan hanya workspace/scope yang diberikan
   yang terlihat.
2. Periksa Factory proposal, exact version, dependency, generated tests, actual
   eval evidence, permission, rollback target, dan audit.
3. Sign in sebagai Director untuk final decision; pastikan maker/self-approval
   material ditolak oleh backend.
4. Verifikasi approve, release, dan activate tetap command terpisah.
5. Sign out dan pastikan protected route kembali ke login.

## Operational boundary

Dashboard boleh menampilkan provider/model sebagai policy metadata, tetapi tidak
API key, header, raw credential, atau data di luar scope. Disabled button dan
hidden menu bukan RBAC evidence; verifikasi allow/deny pada API. Current budget
update API menerima Director dan role compatibility `IT_LEAD`; target role
mapping harus diubah melalui architectural review, bukan dokumentasi saja.
