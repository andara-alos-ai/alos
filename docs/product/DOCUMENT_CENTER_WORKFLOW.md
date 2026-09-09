# Document Center dan Genesis Draft Workflow

## Satu repositori kanonis

Navbar **Dokumen** adalah daftar resmi seluruh dokumen dalam workspace, baik
dibuat manual maupun berasal dari Genesis. Halaman **Genesis** hanya memfilter
dokumen dengan origin `GENESIS`; ia tidak menyimpan salinan kedua.

Setiap dokumen memiliki satu record, versi konten append-only, digest SHA-256,
owner, klasifikasi, status, checklist, dan jejak audit.

## Alur aman

```text
Genesis requirement atau dokumen manual
→ DRAFT
→ checklist otomatis + checklist human independen
→ IN_REVIEW
→ APPROVED atau REJECTED
```

`APPROVED` bukan `ACTIVE`. Publikasi/aktivasi dokumen dan penulisan kembali ke
Google Drive bukan bagian dari vertical slice ini dan harus memiliki gate
terpisah.

## Peran

- Maker: setiap pengguna dengan akses workspace dapat membuat DRAFT dan hanya
  pembuatnya yang dapat mengirim DRAFT untuk review.
- Checker: Director, Lead Divisi, IT Lead, Technical Reviewer, Business
  Reviewer, atau Wakil IT (`QA_SECURITY`). Pembuat DRAFT tidak dapat melengkapi
  checklist human miliknya sendiri.
- Approver: Director atau Lead Divisi. Approver juga harus berbeda dari maker.

## Checklist default

1. Metadata dokumen lengkap — otomatis.
2. Konten DRAFT tersedia dan memiliki digest — otomatis.
3. Evidence/sumber diperiksa atau dinyatakan tidak diperlukan — human.
4. Ruang lingkup serta owner dikonfirmasi — human.
5. Klasifikasi dan risiko ditinjau — human.

Semua checklist wajib harus `PASSED` sebelum maker dapat mengirim dokumen
untuk review. Setiap tindakan menghasilkan audit event tanpa menyimpan
credential, API key, atau dokumen Drive mentah.

## Batas Genesis saat ini

Genesis mencatat requirement dan menyiapkan kerangka DRAFT yang secara jelas
menandai bagian evidence, scope, dan risiko yang masih harus dilengkapi. Ia
tidak menyatakan kerangka itu sebagai analisis final, tidak mengesahkan
checklist, tidak menyetujui dokumen, serta tidak mempublikasikan atau menulis
ke Google Drive.
