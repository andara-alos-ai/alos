# Kesiapan Pilot dan Recovery ALOS

## Tujuan

Runbook ini menjadi gate operasional sebelum controlled pilot. Pilot hanya memakai data sintetis atau data yang telah disanitasi. Hasil readiness bukan izin production dan tidak menggantikan persetujuan pemilik bisnis, IT, Security, dan Direktur Utama.

## Readiness Gate

Pilih proyek pada ALOS, lalu buka **Kesehatan Sistem**. Pemeriksaan membaca profil terversi di `definitions/pilot/controlled-pilot/profile.json` dan menilai:

- proyek aktif dan enam divisi tersedia;
- Direktur Utama, AI Executive, technical custodian, serta operator domain aktif;
- separation of duties untuk Keuangan, Property, HR, dan Legal;
- 18 Core Agent dan enam workflow tersedia pada registry;
- dokumen uji aman, dead-letter, dan heartbeat worker;
- OIDC, object storage, malware scan, serta bukti recovery sesuai environment.

Status `BLOCKED` wajib ditutup sebelum UAT. Status `ATTENTION` memerlukan penerimaan risiko tertulis dan tidak pernah mengizinkan production secara otomatis.

## Backup Terkontrol

Simpan backup pada media terenkripsi dengan akses terbatas. Direktori backup tidak boleh berada di Git.

```powershell
.\scripts\database\backup-alos.ps1 -BackupDirectory "D:\ALOS-Backups"
```

Script menghasilkan PostgreSQL custom dump dan manifest SHA-256. Perlakukan keduanya sebagai `RESTRICTED`, terapkan retensi yang disetujui, dan jangan mengirimkannya melalui kanal publik.

## Uji Restore Aman

Uji restore tidak menimpa database `alos`. Script membuat database sementara dengan prefix `alos_restore_check_`, memverifikasi migration records, lalu menghapus database uji tersebut.

```powershell
.\scripts\database\test-alos-restore.ps1 -BackupFile "D:\ALOS-Backups\alos-<timestamp>.dump"
```

Lampirkan log perintah, checksum, waktu mulai/selesai, operator, hasil integrity check, dan keputusan pada evidence operasional. Jangan menandai readiness recovery selesai hanya karena file backup berhasil dibuat.

## Checklist Controlled Pilot

1. Gunakan environment staging dan hostname HTTPS resmi.
2. Pastikan login Google OIDC aktif; local pilot login dinonaktifkan.
3. Provision PIC, role, divisi, project assignment, dan masa berlaku akses.
4. Gunakan minimal dua pengguna berbeda pada alur yang mewajibkan maker-checker.
5. Jalankan backup dan restore drill terisolasi; simpan bukti.
6. Pastikan worker baru, tidak ada dead-letter, dan log tidak memuat secret atau isi dokumen.
7. Jalankan UAT delapan skenario dengan data sintetis/sanitasi.
8. Catat defect, risiko tersisa, owner, target perbaikan, dan sign-off.

## Respons Kegagalan

- `BLOCKED`: hentikan UAT pada domain terkait dan ikuti remediation di layar.
- worker tidak baru: periksa service worker, koneksi database, dan log siklus terakhir.
- dead-letter: identifikasi penyebab, perbaiki integrasi, kemudian requeue dengan alasan audit.
- checksum tidak cocok: karantina backup; jangan restore.
- restore gagal: pertahankan database aktif, simpan log, dan eskalasi ke IT custodian.
- dugaan kebocoran data/secret: hentikan akses, rotasi secret, simpan evidence minimum, dan jalankan incident response.

## Bukti Minimum

Evidence readiness harus berisi project, environment, timestamp, operator, hasil seluruh check, referensi backup/checksum, hasil restore drill, ringkasan UAT, defect terbuka, serta keputusan sign-off. Secret, token, isi dokumen sensitif, dan data pribadi tidak boleh ditempelkan ke laporan.
