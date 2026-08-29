# Dasar Keamanan dan Kebijakan Data AI ALOS

| Metadata | Nilai |
|---|---|
| Status | Rancangan untuk Pilot Internal |
| Versi | 0.2.0 |
| Pemilik kebijakan | Manajemen dan IT; pemilik data sesuai divisi |
| Pembaruan terakhir | 29 Agustus 2026 |

## 1. Tujuan

Dokumen ini menetapkan pengamanan minimum pilot serta batas pemrosesan data oleh AI. Kebijakan ini berlaku bagi aplikasi web, API, worker, agent, dokumen, integrasi, observabilitas, dan lingkungan pengembangan.

## 2. Prinsip Keamanan

- ditolak secara bawaan dan diberikan seminimal mungkin;
- satu akun untuk satu identitas manusia;
- autentikasi, otorisasi, dan persetujuan merupakan kontrol terpisah;
- satu pengguna boleh memiliki beberapa peran, tetapi tindakan memakai satu konteks peran aktif;
- data dibatasi menurut organisasi, divisi, proyek, klasifikasi, dan tujuan;
- seluruh tindakan material dapat ditelusuri;
- agent dan integrasi menggunakan identitas layanan terbatas;
- rahasia tidak disimpan di Git, prompt, log, atau keluaran agent;
- kontrol keamanan tidak boleh bergantung pada kepatuhan sukarela model AI.

## 3. Identitas dan Akses

Pilot dapat menggunakan autentikasi lokal, tetapi batas antarmukanya harus kompatibel dengan OIDC. Produksi memerlukan penyedia identitas yang disahkan dan MFA untuk tindakan istimewa atau material.

Otorisasi memadukan:

- RBAC untuk izin berbasis jabatan/peran;
- ABAC untuk divisi, proyek, klasifikasi, status, dan tujuan;
- pemisahan tugas berbasis identitas asli;
- validasi ulang pada setiap perintah material, bukan hanya di antarmuka.

Perubahan peran, delegasi, akses darurat, dan pencabutan akses wajib memiliki masa berlaku, alasan, persetujuan, dan audit.

## 4. Klasifikasi Data

| Tingkat | Contoh pilot | Perlakuan minimum |
|---|---|---|
| D0 Publik | materi publik yang disahkan | akses sesuai kebutuhan |
| D1 Internal | prosedur umum dan data sintetis | pengguna internal berwenang |
| D2 Rahasia | anggaran, kontrak internal, data pelanggan | pembatasan divisi/proyek dan masking |
| D3 Sangat Terbatas | KTP, payroll, rekening, berkas personalia | akses tujuan-spesifik, persetujuan, audit rinci |
| D4 Kritikal | kredensial, kunci, data keamanan inti | vault khusus; tidak boleh diproses agent/LLM |

Pemilik data menetapkan klasifikasi final. Jika klasifikasi belum tersedia, sistem memilih tingkat yang lebih ketat.

## 5. Kebijakan Data Pilot

Data yang diperbolehkan:

- data sintetis yang tidak mewakili orang atau transaksi nyata;
- template dokumen tanpa data rahasia;
- dokumen yang telah disanitasi dan disetujui untuk pengujian;
- metadata teknis yang tidak mengandung rahasia.

Data perusahaan asli, data pribadi, payroll, rekening, identitas pemerintah, kredensial, kontrak sensitif, dan dokumen hukum mentah tidak boleh dimasukkan sampai tersedia klasifikasi, dasar penggunaan, kontrol akses, retensi, dan persetujuan pemilik data.

## 6. Penggunaan LLM

LLM hanya digunakan untuk tugas non-deterministik yang diizinkan kontrak agent. Setiap permintaan wajib melalui adaptor penyedia dan pemeriksaan kebijakan data.

Sebelum pengiriman, sistem memeriksa klasifikasi, tujuan, bidang yang harus dimasking, batas penyedia, retensi, dan lokasi pemrosesan bila relevan. Data D3/D4 dilarang dikirim ke LLM cloud pada pilot.

Keluaran LLM:

