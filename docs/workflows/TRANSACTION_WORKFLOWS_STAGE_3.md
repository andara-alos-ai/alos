# Workflow Transaksi ALOS

Dokumen ini menjelaskan working baseline untuk dua workflow transaksi tahap 3. Seluruh
contoh menggunakan profil dan data sintetis `@example.test`; jangan memasukkan data
perusahaan asli ke environment lokal atau test.

## Sales & Marketing — FLOW-001

1. Sales membuat lead pada project yang dapat diakses melalui `POST /api/v1/leads`.
2. SLA melakukan validasi field, consent, dan routing melalui Agent Registry serta shared
   Agent Runtime. Deduplikasi kontak ditegakkan oleh rule dan constraint database.
3. Sales Human menerima assignment dan menentukan follow-up pertama melalui
   `POST /api/v1/workflow-runs/{run_id}/sales-assignment`.
4. CFA membuat follow-up task dan reminder. Interaksi berikutnya dicatat melalui
   `POST /api/v1/workflow-runs/{run_id}/interactions`.
5. Outcome deterministik adalah `follow_up`, `qualified`, `reserved`, `lost`, atau
   `exception`. Qualified tetap berada di pipeline sehingga dapat dilanjutkan ke reservasi.
6. Reservasi wajib memiliki referensi, tanggal, dan document evidence. Lost wajib memiliki
   lost reason.

Queue personal/divisi tersedia pada `/api/v1/operations/work-queue`; reminder ada pada
`/api/v1/operations/reminders`. Semua mutasi material membutuhkan `Idempotency-Key` dan
menulis audit entry.

## Keuangan — FLOW-002

1. Finance membuat budget aktif dan payment request berisi project, budget, dokumen utama,
   vendor/payee, kategori, nominal, currency, dan due date.
2. DIA, CEA, BCA, dan ARA dijalankan melalui shared Agent Runtime. DIA memvalidasi metadata
   dokumen dari fakta server tanpa LLM; hasil document, evidence, budget, dan approval-route
   disimpan pada `finance.payment_checks`.
3. Kategori yang diterima server adalah `GENERAL`, `MATERIAL`, `OPERATIONS`, `CONTRACTOR`,
   dan `TAX`. Evidence tambahan wajib untuk kategori `TAX` dan `CONTRACTOR`.
   Dokumen utama, evidence tambahan, bukti pembayaran, dan dokumen revisi harus berada
   pada organisasi, project, dan scope divisi Finance yang sama (atau berstatus shared),
   tidak ditolak pada verifikasi, serta memiliki scan status `NOT_CONFIGURED` atau `CLEAN`.
4. Routing ARA bersifat deterministik dan dibaca dari policy registry berversi. Baseline
   berikut hanya aktif sebagai konfigurasi pilot sampai diratifikasi pemilik bisnis:

   - sampai IDR 25.000.000: `FINANCE_REVIEWER`, SLA 24 jam;
   - di atas IDR 25.000.000 sampai IDR 250.000.000: `FINANCE_HEAD`, SLA 12 jam;
   - di atas IDR 250.000.000: `DIRECTOR`, SLA 8 jam.

   Sumber konfigurasi aktif berada pada
   `definitions/policies/approval-levels/payment-request.json`; kode runtime dan database
   tidak menyimpan salinan threshold tersebut.

5. Approver tidak boleh sama dengan requester. Keputusan yang sah adalah approve, reject,
   atau return for revision. Requester dapat memperbaiki lalu resubmit; requester, Kepala
   Finance, atau Direktur dapat membatalkan sebelum pembayaran tercatat.
6. Finance Human mencatat pembayaran beserta document evidence. FRA mencocokkan reference,
   amount, dan currency secara deterministik. Selisih membuka exception.

Deadline work item berpindah mengikuti langkah aktif: SLA approval sesuai route, tanggal
pembayaran yang diminta untuk payment action, 24 jam untuk reconciliation, 48 jam untuk
revision, dan 24 jam untuk penanganan exception. Worker memakai deadline tersebut untuk
reminder, overdue, serta escalation berulang.

Migration `033_transaction_workflow_backfill.sql` membawa payment request sintetis yang
sudah ada sebelum tahap 3 ke model route/evidence baru secara deterministik. Migration
`034_transaction_integrity_hardening.sql` membatasi kategori pembayaran, menyelaraskan
kontrak qualification Sales, dan memperbaiki hasil check/evidence lama dari sumber transaksi
otoritatif. Migration `035_transaction_reference_isolation.sql` membuat reference reservasi,
pembayaran, dan rekonsiliasi unik dalam organisasi masing-masing agar tenant tidak saling
menyebabkan collision. Migration tersebut tidak membuat ulang transaksi dan aman dijalankan
melalui migration runner yang idempoten.

`Idempotency-Key` divalidasi bersama hash payload dan dikunci per organisasi/operasi/key di
dalam transaksi. Request paralel dengan key dan payload yang sama mengembalikan transaksi
yang sama; penggunaan ulang key dengan payload berbeda ditolak.

## Menjalankan lokal

```powershell
python -m alos.persistence.migrations
python -m uvicorn alos.main:app --app-dir services/platform/src --reload --port 8000
pnpm dev:web
```

Provisioning sintetis dapat diulang tanpa duplikasi:

```powershell
.\scripts\development\provision-controlled-pilot.ps1
```

## Verifikasi

```powershell
$env:ALOS_RUN_POSTGRES_TESTS='1'
python -m pytest services/platform/tests
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Manual smoke test: login sebagai profil Sales, selesaikan lead sampai reservation; kemudian
login sebagai Finance A untuk membuat request, Finance B untuk approval/payment, dan jalankan
reconciliation. Gunakan halaman Work Queue, Risks, Approvals, dan Governance untuk memeriksa
assignment, reminder, exception, evidence, dan audit.

Untuk routing, gunakan nominal sintetis hingga IDR 25 juta untuk Finance Reviewer, di atas
IDR 25 juta untuk Kepala Finance, dan di atas IDR 250 juta untuk Direktur. Uji pula return for
revision, TAX tanpa evidence tambahan, lost reason Sales, dan reconciliation reference yang
berbeda agar jalur exception dapat diverifikasi.
