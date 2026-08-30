# UAT Pilot Sintetis ALOS Internal v1

## Tujuan

UAT membuktikan bahwa pekerjaan dapat diselesaikan oleh aktor yang benar, keputusan material tetap pada manusia, dan setiap langkah dapat ditelusuri. Gunakan data sintetis; jangan gunakan data perusahaan asli sebelum kebijakan data disahkan.

## Skenario Minimum

| ID | Workspace | Skenario | Hasil penerimaan |
|---|---|---|---|
| UAT-01 | Sales & Marketing | lead → assignment → follow-up → reservation | consent, PIC, evidence, status, dan audit benar |
| UAT-02 | Keuangan | payment request → approval → payment record → reconciliation | SoD, budget, evidence, exception, dan audit benar |
| UAT-03 | Property | site evidence → review → KPI atau CAPA | variance deterministik dan reviewer terpisah |
| UAT-04 | Legal | permit/contract → extraction → review Legal | sumber resmi, evidence, dan keputusan manusia terjaga |
| UAT-05 | HR | recruitment request → screening → decision → personnel checklist | data sensitif dibatasi dan keputusan HR manual |
| UAT-06 | AI Executive | agregasi → brief → review Direktur | seluruh angka berasal dari snapshot sistem |
| UAT-07 | Shared Runtime | evaluasi satu capability dari setiap 18 Core | handler, evidence, warning, dan audit tersedia |
| UAT-08 | Genesis | REUSE/EXTEND/CREATE → dua review → staging → release | tidak ada self-review atau perubahan production |

## Bukti dan Keputusan

Setiap skenario mencatat tester, role, waktu, data sintetis, langkah, hasil aktual, screenshot/referensi evidence, defect, severity, dan keputusan `ACCEPTED`, `ACCEPTED_WITH_RISK`, atau `REJECTED`.

Pilot internal hanya dapat dibuka setelah tidak ada defect kritis/tinggi, enam owner divisi menerima skenario domainnya, Direktur menerima brief, IT menerima operasional, dan seluruh keputusan TBD yang memengaruhi tindakan material telah ditutup atau diblokir secara aman.
