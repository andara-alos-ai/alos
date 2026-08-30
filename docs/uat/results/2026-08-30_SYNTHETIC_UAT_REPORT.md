# Laporan UAT Sintetis ALOS Internal v1

| Metadata | Nilai |
|---|---|
| Tanggal | 30 Agustus 2026 |
| Ruang lingkup | Backend, database, worker, web production build, 18 Core Agent, enam workflow, LLM Gateway, dan Genesis |
| Data | Sintetis; tidak menggunakan data perusahaan asli |
| Hasil teknis | LULUS |
| Keputusan release candidate | LULUS |

## Ringkasan

Fondasi teknis ALOS Internal v1 memenuhi skenario UAT otomatis, smoke test aplikasi aktual, dan verifikasi container penuh. Tidak ditemukan defect kritis atau tinggi pada scope yang diuji. Release candidate berbasis data sintetis dapat dibentuk untuk proses review berikutnya.

## Hasil Skenario Utama

| ID | Skenario | Hasil | Bukti otomatis |
|---|---|---|---|
| UAT-01 | Sales: lead sampai reservasi | LULUS | `test_sales_workflow_is_persisted_from_lead_to_reservation` |
| UAT-02 | Keuangan: payment request sampai rekonsiliasi | LULUS | `test_payment_request_is_approved_paid_and_reconciled` |
| UAT-03 | Property: site evidence sampai KPI/CAPA | LULUS | `test_site_evidence_updates_kpi_or_opens_capa` |
| UAT-04 | Legal: izin dan kontrak sampai review manusia | LULUS | `test_permit_and_contract_reach_controlled_legal_review` |
| UAT-05 | HR: rekrutmen sampai checklist personalia | LULUS | `test_recruitment_decision_controls_personnel_checklist` |
| UAT-06 | AI Executive: fakta sistem sampai brief Direktur | LULUS | `test_system_facts_become_director_reviewed_executive_brief` |
| UAT-07 | Shared Runtime: setiap 18 Core Agent dieksekusi | LULUS | `test_each_of_18_core_agents_executes_through_shared_runtime` |
| UAT-08 | Genesis: review, staging, release immutable tanpa deployment | LULUS | `test_genesis_release_package_is_audited_immutable_and_not_deployed` |

Delapan skenario utama lulus pada PostgreSQL dan shared runtime. Seluruh transaksi uji menggunakan identitas, dokumen, nilai, serta referensi sintetis dan dibersihkan oleh fixture pengujian.

## Hasil Skenario Negatif

Dua belas skenario negatif lulus, meliputi:

- lead tanpa consent ditolak;
- role atau divisi yang tidak berwenang ditolak;
- auditor tidak dapat membuat exception;
- tool AI tidak dapat digunakan pada rule deterministik;
- tool di luar Agent Contract ditolak;
- payload agent yang memuat kredensial atau melebihi batas ditolak;
- data `RESTRICTED` diblokir sebelum panggilan LLM;
- keluaran LLM yang tidak sesuai schema gagal secara aman;
- pemohon Genesis tidak dapat mereview permintaannya sendiri;
- traversal path dokumen ditolak;
- token yang dimodifikasi ditolak.

## Smoke Test Aplikasi Aktual

| Pemeriksaan | Hasil |
|---|---|
| Docker Compose | PostgreSQL, migration job, API, worker, dan web berhasil dibangun serta dijalankan |
| API health | HTTP 200; environment `staging`; LLM `disabled` |
| OpenAPI | HTTP 200; kontrak API dapat dibaca |
| Authentication | mode staging menolak token lokal; integrasi IdP tetap menjadi gate sebelum penggunaan internal |
| Agent Registry API | 18 Core Agent |
| Workflow Registry API | 6 workflow |
| Web production build | HTTP 200 pada `/login` |
| Security header web | CSP aktif dan `X-Frame-Options: DENY` |
| Runtime user | API/worker menggunakan user `alos`; web menggunakan user `nextjs` |
| Worker | siklus berulang selesai dengan status `COMPLETED`; healthcheck heartbeat database sehat |
| Database | seluruh 23 migrasi diterapkan pada database baru; migration job keluar dengan kode 0 |

## Release Gate Otomatis

- 110 test backend termasuk PostgreSQL: lulus;
- 10 test web: lulus;
- Ruff, security lint source, mypy, ESLint, dan TypeScript: lulus;
- production build Next.js: lulus untuk 11 route;
- audit dependency Python dan web: tidak menemukan kerentanan yang diketahui;
- secret scan dan pemeriksaan whitespace Git: bersih.

## Defect dan Blocker

| ID | Severity | Temuan | Dampak | Tindakan |
|---|---|---|---|---|
| DEP-001 | Sedang | Build context tidak dapat membaca cache lokal pytest | build image terhenti | DITUTUP — cache pengembangan dikecualikan melalui `.dockerignore` |
| DEP-002 | Tinggi | Migration job pada image tidak menemukan repository root `/app` | schema tidak diterapkan pada database baru | DITUTUP — `ALOS_REPOSITORY_ROOT=/app` ditetapkan pada image dan Compose |
| DEP-003 | Sedang | Worker mewarisi healthcheck HTTP milik API | status worker tidak mencerminkan proses background | DITUTUP — healthcheck worker memakai heartbeat database |
| ENV-001 | Environment | Eksekusi Docker dari sandbox sempat ditolak | verifikasi container tertunda | DITUTUP — Docker Desktop/Engine terbukti aktif dan akses executable tervalidasi |

Seluruh temuan deployment di atas telah diperbaiki dan diuji ulang melalui build dari database baru. Tidak ada blocker teknis terbuka pada scope release candidate sintetis.

## Keputusan

Hasil teknis dinyatakan **LULUS** untuk pembentukan release candidate berbasis data sintetis. Status ini bukan persetujuan production, penggunaan data perusahaan asli, atau aktivasi integrasi eksternal. Integrasi identity provider, sign-off business owner enam divisi, Direktur Utama, IT, dan Security tetap menjadi gate sebelum pilot internal.
