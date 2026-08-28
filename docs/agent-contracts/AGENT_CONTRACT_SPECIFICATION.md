# Spesifikasi Agent Contract ALOS

| Metadata | Nilai |
|---|---|
| Status | Rancangan untuk Pilot Internal |
| Versi | 0.1.0 |
| Berlaku untuk | Seluruh Core, Sub, dan Sub-Sub Agent |
| Pembaruan terakhir | 28 Agustus 2026 |

## 1. Tujuan

Agent Contract adalah kontrak berversi yang menentukan identitas, tugas, kewenangan, sumber, alat, keluaran, pengawasan, dan ukuran keberhasilan agent. Kontrak mencegah agent bekerja berdasarkan prompt bebas tanpa batas operasional yang dapat diaudit.

## 2. Prinsip

- satu agent adalah konfigurasi logis, bukan aplikasi, database, atau microservice;
- agent tidak memiliki kewenangan manusia dan tidak dapat memperluas izinnya sendiri;
- kemampuan digunakan bersama melalui lingkungan eksekusi, sedangkan kontrak menentukan kemampuan yang diizinkan;
- keluaran harus terstruktur, tervalidasi, memiliki sumber, dan dapat dikoreksi;
- tindakan eksternal hanya melalui alat yang terdaftar dan Gerbang Integrasi;
- versi kontrak yang digunakan harus tersimpan pada setiap eksekusi.

## 3. Bidang Wajib

| Bidang | Ketentuan |
|---|---|
| `agent_id` | pengenal stabil, unik, dan tidak berubah antarversi |
| `name` | nama resmi agent |
| `domain` | domain bisnis atau `shared-enterprise` |
| `purpose` | hasil bisnis yang menjadi tanggung jawab agent |
| `human_owner` | peran manusia yang memiliki akuntabilitas bisnis |
| `triggers` | kejadian, jadwal, atau permintaan sah yang memulai agent |
| `inputs` | skema masukan, bidang wajib, klasifikasi, dan validasi |
| `source_of_truth` | sumber resmi yang boleh digunakan |
| `capabilities` | kemampuan terdaftar yang boleh dijalankan |
| `outputs` | skema keluaran dan status verifikasinya |
| `tools_allowed` | alat serta operasi spesifik yang diizinkan |
| `approval_boundary` | kondisi yang memerlukan review atau persetujuan manusia |
| `evidence_requirement` | bukti minimum dan aturan keabsahannya |
| `forbidden_actions` | tindakan yang selalu dilarang |
| `KPI/metrics` | ukuran kualitas, hasil, risiko, biaya, dan kecepatan |
| `escalation` | pemicu, tujuan, batas waktu, dan jalur eskalasi |
| `version` | versi semantik kontrak |
| `status` | status siklus hidup definisi |

Bidang tambahan yang dianjurkan: tingkat risiko, skema keyakinan, batas waktu eksekusi, kebijakan percobaan ulang, klasifikasi data, masa berlaku, dependensi kontrak, dan skenario pengujian.

## 4. Status Definisi

`DRAFT`, `VALIDATED`, `TESTED`, `REVIEWED`, `STAGED`, `RELEASED`, `DEPRECATED`, atau `RETIRED`.

Hanya `RELEASED` yang boleh digunakan untuk pekerjaan produksi. Pilot dapat menggunakan `STAGED` pada lingkungan pilot yang terisolasi dan diberi label jelas.

## 5. Jenis Kemampuan

| Jenis | Contoh | Aturan |
|---|---|---|
| Deterministik | validasi bidang, perhitungan, transisi, pencocokan exact | tidak menggunakan LLM |
| Analisis AI | ekstraksi, klasifikasi, ringkasan, perbandingan | keluaran terstruktur dan memiliki sumber |
| Rekomendasi | prioritas, tindak lanjut, rancangan keputusan | tidak menjadi keputusan final |
| Penyusunan bahasa | rancangan pesan, konten, ringkasan | tunduk pada template, kebijakan, dan review |
| Alat eksternal | baca CRM, kirim notifikasi, baca transaksi | melalui kontrak alat dan Gerbang Integrasi |

## 6. Kontrak Keluaran

Setiap keluaran minimum memuat:

- `run_id`, `agent_id`, dan `agent_version`;
- `result_type` dan versi skema;
- hasil terstruktur;
- referensi sumber dan bukti;
- status verifikasi;
- tingkat keyakinan bila menggunakan AI;
- peringatan, ketidaklengkapan, dan asumsi;
- rekomendasi langkah berikutnya;
- kebutuhan review/persetujuan;
- waktu, model, prompt, kemampuan, dan alat yang digunakan.

Keluaran yang gagal validasi skema berstatus `FAILED_OUTPUT_VALIDATION` dan tidak boleh diteruskan sebagai fakta atau dasar tindakan.

## 7. Review dan Persetujuan

Review manusia memastikan ketepatan hasil AI. Persetujuan merupakan keputusan kewenangan bisnis. Keduanya dibedakan dan dicatat terpisah.

Review wajib apabila keluaran memiliki keyakinan di bawah ambang yang dikonfigurasi, sumber bertentangan, data terbatas, hasil memengaruhi keputusan material, atau kontrak agent secara eksplisit mewajibkannya. Agent tidak dapat mereview atau menyetujui hasilnya sendiri.

## 8. Kebijakan Alat

Setiap alat didaftarkan berdasarkan operasi, cakupan data, mode baca/tulis, kebutuhan persetujuan, batas laju, timeout, percobaan ulang, dan aturan idempotensi. Agent hanya menerima referensi alat; kredensial dikelola Gerbang Integrasi.

Operasi jaringan bebas, shell, kode arbitrer, akses database langsung, dan pengambilan rahasia dilarang secara bawaan.

## 9. Bukti dan Asal-Usul

Agent wajib menghubungkan setiap klaim material dengan sumber yang dapat diperiksa. Untuk dokumen, referensi mencakup versi, hash, halaman atau bagian bila tersedia. Untuk data sistem, referensi mencakup entitas, versi, waktu baca, dan pemilik resmi. Hasil turunan harus mencatat metode atau rumusnya.

## 10. Pengukuran

Metrik minimum per agent:

- keberhasilan dan kegagalan eksekusi;
- ketepatan skema keluaran;
- latensi dan biaya;
- tingkat review, koreksi, dan penolakan manusia;
- kesalahan alat dan percobaan ulang;
- pelanggaran atau blokir kebijakan;
- hasil bisnis spesifik agent;
- perubahan kualitas antarversi.

Volume eksekusi bukan satu-satunya ukuran keberhasilan.

## 11. Perubahan dan Kompatibilitas

Perubahan mayor digunakan ketika makna hasil, batas kewenangan, atau skema tidak kompatibel. Perubahan minor menambah kemampuan kompatibel; patch memperbaiki perilaku tanpa mengubah kontrak. Rilis baru wajib memiliki perbandingan, pengujian regresi, review pemilik bisnis, dan rencana rollback.

## 12. Validasi Minimum

Definisi tidak dapat dirilis jika ada bidang wajib kosong, pemilik manusia tidak jelas, alat tidak terdaftar, tindakan terlarang tidak didefinisikan, keluaran tidak memiliki skema, pengujian tidak tersedia, atau dependensi kebijakan masih `TBD` untuk tindakan material.
