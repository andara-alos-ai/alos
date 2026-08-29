# Register Keputusan Arsitektur ALOS

| Metadata | Nilai |
|---|---|
| Status | Aktif untuk Dasar Pilot |
| Versi | 0.1.0 |
| Pembaruan terakhir | 29 Agustus 2026 |

## 1. Tujuan

Register ini mencatat keputusan arsitektur yang membentuk ALOS Internal v1. Setiap keputusan dapat digantikan oleh keputusan baru, tetapi riwayat dan alasan sebelumnya tidak dihapus.

Status keputusan: `PROPOSED`, `ACCEPTED`, `SUPERSEDED`, atau `REJECTED`.

## ADR-001 — Monorepo Privat

**Status:** `ACCEPTED`

**Konteks:** aplikasi web, backend, definisi agent, alur kerja, migrasi, pengujian, dan deployment berubah bersama selama tahap awal.

**Keputusan:** seluruh komponen pilot dikelola dalam satu repository privat pada GitHub Organization.

**Konsekuensi:** perubahan lintas komponen dapat direview dan diuji atomik. Repository membutuhkan batas folder, pemilik kode, CI selektif, dan perlindungan branch. Pemisahan repository hanya dilakukan ketika kepemilikan dan siklus rilis benar-benar independen.

## ADR-002 — Monolit Modular

**Status:** `ACCEPTED`

**Konteks:** microservice dini menambah kontrak jaringan, deployment, observabilitas, dan operasi sebelum terdapat kebutuhan skala.

**Keputusan:** backend dibangun sebagai monolit modular yang dapat menjalankan proses API, worker, dan scheduler dari basis kode bersama.

**Konsekuensi:** transaksi dan pengembangan lebih sederhana, tetapi batas modul harus ditegakkan melalui struktur kode, antarmuka, kepemilikan skema, dan pengujian arsitektur.

## ADR-003 — Lingkungan Eksekusi Agent Bersama

**Status:** `ACCEPTED`

**Konteks:** 18 Core Agent merupakan peran logis dengan banyak kemampuan bersama.

**Keputusan:** seluruh Core Agent dijalankan dalam satu lingkungan eksekusi bersama menggunakan definisi berversi, pustaka kemampuan, kebijakan alat, dan catatan eksekusi yang sama.

**Konsekuensi:** tidak ada aplikasi, database, atau microservice per agent. Isolasi diterapkan melalui kontrak, izin, versi, antrean, batas sumber daya, dan kill switch.

## ADR-004 — Aturan Deterministik di Luar LLM

**Status:** `ACCEPTED`

**Konteks:** izin, tenggat, transisi, routing persetujuan, aritmetika, dan audit harus konsisten serta dapat diuji.

**Keputusan:** aturan tersebut diimplementasikan melalui domain, state machine, dan mesin tata kelola. LLM dibatasi pada tugas non-deterministik yang disebutkan kontrak agent.

**Konsekuensi:** prompt tidak menjadi tempat aturan bisnis resmi. Setiap perubahan aturan memerlukan definisi, versi, dan pengujian.

## ADR-005 — Genesis Terpisah dari Produksi

**Status:** `ACCEPTED`

**Konteks:** perubahan agent dan alur kerja dapat memengaruhi kewenangan dan operasi perusahaan.

**Keputusan:** Genesis beroperasi pada tahap desain melalui sumber, analisis, pembuatan usulan, validasi, pengujian, selisih, review manusia, staging, dan rilis.

**Konsekuensi:** Genesis bukan Core Agent ke-19 dan tidak dapat mengubah produksi atau struktur organisasi langsung. Rilis membutuhkan identitas manusia yang berwenang.

## ADR-006 — Satu PostgreSQL dengan Skema Logis

**Status:** `ACCEPTED`

**Konteks:** domain memerlukan transaksi konsisten dan operasi pilot yang sederhana tanpa kehilangan batas kepemilikan.

**Keputusan:** gunakan satu PostgreSQL dengan skema logis per kelompok tanggung jawab serta satu penyimpanan objek untuk isi dokumen/bukti.

**Konsekuensi:** tidak ada database per agent/divisi. Modul hanya menulis data miliknya; pertukaran lintas domain memakai antarmuka atau kejadian. Pemisahan fisik dievaluasi jika muncul kebutuhan keamanan, skala, atau ketersediaan.

## ADR-007 — Integrasi Netral Vendor

**Status:** `ACCEPTED`

**Konteks:** vendor CRM, akuntansi, bank, penyimpanan, identitas, dan LLM belum disahkan.

