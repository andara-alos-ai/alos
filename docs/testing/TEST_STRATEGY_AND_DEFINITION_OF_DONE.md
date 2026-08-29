# Strategi Pengujian dan Definisi Selesai ALOS

| Metadata | Nilai |
|---|---|
| Status | Rancangan untuk Pilot Internal |
| Versi | 0.1.0 |
| Cakupan | ALOS Internal Agent Pilot v0.1 |
| Pembaruan terakhir | 29 Agustus 2026 |

## 1. Tujuan

Strategi ini memastikan ALOS tidak hanya menghasilkan keluaran AI yang terlihat benar, tetapi juga menegakkan izin, status, bukti, persetujuan, ketahanan proses, dan audit secara konsisten.

## 2. Prinsip Pengujian

- kontrol material diuji pada lapisan domain/API, bukan hanya antarmuka;
- aturan deterministik memiliki hasil yang sama untuk masukan yang sama;
- keluaran AI dinilai dengan data regresi dan review, bukan exact match semata;
- skenario gagal dan penyalahgunaan memiliki bobot yang sama dengan skenario normal;
- pengujian tidak menggunakan data perusahaan asli;
- setiap cacat kritis harus dapat direproduksi menjadi pengujian otomatis;
- hasil CI menjadi syarat rilis definisi dan aplikasi.

## 3. Lapisan Pengujian

| Lapisan | Fokus | Contoh |
|---|---|---|
| Unit | fungsi kecil deterministik | perhitungan, validasi, pemetaan status |
| Domain | invariant dan siklus agregat | SoD, penutupan CAPA, perubahan versi |
| Tata Kelola | akses dan kontrol | role salah, bukti kurang, approval kedaluwarsa |
| Alur Kerja | langkah, timer, retry, resume | proses pulih setelah worker dimulai ulang |
| Kontrak | skema agent, kejadian, alat, API | definisi tanpa bidang wajib ditolak |
| Integrasi | database, objek, adaptor sandbox | idempotensi webhook dan outbox |
| Regresi Agent | kualitas keluaran AI | ekstraksi invoice, klausul, ringkasan |
| Keamanan | penyalahgunaan dan kebocoran | akses lintas proyek, prompt injection, secret scan |
| Ujung-ke-Ujung | perjalanan pengguna | enam alur dari pemicu sampai status akhir |
| Kinerja | batas kapasitas pilot | antrean, unggahan, latensi agent, konkurensi |

Antarmuka web memiliki unit test untuk katalog, pemetaan navigasi berbasis role, dan format
data. Gate frontend menjalankan lint React, pemeriksaan tipe TypeScript, unit test, serta
production build. Smoke test browser lokal memverifikasi redirect sesi, login pilot,
dashboard berbasis API, halaman operasional, tidak adanya error console, dan sidebar responsif.

## 4. Data Pengujian

Data uji berada di `tests/fixtures/synthetic/` atau dihasilkan saat pengujian. Paket data mencakup kasus normal, batas, hilang, duplikat, bertentangan, kedaluwarsa, berbahaya, dan tidak berizin. Setiap fixture memiliki tujuan, hasil yang diharapkan, klasifikasi, dan versi.

Dokumen regresi tidak boleh mengandung nama, nomor identitas, rekening, kontrak, atau transaksi nyata.

## 5. Pengujian Agent

Setiap Core Agent wajib diuji untuk:

- validasi kontrak dan masukan;
- pembatasan kemampuan dan alat;
- validasi skema keluaran;
- sumber dan bukti;
- hasil ketika data kurang atau bertentangan;
- ambang review manusia;
- timeout, retry, pembatalan, dan idempotensi;
- larangan tindakan;
- audit versi model, prompt, agent, dan alat;
- regresi kualitas antarversi.

Penilaian AI menggunakan bidang terstruktur, cakupan fakta, akurasi sumber, temuan wajib, halusinasi, dan tingkat koreksi manusia. Nilai ambang kualitas per agent ditetapkan pada kontrak dan dapat berstatus pilot sebelum disahkan.

## 6. Skenario Negatif Wajib

1. pemohon mencoba menyetujui pekerjaannya sendiri;
2. pengguna mengakses proyek atau divisi di luar cakupan;
3. bukti wajib kurang atau hash tidak cocok;
4. data sumber sudah kedaluwarsa atau bertentangan;
5. perintah dan webhook dikirim ulang;
6. worker berhenti di tengah alur dan kemudian dimulai ulang;
7. agent menghasilkan keluaran yang tidak sesuai skema;
8. dokumen berisi instruksi untuk mengabaikan kebijakan;
9. alat mencoba operasi yang tidak diizinkan;
10. persetujuan digunakan setelah data material berubah;
11. laporan atau audit yang sudah final dicoba diubah;
12. nilai konfigurasi material masih `TBD` tetapi proses dipaksa lanjut.
13. IT Admin mencoba mengambil atau membaca pekerjaan divisi bisnis;
14. owner CAPA mencoba menutup dan memverifikasi pekerjaannya sendiri;
15. scheduler deadline dijalankan ulang dan menghasilkan reminder duplikat pada level sama.

