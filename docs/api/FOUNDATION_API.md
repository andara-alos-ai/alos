# API Foundation Operasional

| Metadata | Nilai |
|---|---|
| Status | Implementasi Pilot Internal |
| Versi | 0.9.0 |
| Cakupan | Enam workflow backend, governance bersama, dan AI Executive Brief |

## Prinsip

- Operasi bisnis menggunakan bearer token, konteks organisasi, role, dan akses project.
- Perintah yang dapat diulang wajib membawa `Idempotency-Key`.
- `X-Correlation-ID` menghubungkan work item, workflow run, agent run, dan audit.
- Endpoint autentikasi lokal tidak tersedia pada staging atau production.
- API key vendor dan token LLM tidak pernah diteruskan ke Core Agent atau browser.

## Endpoint

| Method | Path | Tujuan | Akses |
|---|---|---|---|
| `GET` | `/health` | status layanan | pemeriksaan sistem |
| `POST` | `/auth/local-token` | token pengembangan lokal | local/test saja |
| `GET` | `/agents` | registry 18 Core Agent | pengguna terautentikasi; read-only |
| `GET` | `/workflows` | enam definisi workflow | pengguna terautentikasi; read-only |
| `POST` | `/agent-runs/prepare` | validasi diagnostik kontrak runtime tanpa eksekusi bisnis | IT Admin |
| `POST` | `/users` | provisioning pengguna dan role per divisi | IT Admin |
| `POST` | `/projects` | membuat project berstatus DRAFT | Director atau IT Admin |
| `GET` | `/projects` | project dalam organisasi pengguna | pengguna terautentikasi |
| `POST` | `/finance/budgets` | membuat budget aktif per project | Finance atau Head divisi Finance |
| `POST` | `/finance/payment-requests` | memulai `FLOW-002` dan pemeriksaan DIA/CEA/BCA/ARA | Finance atau Head divisi Finance |
| `POST` | `/finance/payment-requests/{id}/decision` | menyetujui atau menolak dengan pemisahan tugas | Finance approver yang bukan requester |
| `POST` | `/finance/payment-requests/{id}/payment` | mencatat tindakan pembayaran dan bukti | Finance Human |
| `POST` | `/finance/payment-requests/{id}/reconciliation` | mencocokkan transaksi melalui FRA | Finance atau Head divisi Finance |
| `POST` | `/property/site-evidence` | memulai pemeriksaan bukti dan progres CEA/TPA | Property atau Head divisi Property |
| `POST` | `/property/site-evidence/{id}/review` | review manusia lalu KPI atau exception/CAPA | reviewer Property yang bukan pengunggah |
| `POST` | `/legal/documents` | memulai ekstraksi dan analisis izin atau kontrak | Legal atau Head divisi Legal |
| `POST` | `/legal/documents/{id}/review` | keputusan Legal Human atau pembukaan exception | reviewer Legal yang bukan pengaju |
| `POST` | `/hr/recruitment-requests` | membuat screening administratif SEA/HRA | HR atau Head dari divisi pemohon |
| `POST` | `/hr/recruitment-requests/{id}/decision` | keputusan kandidat dan checklist HPA | HR Human yang bukan pengaju |
| `POST` | `/executive/briefs` | membuat snapshot dan brief lintas divisi | AI Executive atau Direktur Utama |
| `POST` | `/executive/briefs/{id}/review` | menerbitkan atau meminta revisi brief | Direktur Utama |
| `POST` | `/leads` | intake lead dan memulai `FLOW-001` | Sales atau Head divisi Sales & Marketing |
| `GET` | `/work-items` | antrean kerja terfilter organisasi/divisi/project | pengguna terautentikasi |
| `POST` | `/workflow-runs/{id}/sales-assignment` | menetapkan Sales PIC dan follow-up awal | Sales atau Head divisi Sales & Marketing |
| `POST` | `/workflow-runs/{id}/interactions` | mencatat interaksi dan hasil pipeline | Sales PIC atau Head divisi Sales & Marketing |
| `POST` | `/documents` | mencatat metadata dokumen dan versinya | pengguna domain terautentikasi |
| `POST` | `/evidence` | mengaitkan versi dokumen sebagai evidence | pengguna domain terautentikasi |
| `POST` | `/approvals` | membuat permintaan approval | pemilik approval terautentikasi |
| `POST` | `/approvals/{id}/decision` | keputusan approval terpisah dari pemohon | approver berwenang |
| `POST` | `/exceptions` | membuka exception | governance role |
| `POST` | `/capas` | membuat rencana corrective/preventive action | governance role |

## Jalur Lead Saat Ini

`POST /leads` memeriksa kanal kontak, consent, role, dan akses project. Sistem kemudian:

1. menyiapkan eksekusi capability `SLA.validate_lead_fields`;
2. menyimpan lead, work item, workflow run, dan agent run dalam satu transaksi;
3. menetapkan tenggat respons awal 15 menit sebagai baseline pilot;
4. mencatat audit entry berantai hash;
5. berhenti pada langkah `sales-assignment` untuk keputusan manusia;
6. setelah Sales PIC ditetapkan, CFA membuat follow-up task tanpa mengirim pesan;
7. Sales PIC mencatat interaksi sebagai `follow_up`, `qualified`, `reserved`, atau
   `exception`;
