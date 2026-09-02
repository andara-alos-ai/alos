# Kesiapan Pilot dan Recovery ALOS

## Tujuan

Runbook ini menjadi gate operasional sebelum controlled pilot. Pilot hanya memakai data sintetis atau data yang telah disanitasi. Hasil readiness bukan izin production dan tidak menggantikan persetujuan pemilik bisnis, IT, Security, dan Direktur Utama.

## Readiness Gate

Pilih proyek pada ALOS, lalu buka **Kesehatan Sistem**. Pemeriksaan membaca profil terversi di `definitions/pilot/controlled-pilot/profile.json` dan menilai:

- proyek aktif dan enam divisi tersedia;
- Direktur Utama, AI Executive, technical custodian, serta operator domain aktif;
- separation of duties untuk Keuangan, Property, HR, dan Legal;
- agent yang diperlukan dan enam workflow tersedia pada registry;
- dokumen uji aman, dead-letter, dan heartbeat worker;
- OIDC, object storage, malware scan, serta bukti recovery sesuai environment.

Status `BLOCKED` wajib ditutup sebelum UAT. Status `ATTENTION` memerlukan penerimaan risiko tertulis dan tidak pernah mengizinkan production secara otomatis.

## Provisioning Pilot Sintetis

Provisioning opsional tersedia untuk environment lokal atau staging non-production. Script bersifat idempotent, menolak data selain `example.test`, menolak production, dan tidak mencetak token.

1. Pastikan API, PostgreSQL, dan migrasi terbaru telah aktif.
2. Dari root repository, jalankan `./scripts/development/provision-controlled-pilot.ps1`.
3. Buka halaman login, pilih **Profil pilot**, lalu pilih akun pengujian sesuai divisi.
4. Buka **Kesehatan Sistem** dan tutup seluruh pemeriksaan `BLOCKED`.

Pada environment lokal, script membuat token bootstrap sementara, memprovisikan 18 akun
`example.test`, role, divisi, project assignment, proyek aktif, dan satu data awal pada
masing-masing dari enam workflow. Token tidak dicetak atau disimpan. Eksekusi ulang aman:
record yang sudah ada dibaca dan tidak dibuat ulang. Gunakan `-SkipScenarioData` jika hanya
memerlukan akun dan proyek tanpa transaksi awal.

Untuk target non-lokal, parameter `-AllowRemote` hanya boleh digunakan setelah hostname dan
environment staging diverifikasi. Token IT Admin dan Direktur wajib diberikan melalui
`ALOS_PILOT_ADMIN_TOKEN` dan `ALOS_PILOT_DIRECTOR_TOKEN`, serta gunakan `-SkipScenarioData`
karena dokumen staging wajib melalui unggahan dan malware scan. Data pengguna sebenarnya
tetap dibuat melalui proses IAM resmi, bukan fixture sintetis.

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

## Pelaksanaan UAT dan Go-Live Gate

1. Buka **UAT & Go-Live**, pilih proyek `ACTIVE`, lalu buat satu siklus UAT.
2. IT atau Direktur memulai siklus; setiap operator menjalankan skenario sesuai role dan divisinya.
3. Catat hasil aktual dan referensi evidence. Lampirkan hasil restore drill pada UAT-07.
4. Perbaiki `FAILED`, `BLOCKED`, `HIGH`, dan `CRITICAL`; jangan menerimanya sebagai risiko.
5. Setelah delapan skenario lulus, minta sign-off dari lima Kepala Divisi bisnis, IT, AI Executive, dan Direktur.
6. Buka go-live gate. Status `READY` atau keputusan `ACCEPTED_WITH_RISK` tetap tidak mendeploy sistem secara otomatis; release mengikuti otorisasi deployment terpisah.

Sistem tidak membuat tanda tangan atau hasil uji atas nama manusia. Jika satu scope menolak, siklus menjadi `REJECTED` dan tim membuat siklus baru setelah perbaikan.

## Respons Kegagalan

- `BLOCKED`: hentikan UAT pada domain terkait dan ikuti remediation di layar.
- worker tidak baru: periksa service worker, koneksi database, dan log siklus terakhir.
- dead-letter: identifikasi penyebab, perbaiki integrasi, kemudian requeue dengan alasan audit.
- checksum tidak cocok: karantina backup; jangan restore.
- restore gagal: pertahankan database aktif, simpan log, dan eskalasi ke IT custodian.
- dugaan kebocoran data/secret: hentikan akses, rotasi secret, simpan evidence minimum, dan jalankan incident response.

## Bukti Minimum

Evidence readiness harus berisi project, environment, timestamp, operator, hasil seluruh check, referensi backup/checksum, hasil restore drill, ringkasan UAT, defect terbuka, serta keputusan sign-off. Secret, token, isi dokumen sensitif, dan data pribadi tidak boleh ditempelkan ke laporan.
