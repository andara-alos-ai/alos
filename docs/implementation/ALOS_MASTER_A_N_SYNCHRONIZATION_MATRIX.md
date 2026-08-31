# Matriks Sinkronisasi Master ALOS GIIVEPRO dan Lampiran A–N

| Metadata | Nilai |
|---|---|
| Status | Working Baseline / Belum Diratifikasi |
| Versi sinkronisasi | 0.1.0 |
| Tanggal dokumen sumber | 31 Agustus 2026 |
| Ruang lingkup | Master dan Lampiran A–N |
| Efek produksi | Tidak ada |

## 1. Keputusan Pengendalian

Nama file dan metadata `FINAL` pada dokumen sumber tidak menetapkan status rilis di ALOS. Berdasarkan keputusan pengguna, seluruh isi dokumen diperlakukan sebagai `DRAFT/DESIGN_BASELINE`, kecuali struktur organisasi berikut:

`DIREKTUR UTAMA -> AI EXECUTIVE OPERATING LAYER -> KEUANGAN, SALES & MARKETING, PROPERTY, HR, LEGAL, IT`

Source pack kanonik berada di `definitions/source-packs/alos-master-an-draft/source-pack.json`. Hash SHA-256 mengidentifikasi tepat berkas yang telah direview, tanpa menyalin isi dokumen atau data perusahaan ke repository.

Source pack dapat digunakan untuk `ANALYZE`, `GENERATE`, `VALIDATE`, `TEST`, dan `DIFF`. Source pack tidak dapat digunakan untuk `STAGE`, `RELEASE`, atau aktivasi produksi sebelum ratifikasi dan penerbitan versi baru.

Pemetaan kanonik seluruh sumber berada di
`definitions/configuration/alos-master-an/register.json`. Register ini memisahkan struktur
organisasi yang telah `APPROVED` dari authority, SOP, KPI, workflow, data, dan nilai bisnis
lain yang masih `DRAFT` atau `HOLD`. Register tidak memiliki efek produksi.

## 2. Matriks A–N

| Sumber | Isi utama | Kondisi implementasi | Keputusan |
|---|---|---|---|
| Master | arsitektur ALOS, GIIVEPRO, Genesis, governance dan lifecycle | konsep inti selaras | `REUSE`; perluasan dilakukan bertahap |
| A | sumber, hierarki, status dan rekonsiliasi | source governance sebelumnya masih dokumenter | `EXTEND`; Source Registry diterapkan |
| B | organisasi, kewenangan, RACI, SoD dan delegasi | struktur terkunci sudah sesuai; named assignment belum final | `HOLD`; jangan hard-code nama atau delegasi |
| C | 135 SOP dan dua prosedur integrasi | enam workflow pilot tersedia; katalog SOP belum dinormalisasi | `EXTEND`; SOP menjadi konfigurasi/Sub-Agent |
| D | target dan Renstra | belum menjadi data kanonik | `HOLD`; angka menunggu ratifikasi |
| E | KPI divisi dan agent | fondasi KPI tersedia sebagian | `EXTEND`; rumus/target/owner menunggu ratifikasi |
| F | sepuluh workflow, handoff, G1–G8 dan state minimum | enam workflow pilot berjalan | `EXTEND`; empat workflow tambahan tetap planned |
| G | evidence, form, retention dan Product Truth Package | evidence berversi tersedia; registry domain belum lengkap | `EXTEND`; retention menunggu Legal/IT |
| H | kompetensi dan penilaian HR | recruitment/personnel foundation tersedia | `EXTEND`; keputusan ketenagakerjaan wajib manusia |
| I | 18 Core, legacy, 17/72/260 GIIVEPRO | 18 Core dan shared runtime sudah sesuai | `REUSE`; 17/72/260 tetap candidate lineage |
| J | approval, L0–L3, G1–G8 dan decision record | approval, SoD dan audit dasar tersedia | `EXTEND`; nominal materiality belum diaktifkan |
| K | data dictionary, ownership dan fact status | schema domain tersedia sebagian | `EXTEND`; canonical dictionary menjadi tahap berikutnya |
| L | model bisnis dan tenant GIIVEPRO | tenant isolation foundation tersedia | `HOLD/EXTEND`; pricing dan regulated capability belum final |
| M | rekonsiliasi keuangan dan transaction hold | FLOW-002 berjalan dengan data sintetis | `HOLD`; actual wajib primary evidence |
| N | UAT, release, monitoring dan rollback | synthetic UAT dan release isolation tersedia | `EXTEND`; SLO/RTO/RPO dan go-live belum disahkan |

## 3. Pemetaan Portfolio Workflow

| Workflow enterprise | Implementasi saat ini | Status |
|---|---|---|
| WF-01 Land-to-Feasibility | belum memiliki workflow executable | `PLANNED` |
| WF-02 Feasibility-to-Project | belum memiliki workflow executable | `PLANNED` |
| WF-03 Lead-to-Cash | `FLOW-001` Lead-to-Reservation | `PARTIAL/STAGED` |
| WF-04 RAB-to-Payment | `FLOW-002` Payment-to-Reconciliation | `PARTIAL/STAGED` |
| WF-05 Site Progress | `FLOW-003` Site Evidence | `PARTIAL/STAGED` |
| WF-06 Permit and Contract | `FLOW-004` Permit/Contract | `PARTIAL/STAGED` |
| WF-07 Exception-to-CAPA | capability lintas workflow tersedia | `PLANNED AS STANDALONE` |
| WF-08 Report Approval | `FLOW-006` AI Executive Brief | `PARTIAL/STAGED` |
| WF-HR HR Lifecycle | `FLOW-005` Recruitment | `PARTIAL/STAGED` |
| WF-IT IT Delivery | worker/release foundation tersedia | `PLANNED` |

Registry tidak lagi membatasi jumlah workflow tepat enam. Enam ID pilot tetap wajib tersedia. Workflow tambahan belum boleh dijalankan sebelum memiliki graph, owner, evidence, governance gate, test, versi, dan status minimal `STAGED`.

## 4. Implikasi terhadap Genesis

- Genesis hanya menerima source reference yang terdaftar pada Source Registry.
- Dokumen A–N dapat dianalisis untuk usulan `REUSE`, `EXTEND`, atau `CREATE`.
- Source pack `DRAFT` tidak dapat memasuki staging atau release package.
- Release package Genesis tetap `production_effect=false` dan tidak melakukan deployment.
- Item GIIVEPRO tidak dibuat hanya untuk memenuhi jumlah; kontrak lengkap dan kebutuhan bisnis tetap wajib.
- Selisih klaim 73 dengan 72 Sub-Agent teridentifikasi dicatat sebagai open source gap, bukan diisi dengan asumsi.

## 5. Kondisi Keluar Tahap Sinkronisasi

Tahap ini selesai apabila source pack dan canonical configuration register dapat divalidasi,
seluruh hash, owner, lineage, status, disposition, dan decision blocker terbaca, referensi
tidak dikenal ditolak, source draft terblokir dari staging/release, enam workflow pilot tetap
valid, dan seluruh quality gate repository lulus.
