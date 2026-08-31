# Laporan Verifikasi Teknis Tahap 5–6 ALOS

| Metadata | Nilai |
|---|---|
| Tanggal | 31 Agustus 2026 |
| Ruang lingkup | Controlled pilot readiness dan FLOW-003 sampai FLOW-006 |
| Data | Sintetis; tidak menggunakan data perusahaan asli |
| Hasil quality gate | LULUS |
| Sign-off bisnis | BELUM DILAKUKAN |
| Status | Kandidat controlled pilot; bukan production approval |

## Hasil Implementasi

- profil readiness pilot terversi dan tidak memiliki efek production;
- lifecycle proyek `DRAFT → ACTIVE → ON_HOLD/CLOSED` deterministik dan diaudit;
- aktivasi status proyek hanya dapat diputuskan Direktur Utama;
- kelengkapan role, divisi, project assignment, separation of duties, agent, workflow, evidence, worker, dead-letter, dan kontrol environment dapat diperiksa dari ALOS;
- fixture pilot hanya memakai identitas `example.test` dan alias sintetis;
- backup memiliki manifest SHA-256 dan restore drill berjalan pada database terisolasi;
- layar transaksi Property, Legal, HR, dan AI Executive memakai API serta data sistem nyata;
- kepala divisi dapat mengajukan dan hanya membaca permintaan rekrutmen divisinya; HR dapat memproses seluruh permintaan dalam project scope.

## Skenario Tahap 6

| ID | Skenario | Hasil teknis | Kontrol utama |
|---|---|---|---|
| FLOW-003 | Site Evidence → TPA → KDA/CRA | LULUS | reviewer terpisah, variance deterministik, KPI atau CAPA |
| FLOW-004 | Permit/Contract → LPA/CLA → Legal Human | LULUS | sumber, evidence, keputusan manusia, exception |
| FLOW-005 | Recruitment → HRA → HR Human → HPA | LULUS | scope divisi, sanitasi kandidat, SoD, checklist personalia |
| FLOW-006 | KDA/CRA/ARA → MCA → Direktur | LULUS | snapshot sistem, lineage, review dan publish Direktur |

## Quality Gate

| Pemeriksaan | Hasil |
|---|---|
| Backend termasuk PostgreSQL | 148 test lulus |
| Web unit test | 21 test lulus |
| Ruff dan security lint | Lulus |
| mypy strict | Lulus pada 92 source files |
| ESLint dan TypeScript | Lulus |
| Next.js production build | Lulus untuk 19 route |
| Agent Registry | 18 Core Agent valid |
| Source Registry | 3 pack dan 17 source valid |
| Canonical Configuration | 1 register dan 16 mapping valid |
| Audit dependency Python/web | Tidak ada kerentanan yang diketahui |

## Batas Penerimaan

Verifikasi ini membuktikan implementasi dan kontrol teknis, bukan kesesuaian final SOP, KPI, authority matrix, RTO/RPO, atau data perusahaan. Controlled pilot belum boleh dibuka sampai readiness proyek aktual tidak memiliki blocker, backup/restore drill memiliki evidence, dan UAT manusia ditandatangani oleh owner terkait.
