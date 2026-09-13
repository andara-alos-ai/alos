# ALOS / GENESIS

ALOS adalah satu enterprise platform untuk operasi perusahaan. Di dalam ALOS,
**ARA** adalah AI workspace yang dipakai user, sedangkan **GENESIS** adalah AI
control plane, Capability/Agent Factory, dan pengelola shared runtime. Agent,
skill, workflow, serta capability lain bukan aplikasi atau service terpisah.

## Arsitektur singkat

| Lapisan | Tanggung jawab | Implementasi saat ini |
| --- | --- | --- |
| ARA | Workspace AI untuk percakapan, konteks, dan pekerjaan user | Presentasi web tersedia; integrasi penuh ARA dengan API masih target |
| GENESIS | Analisis requirement, resolusi capability, draft, evidence, dan governance handoff | Factory persisten tersedia; handoff release baru lengkap untuk proposal yang memuat Agent |
| Platform | Enforcement, API, registry, governance, runtime, audit, job | FastAPI modular monolith |
| Data | State transaksional dan traceability | Satu PostgreSQL dengan migration append-only |
| Presentation | UI ARA, Factory, governance, registry, dan operasi | Next.js; bukan security boundary |

Model hanya dipanggil melalui `ModelGateway`; tool hanya dieksekusi melalui
`ToolExecutor`. Adapter runtime yang ada adalah OpenAI serta Gemini
(`local`/`test` saja). Tidak ada adapter runtime Anthropic atau local model.

## Factory lifecycle

```text
Requirement
→ GENESIS Analyze
→ Resolve capability
→ Generate DRAFT
→ automated validation/test/eval/security
→ IT Review
→ Submit to Director
→ Director APPROVE / REJECT
→ Release
→ Active
→ Monitor / Suspend / Rollback
```

`CREATE`/`DRAFT`, `APPROVE`, `RELEASE`, dan `ACTIVE` adalah keputusan berbeda.
GENESIS tidak boleh self-approve atau self-release. Target organisasi hanya
mewajibkan Divisi IT sebagai technical/operator reviewer dan Director sebagai
pengambil keputusan final. Backend branch saat ini masih mempertahankan
workflow release legacy lima-duty untuk kompatibilitas; lihat
[governance model](docs/governance/governance-model.md).

## Security boundaries

- Backend adalah enforcement authority; UI hanya presentation dan workflow aid.
- Organization, workspace, division, project, serta tenant scope divalidasi
  server-side.
- Tool, permission, model route, budget, lifecycle, kill switch, cancellation,
  release, dan rollback ditegakkan deterministik.
- Maker tidak boleh menyetujui perubahan material buatannya sendiri.
- Review/reject terikat version; active version dan rollback target harus tepat.
- Release, version, evidence, rollback, dan audit harus dapat ditelusuri.

## Repository map

```text
apps/web/                 Next.js presentation
services/platform/        FastAPI platform, GENESIS, governance, runtime
infra/database/           migration 001-036 (immutable)
infra/compose/            local, staging, dan production Compose manifests
infra/systemd/            native VPS services
infra/proxy/              Caddy configuration
definitions/              versioned declarative contracts
scripts/                  database, deployment, dan validation utilities
docs/                     dokumentasi teknis kanonik dan archive
```

Branch pengembangan aktif: **`epic/genesis-agent-factory`**. Branch `develop`
hanya comparison baseline lama untuk lesson learned governance/UAT, bukan
branch aktif pekerjaan ini. Migration `001`–`036` tidak boleh diubah atau
di-rename; migration baru harus append-only.

## Local quality commands

Setelah dependency terpasang (`pnpm install --frozen-lockfile` dan
`python -m pip install -e "services/platform[dev]"`), jalankan dari repository
root:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Untuk integration test PostgreSQL, hidupkan service lokal, set
`ALOS_RUN_POSTGRES_TESTS=1`, lalu jalankan:

```powershell
python -m pytest services/platform/tests
```

Detail setup dan quality gate ada di
[panduan development](docs/development/README.md).

Mulai dari [peta dokumentasi kanonik](docs/README.md), lalu baca
[system overview](docs/architecture/system-overview.md),
[GENESIS Factory](docs/architecture/genesis-agent-factory.md),
[Agent Runtime](docs/architecture/agent-runtime.md), dan
[lifecycle governance](docs/governance/agent-lifecycle.md).
