# Spesifikasi Agent Contract ALOS

| Metadata | Nilai |
|---|---|
| Status | Diimplementasikan untuk Fondasi Genesis G1–G3 |
| Versi | 1.0.0 |
| Berlaku untuk | Seluruh Core, Sub, dan Sub-Sub Agent |
| Pembaruan terakhir | 30 Agustus 2026 |

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
| `contract_version` | versi skema Agent Contract yang digunakan |
| `agent_id` | pengenal stabil, unik, dan tidak berubah antarversi |
| `name` | nama resmi agent |
| `agent_kind` | `CORE`, `SUB_AGENT`, atau `SUB_SUB_AGENT` |
| `parent_agent_id` | identitas parent; `null` untuk Core Agent |
| `parent_agent_version` | versi parent yang dirujuk; `null` untuk Core Agent |
| `extends` | referensi agent dan versi dasar yang diperluas; dapat `null` |
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
| `metrics` | ukuran kualitas, hasil, risiko, biaya, dan kecepatan |
| `escalation` | pemicu, tujuan, batas waktu, dan jalur eskalasi |
| `version` | versi semantik kontrak |
| `status` | status siklus hidup definisi |

Bidang tambahan yang dianjurkan: tingkat risiko, skema keyakinan, batas waktu eksekusi, kebijakan percobaan ulang, klasifikasi data, masa berlaku, dependensi kontrak, dan skenario pengujian.

`KPI/metrics` tetap diterima sebagai alias kompatibilitas untuk definisi lama, tetapi representasi kanonik menggunakan `metrics`. JSON Schema resmi berada pada `definitions/schemas/agent-contract.schema.json`.

### 3.1 Hierarki Agent

- Core Agent tidak memiliki parent;
- Sub-Agent wajib menunjuk Core Agent beserta versi yang tepat;
- Sub-Sub-Agent wajib menunjuk Sub-Agent beserta versi yang tepat;
- kombinasi `agent_id` dan `version` wajib unik;
- parent dan `extends` yang tidak ditemukan, self-reference, serta dependency cycle ditolak;
- penambahan Sub-Agent atau Sub-Sub-Agent tidak mengubah baseline tepat 18 identitas Core Agent.

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

Setiap execution plan juga membawa `contract_version`, `agent_kind`, `agent_version`, dan SHA-256 `contract_digest`. Agent Release menyimpan konten kontrak lengkap beserta status lifecycle pada kolom terpisah. Snapshot dengan kombinasi `agent_id` dan `version` yang sama tidak boleh ditimpa dengan isi berbeda. Perubahan status seperti `STAGED` menjadi `RELEASED` tidak mengubah digest konten.

Capability yang digunakan workflow diikat melalui invocation contract berisi mode deterministik/AI, referensi tool, versi agent, dan kebutuhan review. Detail teknisnya berada pada `TOOL_REGISTRY_AND_CAPABILITY_INVOCATION.md`.

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

Registry memilih versi semantik terbaru jika pemanggil tidak menentukan versi. Eksekusi yang perlu reproduktif dapat meminta versi secara eksplisit. Perubahan isi kontrak selalu menggunakan versi baru; perubahan isi pada snapshot versi yang sama ditolak.

## 12. Validasi Minimum

Definisi tidak dapat dirilis jika ada bidang wajib kosong, pemilik manusia tidak jelas, alat tidak terdaftar, tindakan terlarang tidak didefinisikan, keluaran tidak memiliki skema, pengujian tidak tersedia, atau dependensi kebijakan masih `TBD` untuk tindakan material.
