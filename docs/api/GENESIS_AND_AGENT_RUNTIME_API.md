# API Genesis dan Shared Agent Runtime

## Shared Runtime

`POST /api/v1/agent-runtime/execute` mengevaluasi capability melalui runtime yang sama untuk seluruh 18 Core Agent. Request membawa agent, capability, input reference, tool yang diminta, klasifikasi data, idempotency key, dan correlation ID opsional.

Endpoint memeriksa business role, project scope, Agent Contract, Capability Contract, dan Tool Registry. Endpoint tidak menjalankan tindakan eksternal atau keputusan material, selalu menghasilkan `production_effect=false`, dan menyimpan run serta audit tanpa menyimpan payload mentah.

Endpoint ini mencakup capability yang belum menjadi bagian enam workflow, termasuk validasi invoice TIA dan penyusunan draft MCA_MKT.

## Genesis

| Method | Path | Tujuan |
|---|---|---|
| `POST` | `/api/v1/genesis/requests` | membuat proposal REUSE, EXTEND, atau CREATE |
| `GET` | `/api/v1/genesis/requests/{id}` | membaca status, test, diff, review, dan release package |
| `POST` | `/api/v1/genesis/requests/{id}/reviews` | memberi review BUSINESS atau TECHNICAL |
| `POST` | `/api/v1/genesis/requests/{id}/stage` | membuat package staging setelah dua approval |
| `POST` | `/api/v1/genesis/requests/{id}/release` | merilis package design-time tanpa deployment |

Semua endpoint memakai bearer token dan isolasi organisasi. Pemohon tidak dapat menyelesaikan gate miliknya sendiri. Conflict dan duplicate gate ditolak secara transaksional.
