# Backup dan Restore ALOS

Database ALOS memuat audit, approval, dan data operasional. Perlakukan dump dan
manifest sebagai `RESTRICTED`; simpan pada lokasi terenkripsi dengan retensi dan
akses yang disetujui organisasi.

## Backup PostgreSQL

Dengan service PostgreSQL yang sehat, jalankan dari root repository:

```powershell
.\scripts\database\backup-alos.ps1 -BackupDirectory D:\ALOS-Backup
```

Script membuat dump PostgreSQL custom dan manifest SHA-256. Simpan keduanya
bersama-sama. Untuk compose non-default, sertakan `-ComposeFile` dengan path
yang eksplisit.

## Restore drill

Jangan melakukan restore langsung ke database aktif dari script ini. Verifikasi
backup pada database sementara terisolasi:

```powershell
.\scripts\database\test-alos-restore.ps1 -BackupFile D:\ALOS-Backup\alos-YYYYMMDDTHHMMSSZ.dump
```

Script memverifikasi manifest dan checksum, membuat database sementara,
menjalankan `pg_restore`, memeriksa catatan migrasi, kemudian menghapus database
uji. Kegagalan checksum atau integrity check menghentikan proses sebelum data
aktif tersentuh.

## Restore insiden

Restore production adalah tindakan change-controlled: hentikan writer, worker,
dan scheduler; verifikasi checksum dan compatibility migrasi; peroleh persetujuan
authority; lalu pulihkan oleh operator database berwenang. Setelah itu jalankan
readiness API, cek heartbeat worker/scheduler, dan catat keputusan di audit.
