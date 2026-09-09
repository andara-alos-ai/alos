# ALOS — Repository Transition Map

Dokumen ini adalah peta transisi dari foundation ke struktur target. Ia tidak
memberi izin penghapusan otomatis. Setiap pemindahan fisik dilakukan hanya
sesudah test pengganti tersedia dan dalam commit kecil yang dapat di-rollback.

| Area saat ini | Keputusan | Tujuan akhir | Syarat sebelum perubahan fisik |
| --- | --- | --- | --- |
| `apps/web` | pertahankan | `apps/web` sebagai Mission Control | route/API contract dan UI smoke test |
| `services/platform/src/alos/main.py`, `config.py`, `security/` | pertahankan dan perluas | application shell/security | auth/health tests tetap PASS |
| `services/platform/src/alos/identity/` | migrasi bertahap | `domain/identity/` | compatibility import dan unit test |
| `services/platform/src/alos/audit/` | migrasi bertahap | `domain/audit/` + audit writer infrastructure | append-only integration test |
| `services/platform/src/alos/persistence/` | pertahankan sementara | `infrastructure/postgres/` | fresh migration dan repository test |
| `services/platform/src/alos/model_gateway.py` | pecah bertahap | `domain` policy + `infrastructure/model_gateway` adapter | fake/OpenAI adapter contract test |
| `services/platform/tests/` | rapikan bertahap | unit/integration/contract/e2e | test discovery tidak berubah |
| `infra/`, `scripts/`, `.env.example` | pertahankan | environment/deploy boundary | preflight dan restore drill PASS |
| `data/synthetic/` | pertahankan dan tambah fixture | source/evidence/R&D test data | tidak berisi data nyata |
| `definitions/` | pertahankan dan isi | contract/prompt/tool/policy/schema registry | JSON Schema validation |
| `docs/*` lama | pertahankan sebagai evidence | archive setelah canonical docs stabil | seluruh tautan diperbarui |
| `.git`, `.env`, credential, history, backup | selalu pertahankan | tidak berubah | tidak masuk scope cleanup |

## Tidak ada kandidat hapus saat ini

Tidak ada folder aplikasi baru yang perlu dihapus pada tahap redesign ini.
Folder cache lokal, virtual environment, `node_modules`, dan `tmp` bukan bagian
dari struktur produk maupun artefak commit; mereka tidak dijadikan dasar
keputusan cleanup source. Penghapusan material hanya dapat dilakukan setelah
inventaris terpisah, test pengganti, dan approval eksplisit.
