# Registry Baseline Agent ALOS (18 Legacy Pilot Agents)

| Metadata | Nilai |
|---|---|
| Status | Fondasi Genesis G1–G3 |
| Versi registry | 1.0.0 |
| Lingkungan eksekusi | Satu lingkungan eksekusi agent bersama |
| Pembaruan terakhir | 30 Agustus 2026 |

## 1. Tujuan

Dokumen ini mencatat 18 identitas agent legacy yang digunakan pada workflow pilot. Sumber tunggal seluruh agent tetap berada pada Agent Registry di `definitions/agents/`; dokumen ini hanya baseline kompatibilitas dan bukan pembatas jumlah atau taxonomy agent.

Registry membaca `definitions/agents/**/agent.json`, memvalidasi referensi silang, dan mengindeks kontrak berdasarkan kombinasi `agent_id` serta `version`. Agent top-level, Sub-Agent, dan Sub-Sub-Agent dapat ditambahkan melalui pipeline Genesis setelah seluruh gate dipenuhi.

Pemanggilan tanpa versi menggunakan versi semantik terbaru. Runtime dapat meminta versi tertentu dan hanya menjalankan status yang diizinkan oleh release gate. Pada lingkungan pilot, `STAGED` dan `RELEASED` dapat dijalankan; production nantinya hanya menggunakan `RELEASED`.

Agent Registry memvalidasi setiap `tools_allowed` terhadap Tool Registry. Penambahan agent oleh pipeline Genesis selalu berupa proposal DRAFT dan tidak mengubah struktur organisasi.

## 2. Pemetaan Kepemilikan

| Kelompok | Core Agent |
|---|---|
| AI Executive / Shared Enterprise | MCA, DIA, SEA, CEA, KDA, ARA, CRA |
| Keuangan | FRA, BCA, TIA |
| Sales & Marketing | SLA, MCA_MKT, CFA |
| Property | TPA |
| HR | HRA, HPA |
| Legal | LPA, CLA |
| IT | pengelola teknis platform, registry, runtime, integrasi, keamanan, observabilitas, dan Genesis |

Pemilik bisnis agent domain adalah pimpinan atau peran yang ditunjuk pada divisi terkait. Agent bersama dimiliki oleh fungsi bisnis yang menggunakan kasusnya; kebijakan lintas perusahaan memerlukan pemilik manajemen yang ditetapkan. IT bukan pemilik bisnis seluruh agent.

## 3. Registry Agent Bersama

| ID | Tujuan dan tugas pilot | Masukan utama | Keluaran utama | Pemilik manusia | Batas utama |
|---|---|---|---|---|---|
| MCA | menggabungkan kondisi lintas divisi, memprioritaskan masalah, dan menyusun ringkasan eksekutif | KPI, persetujuan, penyimpangan, CAPA, kesehatan sistem | Executive Brief, prioritas, antrean keputusan | Direktur Utama/delegasi eksekutif | tidak membuat keputusan atau mengubah status bisnis final |
| DIA | mengklasifikasi dokumen, mengekstrak bidang, meringkas, dan membandingkan versi | PDF, DOCX, gambar, metadata, skema dokumen | hasil ekstraksi, klasifikasi, ringkasan, perbandingan, ketidaklengkapan | pemilik proses dari dokumen terkait | tidak menetapkan keabsahan hukum/keuangan tanpa verifikasi |
| SEA | memilih SOP yang berlaku dan membentuk langkah kerja terkendali | SOP rilis, konteks kasus, aturan domain | rencana langkah, daftar periksa, tugas, ketergantungan | pemilik SOP/divisi terkait | tidak mengubah SOP atau transisi resmi melalui LLM |
| CEA | memeriksa kelengkapan, keterkaitan, dan metadata bukti | persyaratan bukti, dokumen, foto, metadata | hasil pemeriksaan bukti dan daftar kekurangan | pemilik proses/divisi terkait | tidak menyatakan bukti sah jika sumber atau verifikasi belum cukup |
| KDA | menghitung KPI deterministik dan menampilkan penyimpangan | data terverifikasi, rumus KPI rilis, periode | snapshot KPI, tren, variance, data dasbor | pemilik KPI/divisi terkait | tidak membuat rumus atau mengubah target sendiri |
| ARA | menentukan routing persetujuan, memeriksa RACI/SoD, pengingat, dan eskalasi | kebijakan rilis, pemohon, nilai, risiko, proyek, bukti | permintaan persetujuan, hasil SoD, eskalasi, action token | pejabat pemilik kebijakan persetujuan | tidak memberikan persetujuan atau menganggap diam sebagai setuju |
| CRA | membuka penyimpangan, membentuk CAPA, memantau tenggat, dan verifikasi penutupan | pelanggaran aturan, variance, keterlambatan, bukti | Exception, CAPA, tugas, status verifikasi, rekomendasi penutupan | pemilik risiko/proses terkait | tidak menutup CAPA tanpa bukti dan verifikasi manusia |

## 4. Registry Agent Keuangan

| ID | Tujuan dan tugas pilot | Masukan utama | Keluaran utama | Pemilik manusia | Batas utama |
|---|---|---|---|---|---|
| FRA | mencocokkan invoice, pembayaran, dan transaksi serta menangani selisih | invoice, catatan pembayaran, transaksi bank/file sintetis | status cocok penuh/sebagian/tidak cocok/ganda/berselisih | Kepala Keuangan | tidak mengubah transaksi bank atau jurnal final |
| BCA | memeriksa ketersediaan anggaran, RAB, komitmen, dan dampak arus kas | permintaan pembayaran, anggaran, RAB, komitmen | hasil pemeriksaan anggaran, variance, peringatan | Kepala Keuangan | tidak menyetujui pembayaran atau mengubah anggaran |
| TIA | mengekstrak dan memvalidasi invoice serta data pajak berdasarkan aturan rilis | invoice, data lawan transaksi, aturan pajak terkonfigurasi | pemeriksaan invoice/pajak dan daftar koreksi | penanggung jawab pajak/Keuangan | tidak melapor ke DJP atau memberi keputusan pajak final pada pilot |

