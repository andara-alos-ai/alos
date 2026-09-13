# Branch strategy

## Active development

Branch aktif untuk pengembangan GENESIS Capability/Agent Factory adalah:

```text
epic/genesis-agent-factory
```

Semua dokumentasi current implementation pada repository ini harus diverifikasi
terhadap branch tersebut. Jangan menyatakan fitur target selesai hanya karena
pernah ada di branch atau UI lain.

## Comparison baseline

Branch `develop` adalah baseline lama untuk mengambil lesson learned
governance/UAT saja. Dalam pekerjaan Factory ini, ia bukan branch aktif dan
struktur UI/kode lamanya bukan target. Jangan merge atau cherry-pick baseline
tersebut ke branch aktif tanpa change request terpisah.

Behavior yang harus dipertahankan ketika desain baru menggantikan implementasi
lama: maker/self-approval protection, workspace scoping, permission metadata
dan lifecycle, version-bound review/reject, active-version dan rollback-target
correctness, suspend/resume correctness, audit/evidence, serta regression/RBAC
testing.

## Change discipline

- Buat perubahan terfokus sesuai ownership; pisahkan dokumentasi, migration,
  backend, dan frontend bila risikonya lebih mudah direview terpisah.
- Rebase/merge strategy mengikuti repository maintainer; jangan menulis ulang
  shared history secara diam-diam.
- Jangan commit secret, production data, `.env`, dump, atau local artifact.
- Migration baru menggunakan nomor berikutnya dan nama domain; jangan edit atau
  rename migration `001`–`036`.
- Sebelum integrasi, jalankan quality gate dan pastikan docs/ADR tetap cocok
  dengan code yang akan direview.
- Deployment memakai reviewed immutable commit/tag, bukan nama branch yang
  bergerak sebagai bukti release.

CI saat ini berjalan pada pull request dan push ke `main`. Konfigurasi branch
protection di hosting Git tidak dapat disimpulkan dari repository dan harus
diverifikasi oleh maintainer.
