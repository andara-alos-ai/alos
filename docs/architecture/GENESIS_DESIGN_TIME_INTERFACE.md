# Pipeline Design-Time Genesis

| Metadata | Nilai |
|---|---|
| Status | Diimplementasikan untuk Synthetic UAT |
| Versi | 1.0.0 |
| Pembaruan terakhir | 30 Agustus 2026 |

## Tujuan dan Batas

Genesis membentuk tenaga kerja digital melalui kontrak yang sama dengan 18 Core Agent. Genesis bukan Core Agent ke-19, tidak mengubah struktur organisasi, tidak menulis konfigurasi production, dan tidak melakukan deployment.

Alur yang tersedia:

`source/specification → analyze → generate/resolve → validate → test → diff → business review → technical review → staging → release package`

Release Genesis adalah paket konfigurasi immutable dengan `production_effect=false`. Aktivasi ke production membutuhkan proses deployment dan persetujuan terpisah di luar Genesis.

## Source Registry

Setiap permintaan Genesis wajib memakai source reference yang terdaftar di `definitions/source-packs/`. Source pack menyimpan status, authority, permitted use, blocked use, versi, serta hash dokumen tanpa menyimpan isi dokumen eksternal di repository.

Source pack Master dan Lampiran A–N berstatus `DRAFT`. Source tersebut dapat dipakai untuk analisis, generate, validasi, test, dan diff, tetapi diblokir dari staging dan release sampai diratifikasi. Istilah `FINAL` pada nama berkas tidak mengubah status registry.

## Strategi

| Strategi | Hasil |
|---|---|
| `REUSE` | menggunakan versi agent yang sudah terdaftar tanpa mengubah kontraknya |
| `EXTEND` | menghasilkan candidate Sub-Agent/Sub-Sub-Agent yang mempertahankan capability dan tool base |
| `CREATE` | menghasilkan candidate baru melalui Agent Contract universal |

Candidate `EXTEND` dan `CREATE` wajib berstatus `DRAFT`. Genesis dilarang membuat atau mengubah Core Agent. Parent, hierarchy, versi, capability, tool, evidence, dan batas approval divalidasi sebelum review.

## Governance Gate

1. Pemohon tidak dapat mereview, melakukan staging, atau merilis permintaannya sendiri.
2. Review bisnis dilakukan Direktur atau Kepala Divisi.
3. Review teknis dilakukan IT Admin.
4. Staging hanya tersedia setelah dua gate menyetujui.
5. Staging juga mensyaratkan seluruh source berstatus minimal `APPROVED` dan mengizinkan `STAGE`.
6. Release package mensyaratkan source `RELEASED`, dilakukan Direktur, dan tidak mengaktifkan production.
7. Rejection pada salah satu gate menutup request; perubahan diajukan sebagai request baru.

Seluruh stage, review, actor, waktu, test result, diff, contract digest, dan release package disimpan di schema `genesis`. Isi package dilindungi trigger immutability. Separation-of-duties untuk pemohon, dua reviewer, pelaksana staging, dan releaser dijaga pada service serta constraint/trigger database.

## Hasil yang Dapat Digunakan

Direktur atau pemilik bisnis dapat memilih capability yang sudah ada, memperluas agent, atau mengajukan agent baru. Hasil akhirnya berupa konfigurasi berversi yang siap dipertimbangkan pada deployment terpisah—bukan aplikasi, database, atau microservice baru.