Setiap skenario harus menghasilkan penolakan aman, status yang tepat, pesan yang dapat ditindaklanjuti, dan audit.

## 7. Pengujian Enam Alur

| Alur | Bukti penerimaan minimum |
|---|---|
| Lead ke Reservasi | deduplikasi, penugasan, consent, follow-up, SLA, dan terminal status |
| Permintaan Pembayaran | ekstraksi, bukti, anggaran, SoD, approval, tindakan manusia, rekonsiliasi |
| Bukti Lapangan | metadata, progres, variance, KPI, penyimpangan, CAPA |
| Izin dan Kontrak | versi dokumen, ekstraksi, perbandingan, Legal Human review |
| Rekrutmen | persetujuan kebutuhan, screening terbatas, review manusia, berkas |
| Ringkasan Eksekutif | seluruh klaim berasal dari record sistem dan akses terbatas diterapkan |

## 8. Gerbang CI

Pull request tidak dapat digabung jika gagal pada format/lint, pemeriksaan tipe, unit/domain/governance test, validasi definisi agent dan alur, pemeriksaan migrasi, contract test, secret scan, dependency/security scan, build, atau skenario ujung-ke-ujung kritis yang ditentukan.

Rilis staging menambahkan agent regression, pengujian keamanan, pengujian backup/restore, dan smoke test deployment.

## 9. Tingkat Keparahan Cacat

| Tingkat | Definisi | Keputusan rilis |
|---|---|---|
| Kritis | kebocoran data, bypass izin/approval, korupsi data, audit dapat diubah | rilis diblokir |
| Tinggi | alur utama gagal, hasil material salah tanpa blokir, kehilangan bukti | rilis diblokir |
| Sedang | fungsi penting terganggu dengan jalan keluar aman | wajib ada keputusan penerimaan risiko |
| Rendah | masalah tampilan atau kenyamanan tanpa dampak kontrol | dapat dijadwalkan |

## 10. UAT Pilot

UAT dilakukan oleh perwakilan enam divisi dan pengguna eksekutif menggunakan data sintetis. Setiap skenario mencatat aktor, langkah, hasil harapan, hasil aktual, bukti, temuan, tingkat keparahan, dan keputusan penerimaan. Reviewer bisnis memastikan istilah, pekerjaan, dan batas agent dapat dipahami serta sesuai konteks divisinya.

## 11. Definisi Selesai untuk Perubahan

Satu perubahan dianggap selesai jika:

- kebutuhan dan acceptance criteria jelas;
- kode/definisi telah direview oleh pemilik yang sesuai;
- migrasi dan dokumentasi diperbarui jika terdampak;
- pengujian positif dan negatif lulus;
- keamanan, data, audit, dan observabilitas telah diperiksa;
- tidak ada rahasia atau data nyata masuk repository;
- deployment dapat dilakukan ulang;
- keterbatasan dan `TBD` tercatat.

## 12. Definisi Selesai Agent

Agent dianggap siap pilot jika kontraknya lengkap, definisinya valid, kemampuan dan alat dibatasi, satu kasus penggunaan nyata berjalan, keluaran terstruktur memiliki sumber, review manusia berfungsi, skenario kegagalan aman, metrik tersedia, dan penghentian darurat teruji.

## 13. Definisi Selesai Alur Kerja

Alur dianggap siap pilot jika dapat dimulai oleh aktor sah, bertahan dari restart, menolak transisi ilegal, menangani timeout/duplikasi, menegakkan bukti/approval, membuat penyimpangan ketika perlu, mencapai status akhir, dan memiliki audit ujung-ke-ujung.

## 14. Definisi Selesai Pilot

Definisi Selesai pilot mengikuti sepuluh kriteria pada rencana implementasi. Tambahan gerbang rilis:

- tidak ada cacat kritis atau tinggi terbuka;
- enam skenario UAT utama diterima;
- seluruh 18 agent lolos validasi dan kasus penggunaan pilot;
- backup/restore, kill switch, dan pemulihan worker telah diuji;
- daftar risiko, batas, dan keputusan `TBD` disetujui untuk pilot.

Pilot yang selesai belum otomatis layak produksi. Kesiapan produksi memerlukan data asli yang telah diatur, keamanan dan privasi formal, integrasi produksi, target layanan, prosedur insiden, pemulihan bencana, serta persetujuan manajemen.