- diperlakukan sebagai turunan dan belum terverifikasi;
- wajib mengikuti skema;
- menyimpan referensi sumber, model, prompt, dan versi;
- harus dapat dikoreksi atau ditolak manusia;
- tidak boleh menjadi dasar tunggal keputusan keuangan, hukum, personalia, atau keamanan.

## 7. Prompt Injection dan Konten Tidak Tepercaya

Dokumen, halaman web, email, dan hasil integrasi diperlakukan sebagai data tidak tepercaya. Instruksi yang terdapat di dalamnya tidak boleh mengubah kontrak agent, kebijakan alat, atau perintah sistem. Retrieval dipisahkan dari instruksi sistem; penggunaan alat selalu divalidasi ulang oleh kode deterministik.

## 8. Dokumen dan Unggahan

Unggahan dibatasi pada tingkat request dan berkas, dibatasi tipe, diberi nama internal, dihitung hash-nya, diklasifikasikan, dan disimpan pada penyimpanan objek. Ekstensi file tidak menjadi satu-satunya validasi; struktur Office juga dibatasi untuk mengurangi risiko ZIP bomb. Pilot lokal hanya memakai data sintetis dan menandai scan `NOT_CONFIGURED`; production wajib memakai pemeriksaan malware eksternal dan memblokir download sampai status `CLEAN`. Dokumen bersama berklasifikasi rahasia hanya tersedia bagi peran tingkat organisasi. Pratinjau dan ekstraksi dilakukan pada proses terisolasi. Download dilakukan melalui API terotorisasi atau tautan terbatas waktu bila kelak diaktifkan.

## 9. Rahasia dan Integrasi

Rahasia berada pada vault atau mekanisme secret environment yang disetujui. Agent hanya melihat nama alat dan parameter aman, bukan token. Kredensial dipisah antarlingkungan dan diberi cakupan minimum. Webhook memerlukan verifikasi tanda tangan, replay protection, idempotensi, dan audit.

## 10. Audit dan Observabilitas Aman

Log dan trace tidak boleh berisi token, kata sandi, isi dokumen sensitif, atau data pribadi mentah. Bidang sensitif dimasking sebelum keluar dari modul pemilik. Akses audit dibatasi dan setiap pembacaan audit sensitif juga dicatat.

## 11. Pengembangan dan Rantai Pasok

- repository bersifat privat;
- `main` dilindungi dan perubahan melalui pull request;
- review pemilik kode diwajibkan untuk area sensitif;
- lint, test, pemeriksaan migrasi, secret scan, dan dependency scan dijalankan di CI;
- dependency dikunci dan penambahannya direview;
- artifact rilis dapat ditelusuri ke commit dan hasil CI;
- data produksi dan rahasia tidak tersedia pada lingkungan pengembangan.

## 12. Respons Insiden dan Penghentian Darurat

Sistem menyediakan penghentian per agent, alur kerja, kemampuan, alat, integrasi, atau lingkungan eksekusi. Insiden mencatat dampak, waktu, komponen, tindakan mitigasi, pemilik, bukti, dan CAPA. Pemulihan tidak boleh menghapus jejak kegagalan.

## 13. Retensi dan Penghapusan

Nilai retensi per kategori berstatus `TBD`. Sampai disahkan, data pilot menggunakan masa hidup minimum yang diperlukan dan tidak memasukkan data perusahaan asli. Penghapusan yang sah harus mematuhi legal hold, keterkaitan audit, serta aturan penyimpanan bukti; audit dapat menyimpan metadata tindakan tanpa mempertahankan isi yang sudah wajib dihapus.

## 14. Persyaratan Sebelum Data Asli

Data asli hanya dapat digunakan setelah tersedia:

1. pemilik dan klasifikasi data;
2. tujuan dan dasar pemrosesan;
3. matriks akses dan masking;
4. retensi serta prosedur penghapusan;
5. penilaian penyedia AI/integrasi;
6. persetujuan manajemen dan pemilik data;
7. pengujian keamanan serta prosedur insiden;
8. lingkungan staging yang terpisah dan terkontrol.

## 15. Keputusan Terbuka

Penyedia identitas, penyedia/deployment LLM, lokasi hosting, retensi, petugas keamanan, prosedur legal hold, standar enkripsi final, RTO/RPO, dan aturan penggunaan data perusahaan masih `TBD`.