## 5. Registry Agent Sales & Marketing

| ID | Tujuan dan tugas pilot | Masukan utama | Keluaran utama | Pemilik manusia | Batas utama |
|---|---|---|---|---|---|
| SLA | menerima, deduplikasi, mengklasifikasi, memprioritaskan, dan menugaskan lead | formulir lead, sumber, aturan deduplikasi/penugasan | Lead Record, skor/kelas, Sales PIC, SLA respons | Kepala Sales & Marketing | tidak menjanjikan harga, ketersediaan, atau reservasi final |
| MCA_MKT | menyusun rancangan konten berdasarkan brief dan aturan merek | brief, target audiens, kanal, aturan merek | rancangan konten, variasi, daftar pemeriksaan kepatuhan | Kepala Sales & Marketing/Marketing | tidak menerbitkan konten tanpa review dan persetujuan |
| CFA | menyusun rencana tindak lanjut dan rancangan komunikasi pelanggan | Lead Record, riwayat interaksi, consent, status pipeline | FollowUpTask, rancangan pesan, tindakan berikutnya | Sales PIC dan Kepala Sales | tidak mengirim komunikasi di luar consent atau membuat komitmen final |

## 6. Registry Agent Property

| ID | Tujuan dan tugas pilot | Masukan utama | Keluaran utama | Pemilik manusia | Batas utama |
|---|---|---|---|---|---|
| TPA | memeriksa bukti lapangan, progres, opname, inspeksi, defect, dan variance | paket kerja, klaim progres, foto, geotag, pengukuran | progres terverifikasi, variance, temuan, pembaruan KPI | Kepala Property/penanggung jawab proyek | tidak menetapkan status hukum izin atau menyetujui pembayaran |

## 7. Registry Agent HR

| ID | Tujuan dan tugas pilot | Masukan utama | Keluaran utama | Pemilik manusia | Batas utama |
|---|---|---|---|---|---|
| HRA | menjalankan permintaan rekrutmen, screening administratif, tugas interview, dan penyimpangan kehadiran | permintaan posisi, kriteria rilis, CV sanitasi, data kehadiran sintetis | kandidat terstruktur, ringkasan screening, tugas review, exception | Kepala HR | tidak memutuskan penerimaan, promosi, sanksi, atau PHK |
| HPA | memeriksa kelengkapan, versi, klasifikasi, dan masa berlaku berkas personalia | daftar persyaratan dan dokumen personalia sanitasi | status kelengkapan, kekurangan, pengingat masa berlaku | Kepala HR | tidak membuka data personalia kepada pihak atau agent tanpa izin |

## 8. Registry Agent Legal

| ID | Tujuan dan tugas pilot | Masukan utama | Keluaran utama | Pemilik manusia | Batas utama |
|---|---|---|---|---|---|
| LPA | mengelola register izin, persyaratan, masa berlaku, sumber, dan ketergantungan proyek | izin, sumber resmi/terverifikasi, persyaratan, proyek | Permit Record, checklist, pengingat, status penghambat | Kepala Legal | tidak menyatakan izin sah tanpa sumber resmi dan review Legal |
| CLA | mengekstrak klausul, membandingkan kontrak, dan mencatat kewajiban | kontrak, template rilis, daftar klausul wajib | perbandingan, temuan klausul, kewajiban, paket review | Kepala Legal | tidak memberi persetujuan hukum atau menandatangani kontrak |

## 9. Pemicu dan Alat Pilot

Pemicu awal berasal dari formulir pengguna, unggahan dokumen, langkah alur kerja, jadwal, atau kejadian internal. API eksternal produksi belum diaktifkan. Alat pilot dibatasi pada pembacaan data ALOS sesuai izin, penyimpanan dokumen, kemampuan AI yang disetujui, kalkulator deterministik, dan pembuatan tugas internal.

## 10. Bukti dan Persetujuan

Setiap agent wajib menghubungkan keluaran material dengan bukti atau data sumber. Review manusia wajib untuk hasil dokumen sensitif, keputusan keuangan, hukum, personalia, publikasi eksternal, dan hasil berkeyakinan rendah. ARA mengelola routing, tetapi keputusan tetap dibuat identitas manusia yang berwenang.

## 11. Larangan Bersama

Seluruh agent dilarang mengubah organisasi, menambah izinnya sendiri, melihat rahasia, mengakses jaringan bebas, menghapus audit, mengubah fakta terverifikasi tanpa perintah sah, menyetujui hasil sendiri, menganggap diam sebagai persetujuan, atau menjalankan tindakan eksternal material tanpa kebijakan dan persetujuan.

## 12. Metrik Pilot

Metrik bersama meliputi keberhasilan eksekusi, latensi, biaya, validitas skema, kelengkapan sumber, tingkat koreksi manusia, kesalahan alat, blokir kebijakan, dan penyelesaian kasus penggunaan. Metrik bisnis spesifik tetap menggunakan nilai pilot sampai rumus resmi divisi disahkan.

## 13. Eskalasi

Agent mengeskalasi ketika sumber bertentangan, data wajib kurang, keyakinan di bawah batas, SLA terlewati, tindakan melebihi kewenangan, kebijakan masih `TBD`, atau alat gagal setelah batas percobaan. Eskalasi ditujukan kepada pemilik pekerjaan, pemilik bisnis, pejabat persetujuan, atau IT sesuai jenis masalah.
