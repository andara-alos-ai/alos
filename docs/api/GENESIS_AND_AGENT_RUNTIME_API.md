# API Genesis dan Shared Agent Runtime

## Shared Runtime

`POST /api/v1/agent-runtime/execute` mengevaluasi capability melalui shared runtime untuk agent yang dipilih dari Agent Registry. Request membawa agent, capability, input reference, tool yang diminta, klasifikasi data, idempotency key, dan correlation ID opsional.

Endpoint memeriksa business role, project scope, Agent Contract, Capability Contract, dan Tool Registry. Endpoint tidak menjalankan tindakan eksternal atau keputusan material, selalu menghasilkan `production_effect=false`, dan menyimpan run serta audit tanpa menyimpan payload mentah.

Endpoint ini mencakup capability yang belum menjadi bagian enam workflow, termasuk validasi invoice TIA dan penyusunan draft MCA_MKT.

## Genesis

| Method | Path | Tujuan |
|---|---|---|
| `GET` | `/api/v1/genesis/source-packs` | membaca metadata, status, hash, dan batas penggunaan source pack; khusus Direktur, AI Executive, Kepala Divisi, IT Admin, dan Auditor |
| `GET` | `/api/v1/genesis/configuration-registers` | membaca pemetaan kanonik Master dan A–N, owner, status, disposition, lineage, dan decision blocker tanpa efek produksi |
| `POST` | `/api/v1/genesis/requests` | membuat proposal REUSE, EXTEND, atau CREATE |
| `GET` | `/api/v1/genesis/requests/{id}` | membaca status, test, diff, review, dan release package |
| `POST` | `/api/v1/genesis/requests/{id}/reviews` | memberi review BUSINESS atau TECHNICAL |
| `POST` | `/api/v1/genesis/requests/{id}/stage` | membuat package staging setelah dua approval |
| `POST` | `/api/v1/genesis/requests/{id}/release` | merilis package design-time tanpa deployment |

Semua endpoint memakai bearer token dan isolasi organisasi. Pemohon tidak dapat menyelesaikan gate miliknya sendiri. Conflict dan duplicate gate ditolak secara transaksional. `source_references` wajib menunjuk Source Registry; source `DRAFT` dapat dianalisis tetapi tidak dapat memasuki staging atau release. Canonical Configuration Registry bersifat baca-saja melalui API dan tidak menyediakan operasi aktivasi.
