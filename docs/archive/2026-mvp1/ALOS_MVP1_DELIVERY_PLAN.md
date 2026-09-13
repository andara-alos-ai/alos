# ALOS — Delivery Plan: MVP1 Proof

## Hasil yang harus terbukti

MVP1 membuktikan bahwa Genesis dapat membuat dan menjalankan minimal satu
logical agent secara end-to-end dalam shared runtime, dengan data sintetis dan
human approval. Proof case adalah Property R&D Mission; tiga validation agent
memastikan pattern sama dapat dipakai lintas konteks enam divisi.

MVP1 bukan janji bahwa Genesis sudah boleh menghubungi customer, membeli
iklan, membayar vendor, menerbitkan website production, atau mengambil
keputusan legal/HR/keuangan.

## Lima hari pembuktian

| Hari | Outcome | Bukti exit |
| --- | --- | --- |
| 1 — Foundation | monolith, auth scope, PostgreSQL clean migration, source/artifact/work schema final, local security boundary | fresh migration, health, auth tests, schema review |
| 2 — Genesis R&D design-time | source registry/version/citation, conversation/requirement, Research Mission menghasilkan Research Brief + Task Plan + draft Contract | API/UI minimal dan integration test cited artifact |
| 3 — Contract dan runtime | prompt/model/tool registry, Model Gateway OpenAI adapter + fake test, permission/cost/schema guardrail, shared executor dan scheduler dasar | fake-provider, tool denial, cost cap, scheduled read-only run |
| 4 — Governance lifecycle | validation/test/diff, review queue, staging/release/activate, suspension/kill/rollback | CREATE → REVIEW → ACTIVE → RUN → KILL/ROLLBACK evidence |
| 5 — Validation dan release decision | tiga validation agent dibuat Genesis, enam scope divisional, negative/security/recovery tests, VPS/OpenAI low-cap smoke | UAT report, scan report, GO/HOLD/NO-GO decision |

## Prioritas implementasi

1. **P0 — safety and proof path:** Natural-language requirement sampai satu
   safe run dengan citation, approval, audit, cost, kill switch, rollback.
2. **P1 — task cadence:** WorkItem recurring dan Mission Control minimal untuk
   melihat pekerjaan harian/mingguan/bulanan serta approval queue.
3. **P2 — expansion:** website preview generator, richer experiment runner,
   tools/integrations tambahan, dan automasi R&D lebih luas setelah proof P0.

Dashboard kompleks bukan dependency P0. Web pada MVP1 hanya menyediakan
input requirement, daftar source/artifact, approval queue, status task/agent
run, dan audit/cost/kill switch.

## Perubahan schema yang direncanakan

Migration berikutnya bersifat append-only dan menambahkan `work`, citation dan
evidence relation, Research Mission/finding/opportunity, policy registry, serta
transition/audit enforcement. Baseline `001` tidak ditulis ulang pada database
yang pernah dipakai. Tidak ada data production, credential, `.env`, atau
riwayat Git yang dihapus.

## Deployment gate VPS dan OpenAI

VPS/OpenAI bukan lingkungan eksperimen pertama. Sebelum deploy, semua test
lokal/containers dengan fixture sintetis wajib PASS. Smoke pertama:

- memakai commit bersih yang sudah direview;
- memakai secret server-side dan `store=false`;
- prompt non-sensitif serta no tool/no external side effect;
- timeout dan hard low cost cap;
- correlation ID, usage, error redaksi, dan rollback procedure terbukti.

Gagal satu gate berarti `HOLD`; tidak ada bypass untuk mengejar jadwal.
