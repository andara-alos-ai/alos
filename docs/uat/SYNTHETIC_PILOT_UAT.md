# UAT Pilot Sintetis ALOS

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
| UAT-07 | Shared Runtime | evaluasi 18 Core serta recovery drill | handler, evidence, warning, audit, dan bukti restore tersedia |
| UAT-08 | Genesis | REUSE/EXTEND/CREATE → dua review → staging → release | tidak ada self-review atau perubahan production |

## Bukti dan Keputusan

Setiap skenario mencatat tester, role, waktu, data sintetis, langkah, hasil aktual, screenshot/referensi evidence, defect, severity, dan keputusan `ACCEPTED`, `ACCEPTED_WITH_RISK`, atau `REJECTED`.

Hasil dicatat pada menu **UAT & Go-Live**. Status skenario yang dianggap lulus hanya `PASSED` atau `PASSED_WITH_RISK`; keduanya wajib memiliki hasil aktual dan minimal satu evidence. Risk yang dapat diterima melalui UAT hanya `LOW` atau `MEDIUM`. Temuan `HIGH` atau `CRITICAL` harus diperbaiki dan diuji ulang.

Sign-off wajib diberikan oleh Kepala Sales & Marketing, Kepala Keuangan, Kepala Property, Kepala HR, Kepala Legal, IT custodian, AI Executive, dan Direktur Utama. Operator domain dapat menguji tetapi tidak dapat menggantikan business owner. Keputusan yang sudah ditandatangani bersifat final untuk satu siklus; penolakan memerlukan siklus baru setelah perbaikan.

Controlled pilot hanya dapat dibuka setelah tidak ada defect kritis/tinggi, seluruh owner menerima ruang lingkupnya, recovery evidence tersedia, serta keputusan TBD yang memengaruhi tindakan material telah ditutup atau diblokir secara aman. Kelulusan test otomatis adalah bukti teknis, bukan pengganti sign-off UAT manusia.

## Status Siklus

`DRAFT → IN_PROGRESS → READY_FOR_SIGNOFF → ACCEPTED | ACCEPTED_WITH_RISK | REJECTED`

Transisi dihitung oleh aturan deterministik. LLM tidak digunakan untuk menentukan status, severity, kelengkapan evidence, atau penerimaan akhir.
