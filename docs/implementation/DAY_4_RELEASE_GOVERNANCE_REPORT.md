# Hari 4 — Release Governance Report

## Hasil

H4 menerapkan jalur lifecycle untuk satu Agent Contract tanpa membuat service
atau database baru:

```text
DRAFT → TESTED → IN_REVIEW → APPROVED → RELEASED → ACTIVE
                                            → SUSPENDED → ROLLED_BACK
```

Setiap transition menyimpan event sequence, actor manusia, reason, correlation
ID, dan audit event. Urutan event tidak bergantung pada timestamp saja sehingga
riwayat dapat direplay secara deterministik.

## Kontrol yang diterapkan

- Genesis Designer hanya membuat Blueprint/Agent Contract `DRAFT`; default-nya
  low-risk, read-only, tanpa tool atau permission, dan tetap memerlukan
  approval manusia.
- Maker hanya dapat mendaftarkan test case. Checker harus berbeda dari maker.
- Satu reviewer business dan satu reviewer technical harus berbeda dari maker,
  checker, dan satu sama lain. Approver juga harus independen.
- Positive, negative, dan regression test harus PASS serta ada Agent Run
  berhasil sebelum request masuk review.
- Release dan activation hanya mengikuti dua review approval serta approval
  manusia yang terekam.
- Kill switch membatalkan active version dan memblokir Agent Run berikutnya.
  Kill switch harus dibersihkan eksplisit sebelum rollback.
- Rollback hanya dapat memilih versi lain dari Agent Contract yang telah
  released sebelumnya. Tidak ada rollback ke draft.
- Setiap aksi lifecycle mengonfirmasi membership workspace; role dicek pada
  lapisan API.
- Endpoint local-only `POST /api/v1/local/release-review-team` menyiapkan lima
  identitas test terpisah beserta token masing-masing untuk maker, checker,
  business reviewer, technical reviewer, dan approver. Endpoint ini ditolak di
  luar environment `local`/`test`.
- Runtime lokal memprioritaskan draft terbaru untuk test release. Bila tidak
  ada draft tertunda, ia menjalankan versi `ACTIVE` yang ditunjuk Agent Registry.

## Evidence quality gate

`test_release_governance_postgres.py` menjalankan database PostgreSQL sementara
dan provider palsu. Test membuktikan lifecycle penuh, SoD, workspace denial,
tool/runtime denial saat kill switch aktif, clear kill switch, dan rollback ke
versi released sebelumnya. Tidak ada Gemini call, secret, atau data perusahaan
dalam test tersebut.

## HOLD yang disengaja

- Staging VPS, snapshot staging, HTTPS, dan OpenAI belum diaktifkan.
- End-to-end provider nyata untuk release workflow belum dijalankan agar tidak
  mengonsumsi kuota Gemini atau mengubah lifecycle agent lokal tanpa approval
  eksplisit.
- Local token dan review team hanya untuk development. Provisioning
  user/reviewer produksi dan identity provider tetap pekerjaan staging.
- Scheduler dan execution active pada staging masih HOLD sampai policy provider
  OpenAI dan identity reviewer produksi tersedia.