**Keputusan:** domain bergantung pada kontrak kemampuan, sedangkan adaptor vendor berada di Gerbang Integrasi.

**Konsekuensi:** vendor dapat diganti tanpa menulis ulang domain. Setiap adaptor memerlukan pemetaan, kredensial terbatas, idempotensi, observabilitas, keamanan, dan contract test.

## ADR-008 — Alur Kerja Pilot Berbasis PostgreSQL

**Status:** `ACCEPTED`

**Konteks:** pilot membutuhkan alur tahan restart, timer, retry, dan audit, tetapi belum memiliki bukti kebutuhan platform orkestrasi terpisah.

**Keputusan:** simpan status alur, timer, lease, percobaan, dan outbox di PostgreSQL serta jalankan melalui worker/scheduler.

**Konsekuensi:** implementasi awal lebih sederhana. Teknologi khusus seperti Temporal hanya dievaluasi berdasarkan kompleksitas, volume, dan kebutuhan operasi yang terukur.

## ADR-009 — Data Sintetis/Sanitasi untuk Pilot

**Status:** `ACCEPTED`

**Konteks:** klasifikasi, retensi, penyedia AI, dan matriks akses data perusahaan belum disahkan.

**Keputusan:** pilot hanya menggunakan data sintetis atau data yang telah disanitasi dan disetujui.

**Konsekuensi:** validasi teknis dapat berjalan tanpa mempertaruhkan data perusahaan. Uji dengan data asli menunggu kebijakan, kontrol, dan persetujuan formal.

## ADR-010 — Web App sebagai Antarmuka Operasional

**Status:** `ACCEPTED`

**Konteks:** ALOS ditujukan untuk menyelesaikan pekerjaan, bukan hanya menyajikan analitik atau percakapan.

**Keputusan:** aplikasi web dengan ruang kerja, formulir, antrean, approval, bukti, penyimpangan, dan audit menjadi antarmuka utama. Chat dan BI hanya menjadi pendukung.

**Konsekuensi:** setiap kemampuan agent harus terhubung ke objek kerja dan status sistem. Keluaran percakapan tanpa tindak lanjut terstruktur tidak dianggap implementasi workflow.

## ADR-011 — Stack Teknis Pilot

**Status:** `ACCEPTED`

**Konteks:** target dua minggu membutuhkan teknologi yang matang, mudah diuji, mendukung AI/document processing, dan tetap sederhana untuk satu tim.

**Keputusan:** aplikasi web menggunakan Next.js dan TypeScript; backend modular, workflow, serta shared Agent Runtime menggunakan FastAPI dan Python; database menggunakan PostgreSQL. Versi dependency dikunci melalui `pnpm-lock.yaml` dan environment Python terisolasi. Dokumen pilot memakai adaptor filesystem lokal; penyimpanan objek produksi tetap berada di balik kontrak netral vendor.

**Konsekuensi:** frontend dan backend dapat berkembang secara independen dalam satu monorepo tanpa menjadi microservice per agent. Pemilihan penyedia object storage, identitas, LLM, dan hosting produksi tetap memerlukan evaluasi serta persetujuan terpisah.

## ADR-012 — Object Storage Netral Vendor

**Status:** `ACCEPTED`

**Konteks:** dokumen dan evidence memerlukan isi berkas nyata, versioning, integritas,
kontrol akses, dan jalur migrasi tanpa mengunci domain pada satu produk storage.

**Keputusan:** modul dokumen bergantung pada kontrak object storage. Local/test memakai
filesystem terisolasi; production memakai API S3 atau S3-compatible yang disahkan. Server
menghasilkan object key, hash, ukuran, dan metadata versi. Database tetap menjadi sumber
relasi dan otorisasi, sedangkan bucket menyimpan isi immutable.

**Konsekuensi:** pemilihan AWS S3 atau layanan compatible lain tidak mengubah workflow.
Production wajib memakai bucket private terenkripsi, HTTPS, kredensial minimum, malware
scan, backup, lifecycle, dan uji pemulihan. Produk server tertentu tidak menjadi dependency
inti repository; vendor dan lokasi hosting tetap `TBD` sampai review deployment.

## 2. Keputusan yang Belum Dibuat

Keputusan berikut tetap `PROPOSED/TBD`: penyedia identitas, LLM, hosting produksi, observability backend, target layanan, vendor integrasi, strategi analitik, dan teknologi orkestrasi setelah pilot. Keputusan baru wajib mencatat konteks, alternatif, alasan, dampak keamanan/data, konsekuensi, dan rencana migrasi.