8. reservasi menyelesaikan workflow hanya setelah dicatat Sales Human dan memiliki
   referensi reservasi.

Tidak ada komunikasi pelanggan, perubahan harga, pembayaran, atau aktivitas eksternal
yang dilakukan otomatis pada tahap foundation ini.

## Jalur Pembayaran Saat Ini

`POST /finance/payment-requests` membuat work item dan workflow run, mengaitkan dokumen
sebagai evidence, lalu menjalankan pemeriksaan terstruktur DIA, CEA, BCA, dan ARA pada
shared Agent Runtime. Anggaran yang tersedia dicadangkan sebagai `committed_amount` dan
permintaan diteruskan ke approval manusia yang berbeda dari requester.

Setelah disetujui, Finance Human tetap melakukan pembayaran di kanal resmi perusahaan
dan mencatat referensi beserta bukti melalui endpoint payment. FRA kemudian mencocokkan
referensi, nilai, dan mata uang secara deterministik. Hasil cocok memindahkan nilai budget
dari committed menjadi spent; ketidakcocokan membuka exception untuk penanganan manusia.
ALOS pada tahap ini tidak mengeksekusi transfer bank atau mengirim instruksi pembayaran.

## Jalur Bukti Lapangan Saat Ini

`POST /property/site-evidence` mengaitkan versi dokumen dengan work item Property,
memeriksa metadata evidence melalui CEA, dan menghitung selisih progres klaim terhadap
hasil pengukuran melalui TPA. Hasilnya selalu masuk ke review manusia; pengunggah tidak
dapat mereview bukti miliknya sendiri.

Keputusan `ACCEPTED` menghasilkan snapshot `PROPERTY_VERIFIED_PROGRESS` melalui KDA.
Keputusan `VARIANCE` membuka exception dan CAPA melalui CRA dengan tenggat awal tujuh
hari. Nilai progres final tetap berasal dari reviewer berwenang dan formula KPI perusahaan
yang masih TBD tidak dibuat atau diasumsikan oleh sistem.

## Jalur Izin dan Kontrak Saat Ini

`POST /legal/documents` membuat kasus dan paket evidence Legal. DIA menyiapkan metadata
terstruktur, LPA menangani jenis `PERMIT`, CLA menangani jenis `CONTRACT`, dan CEA
memeriksa kelengkapan paket sebelum masuk ke `legal-review`.

Keputusan akhir tetap milik Legal Human yang berbeda dari pengaju. Izin tidak dapat
berstatus disetujui sebelum reviewer menyatakan sumber resmi telah diverifikasi.
Keputusan revisi atau penolakan membuka exception dan memblokir work item. Sistem tidak
memberikan opini hukum, menyatakan izin sah secara otonom, atau menandatangani kontrak.

## Jalur Rekrutmen Saat Ini

`POST /hr/recruitment-requests` menerima metadata kebutuhan posisi, versi kriteria,
alias kandidat, dan referensi dokumen yang telah disanitasi. SEA membentuk work plan dari
workflow yang dirilis, sedangkan HRA membandingkan kriteria administratif secara
terstruktur dan meneruskan seluruh hasil ke HR Human.

Agent tidak memilih atau menolak kandidat. Keputusan hanya tersedia untuk role HR dan
harus dilakukan oleh pengguna berbeda dari pengaju. Kandidat terpilih memicu HPA untuk
membuat checklist berkas personalia berstatus belum lengkap; kandidat ditolak menutup
workflow tanpa membuat personnel file. API tidak menerima atribut sensitif seperti agama,
etnis, gender, kondisi kesehatan, atau data keluarga pada tahap pilot.

## Jalur AI Executive Saat Ini

`POST /executive/briefs` membekukan snapshot periode dari fakta ALOS: work item aktif,
approval tertunda, exception, CAPA, KPI terverifikasi, serta catatan Sales, Finance,
Property, Legal, dan HR. KDA, CRA, dan ARA mengagregasi angka secara deterministik;
MCA menyusun narasi template yang setiap angkanya menunjuk ke field snapshot dan hash
sumber.

Brief berhenti pada `brief-review`. Hanya role `DIRECTOR` yang dapat menerbitkan atau
meminta revisi. Permintaan revisi membuka exception. Role `DIRECTOR`, `AI_EXECUTIVE`,
dan `AUDITOR` merupakan role tingkat organisasi tanpa penempatan divisi, sehingga tidak
mengubah enam workspace divisi yang LOCKED. LLM belum digunakan pada jalur ini; adaptor
LLM nantinya hanya boleh memperbaiki bahasa tanpa menghitung ulang atau mengubah fakta.

## Batas Pilot

Token lokal merupakan bootstrap provider untuk pengembangan, bukan pengganti identity
provider perusahaan. Formula SLA 15 menit, role final, serta kebijakan akses masih dapat
berubah melalui review dan rilis konfigurasi sebelum production.
