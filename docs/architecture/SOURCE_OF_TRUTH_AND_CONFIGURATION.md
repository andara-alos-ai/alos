# Sumber Kebenaran dan Tata Kelola Konfigurasi

| Metadata | Nilai |
|---|---|
| Status | Rancangan untuk Pilot Internal |
| Versi | 0.1.0 |
| Pembaruan terakhir | 28 Agustus 2026 |

## 1. Tujuan

Dokumen ini mencegah konflik antara keputusan manajemen, dokumentasi, definisi yang dapat dibaca mesin, catatan operasional, sistem eksternal, dan keluaran AI.

## 2. Urutan Otoritas

Jika terdapat pertentangan, urutan otoritas yang digunakan adalah:

1. peraturan yang berlaku dan keputusan perusahaan yang disahkan;
2. struktur organisasi yang terkunci;
3. kebijakan dan definisi bisnis yang telah dirilis setelah persetujuan;
4. catatan operasional kanonik dan fakta eksternal yang terverifikasi;
5. dokumentasi dan keputusan arsitektur yang disetujui;
6. spesifikasi rancangan dan dasar desain;
7. analisis, ekstraksi, prediksi, atau rekomendasi AI.

Keluaran AI tidak menjadi fakta bisnis resmi hanya karena dihasilkan Core Agent.

## 3. Keputusan Terkunci dan Dasar Implementasi

### 3.1 Terkunci

`DIREKTUR UTAMA -> AI EXECUTIVE OPERATING LAYER -> KEUANGAN, SALES & MARKETING, PROPERTY, HR, LEGAL, IT`

AI Executive Operating Layer tidak merupakan pejabat resmi dan tidak menggantikan Direktur Utama atau pimpinan divisi.

### 3.2 Dasar implementasi berversi

Hal berikut merupakan dasar implementasi, bukan aturan permanen yang terkunci:

- taksonomi dan pemetaan 18 Core Agent;
- governance gate, tingkat persetujuan, RACI, KPI, SLA, dan alur kerja;
- model data, arsitektur, keamanan, observabilitas, dan integrasi;
- pipeline Genesis serta detail implementasi.

Perubahannya wajib melalui validasi, pengujian, review, dan rilis sesuai tingkat dampak.

## 4. Jenis Sumber

| Sumber | Kegunaan | Kedudukan |
|---|---|---|
| Master Blueprint | maksud desain dan dasar konsolidasi | dasar, kecuali struktur organisasi yang terkunci |
| dokumen implementasi | desain yang dapat dibaca manusia | dokumentasi terkendali |
| `definitions/` | definisi agent, alur kerja, dan kebijakan | resmi hanya setelah dirilis |
| database | status operasional dan snapshot definisi rilis | resmi untuk operasi tercatat |
| penyimpanan objek | isi dokumen/bukti dan versinya | resmi jika hash dan metadata sesuai |
| sistem eksternal | fakta milik otoritas eksternal | resmi hanya untuk bidang yang disepakati |
| audit | riwayat tindakan dan asal-usul | riwayat resmi yang tidak boleh diubah |
| keluaran AI | ekstraksi, ringkasan, perbandingan, rekomendasi | turunan dan wajib dapat direview |

## 5. Satu Fakta, Satu Pemilik Resmi

Kepemilikan ditetapkan pada tingkat fakta atau atribut. Satu pelanggan dapat memiliki identitas kanonik, sementara Sales & Marketing mengelola interaksi komersial, Keuangan mengelola fakta pembayaran, dan Legal memverifikasi atribut hukum.

Setiap bidang yang dikendalikan harus memiliki:

- pemilik resmi;
- sistem atau dokumen sumber;
- status verifikasi;
- waktu dan versi berlaku;
- klasifikasi dan kebijakan akses;
- asal-usul nilai turunan.

Nilai yang bertentangan dibuat sebagai kasus rekonsiliasi dan tidak boleh ditimpa diam-diam.

## 6. Siklus Hidup Definisi

```text
DRAFT -> VALIDATED -> TESTED -> REVIEWED -> STAGED -> RELEASED
                                             \-> REJECTED
RELEASED -> DEPRECATED -> RETIRED
```

Hanya definisi `RELEASED` yang dapat memulai pekerjaan produksi baru. Setiap eksekusi menyimpan versi definisi, kebijakan, prompt, model, kemampuan, dan alat yang digunakan. Eksekusi lama tetap dapat ditelusuri ketika versi baru dirilis.

## 7. Batas Genesis

Genesis diperbolehkan:

- membaca spesifikasi sumber yang disetujui;
- mengusulkan perubahan agent, alur kerja, kebijakan, pengujian, dan manifest;
- memvalidasi skema dan referensi silang;
- menghasilkan perbandingan perubahan;
- menjalankan pengujian pada lingkungan terisolasi;
- membuat permintaan review dan rilis manusia.

Genesis dilarang mengubah struktur organisasi, menulis langsung ke data operasional produksi, mengaktifkan usulannya sendiri, melewati review, atau menghapus riwayat audit.

## 8. Kepemilikan Konfigurasi

| Konfigurasi | Pemilik bisnis | Pengelola teknis | Review minimum |
|---|---|---|---|
| struktur organisasi | Direktur Utama | IT | otorisasi manajemen |
| aturan domain | divisi terkait | IT | pemilik divisi dan hasil uji |
| persetujuan/RACI | pejabat berwenang | IT | review tata kelola/manajemen |
| tujuan dan batas agent | divisi terkait atau Eksekutif | IT | pemilik bisnis, keamanan, dan AI |
| kontrak alat/integrasi | divisi terkait | IT | keamanan dan teknis |
| kebijakan platform bersama | pemilik yang ditunjuk | IT | review lintas fungsi |
| kontrol keamanan | manajemen dan IT | IT | review keamanan |

Pengelolaan teknis oleh IT tidak memindahkan kepemilikan bisnis kepada IT.

## 9. Konsistensi Dokumentasi dan Implementasi

- Dokumentasi menjelaskan maksud, keputusan, kepemilikan, batas, dan penerimaan.
- Definisi yang dapat dibaca mesin menetapkan konfigurasi yang dijalankan.
- Migrasi database menetapkan struktur data yang disimpan.
- Pengujian menjadi bukti bahwa aturan dan batas ditegakkan.
- Dokumentasi API yang dihasilkan menggambarkan antarmuka yang benar-benar tersedia.

Konstanta tidak boleh digandakan di banyak tempat jika dapat dirujuk dari satu definisi berversi.

## 10. Nilai yang Belum Divalidasi

Ambang persetujuan, SLA, rumus KPI, retensi, vendor, dan detail API yang belum diputuskan menggunakan `TBD`. Alur material yang bergantung pada nilai tersebut harus memasuki `BLOCKED_CONFIGURATION` atau menggunakan kebijakan khusus pilot yang telah disetujui. Contoh di blueprint tidak boleh dianggap sebagai kebijakan produksi.

## 11. Catatan Perubahan

Setiap rilis perubahan wajib mencatat pengenal dan alasan perubahan, sumber dan versinya, domain terdampak, pembuat, reviewer, persetujuan, hasil validasi dan pengujian, dampak keamanan/data, selisih dari versi sebelumnya, identitas rilis dan rollback, tanggal berlaku, dan status.
