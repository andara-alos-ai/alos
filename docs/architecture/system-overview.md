# System overview

## ALOS, ARA, dan GENESIS

ALOS adalah satu enterprise platform. ARA adalah AI workspace yang menghadap
user. GENESIS adalah control plane AI, Capability/Agent Factory, dan pengelola
shared runtime di dalam ALOS.

```text
User
  → ARA workspace / operational UI
    → ALOS backend enforcement
      ├─ GENESIS analyze + capability resolution + draft
      ├─ Registry + governance + evidence + audit
      ├─ shared Agent Runtime
      │   ├─ ModelGateway → approved provider adapter
      │   └─ ToolExecutor → registered typed tool
      └─ PostgreSQL + worker + scheduler
```

ARA tidak memiliki authority sendiri. GENESIS juga bukan user manusia,
division, approver, atau release authority. Semua keputusan keamanan dan state
transition dilakukan backend.

## CURRENT IMPLEMENTATION

- Web memakai Next.js di `apps/web`. ARA sudah tampil sebagai workspace pada UI,
  tetapi komponennya masih memuat state/presentation lokal; integrasi ARA penuh
  dengan layanan backend belum selesai. Module key/route web masih memakai
  `genesis` sebagai compatibility route untuk surface ARA.
- Platform memakai FastAPI di `services/platform/src/alos` dengan boundary
  modular untuk identity, documents, capabilities, GENESIS, release, runtime,
  tools, jobs, audit, dan persistence.
- PostgreSQL adalah state store utama. Migration `001`–`036` bersifat immutable.
- Factory menyimpan requirement, hasil analisis, keputusan implementasi,
  dependency resolution, draft proposal, generated-test proposal, tenant scope,
  correlation ID, serta linkage governance.
- Proposal dengan komponen Agent membuat Agent Contract `DRAFT` dan release
  request. Proposal non-Agent belum memiliki generic artifact/release path.
- Shared runtime memilih exact Agent Version, memeriksa scope, lifecycle,
  permission, tool, budget, source/evidence, kill switch, serta cancellation,
  kemudian mencatat run dan audit.
- `ModelGateway` memiliki adapter OpenAI dan Gemini. Gemini dibatasi ke
  `local`/`test`; production hanya mengizinkan `disabled` atau OpenAI. Nilai
  konfigurasi provider lain bukan bukti adapter runtime.
- `ToolExecutor` menjalankan handler typed yang terdaftar dan approved; agent
  tidak mendapat akses langsung ke database, credential, filesystem, SDK
  provider, atau HTTP bebas.

## TARGET ARCHITECTURE

GENESIS harus menjadi capability-first factory, bukan Agent-only generator.
Semua tipe hasil resolusi memakai lifecycle, version, evidence, governance,
release, monitoring, suspend, dan rollback yang konsisten. Target governance
organisasi adalah automated validation oleh GENESIS, review teknis/operator
oleh Divisi IT, lalu keputusan final Director.

`CREATE`/`DRAFT != APPROVE != RELEASE != ACTIVE`. Penamaan layar atau tombol
tidak boleh menggabungkan keputusan tersebut.

## Deployment topology

Repository memuat beberapa topology yang tidak boleh dicampur:

- local development: PostgreSQL via `infra/compose/compose.yaml`, API dan web
  dapat dijalankan dari host;
- staging Compose: `infra/compose/compose.staging.yaml` dengan PostgreSQL
  container, platform, worker, scheduler, web, dan Caddy;
- production Compose: `infra/compose/compose.production.yaml` dengan PostgreSQL
  eksternal dan S3-compatible object storage;
- production native: unit systemd dan `Caddyfile.vps`, dengan PostgreSQL serta
  object storage eksternal.

Native production adalah runbook operasional utama saat ini. Keberadaan
manifest bukan bukti bahwa environment tertentu sudah deployed atau ready.

## Boundaries

PydanticAI/Pydantic Evals adalah komponen engine/evaluation di belakang
boundary milik ALOS; keduanya bukan control plane. Next.js bukan enforcement
boundary. PostgreSQL constraints, repository/service policy, authorization,
ModelGateway, ToolExecutor, dan runtime guard adalah authority aktual.
