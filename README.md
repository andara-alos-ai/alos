# ALOS

ALOS adalah enterprise operating platform PT Andara Rejo Makmur. Repository ini
menampung satu platform dalam bentuk **monorepo + modular monolith**: aplikasi web,
backend, runtime AI, governance, definitions, persistence, dan deployment foundation.

**ARA** adalah AI workspace yang berhadapan langsung dengan user: percakapan,
contextual assistance, pencarian, drafting, dan bantuan dokumen. **GENESIS** adalah AI
control plane serta Capability/Agent Factory: menganalisis kebutuhan, memilih bentuk
capability, menghasilkan DRAFT, mengumpulkan evidence validasi, dan menyerahkan versi
tepat ke governance. GENESIS bukan chatbot, role manusia, Director, atau pemegang
otoritas bisnis final.

## Arsitektur dan dependency direction

```text
User → Operational UI / ARA → ALOS Backend
                               ├─ Identity, RBAC, Scope
                               ├─ Operational Domains
                               ├─ GENESIS Factory
                               ├─ Capability Registry / Skills / Memory
                               ├─ Shared Agent Runtime
                               ├─ ModelGateway → Provider Adapter
                               └─ ToolExecutor → Approved Execution Backend
```

Factory bersifat **capability-first**. Requirement dapat diselesaikan sebagai Agent,
Skill, Workflow, Rule, Validator, Report, Human Task, Schedule, Event Handler,
connector/tool requirement, atau composite. Agent dipilih hanya bila reasoning atau
autonomy diperlukan. Agent bukan package/aplikasi tersendiri, melainkan logical,
versioned artifact yang terdiri dari Contract, prompt, logical model route, Skill,
Tool, permission, scope, test/eval, dan runtime configuration. Semua Agent memakai
shared Agent Runtime.

Boundary platform:

- `capabilities/` adalah katalog authoritative untuk availability, backing tool,
  scope, risk, classification, configuration, dan lifecycle capability.
- `skills/` mengelola Skill berversi dan hanya memuat versi ACTIVE yang authorized.
- `memory/` menyimpan dan mengambil memory dengan organization/workspace/tenant serta
  optional division/project scope, classification, retention, expiry, dan lineage.
- `runtime/` menegakkan contract, context budget, tool policy, delegation, audit,
  cancellation, dan execution limit tanpa mengetahui SDK provider.
- `model_gateway/` memetakan logical route `light`, `standard`, atau `critical` ke
  provider/model server-side. OpenAI adalah adapter aktif saat ini; provider baru
  ditambahkan melalui adapter dan registry, bukan melalui perubahan Runtime/Factory.
- `tools/` adalah satu-satunya jalur eksekusi Tool. PydanticAI hanya berinteraksi
  melalui ALOS adapter dan `ToolExecutor`.
- `release/` menjaga evidence, keputusan manusia, release, active version, suspend,
  dan rollback. Automated validation bukan human approval.

Lifecycle governance memisahkan `CREATE/DRAFT`, `APPROVE`, `RELEASE`, dan `ACTIVE`.
Target organisasi adalah automated validation → IT Review → Director decision →
Release → Active. Backend legacy multi-duty tetap dipertahankan sebagai compatibility
behavior sampai migrasi terpisah selesai.

## Prinsip keamanan inti

- Backend adalah enforcement authority; UI dan LLM bukan permission engine.
- Permission, RBAC, scope, classification, budget, dan lifecycle divalidasi server-side.
- Semua provider model melalui `ModelGateway`; semua Tool/connector melalui `ToolExecutor`.
- Child delegation tidak boleh memperluas scope, permission, Tool, atau budget parent.
- Material change tidak boleh self-approve dan semua execution material harus auditable.
- Secret, production data, dan dokumen rahasia tidak boleh masuk repository.

## Peta repository

```text
.github/                  governance, templates, dependency updates, quality CI
apps/web/                 Next.js presentation layer
services/platform/src/alos/
  ara/                    user-facing AI workspace
  genesis/factory/        capability-first control plane
  capabilities/           authoritative capability catalog
  skills/                 governed Skill versions
  memory/                 scoped semantic memory
  runtime/                shared Agent Runtime and context/delegation boundaries
  model_gateway/          routes, policy, pricing, factory, provider adapters
  tools/                  registry and enforced execution
  release/                governance and release lifecycle
  jobs/                   scheduler, worker, long-running work foundation
  persistence/            database connection and migration runner
definitions/              declarative, versioned contracts (tanpa dummy definition)
infra/database/           immutable append-only SQL migrations
infra/                    Compose, Docker, proxy, environment, systemd
scripts/                  database, deployment, and validation utilities
data/                     synthetic/sanitized development and test artifacts only
docs/                     active technical docs and preserved archive
```

## Technology stack

- Web: Next.js, React, TypeScript, Vitest, ESLint.
- Platform: Python 3.12+, FastAPI, Pydantic, PydanticAI, SQLAlchemy/psycopg.
- Data: PostgreSQL + pgvector; SQL migration append-only.
- Delivery: pnpm workspace, Docker/Compose, Caddy, systemd, GitHub Actions.

## Local development

Prasyarat: Node.js 22+, pnpm 11, Python 3.12, dan PostgreSQL/pgvector untuk
integration test. Salin `.env.example` menjadi `.env` dan isi hanya credential lokal;
`.env` tidak boleh di-commit.

```powershell
pnpm install --frozen-lockfile
python -m pip install -e "services/platform[dev]"
pnpm dev:web
pnpm dev:api
```

Quality gate:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Untuk PostgreSQL integration test, gunakan disposable database, set
`ALOS_RUN_POSTGRES_TESTS=1`, jalankan fresh migration, lalu backend suite. Migration
existing tidak boleh diubah/rename; migration baru harus append-only.

## Dokumentasi, data, dan branch

Mulai dari [peta dokumentasi](docs/README.md), [system overview](docs/architecture/system-overview.md),
[ARA](docs/architecture/ara.md), [capability model](docs/architecture/capability-model.md),
[ModelGateway](docs/architecture/model-gateway.md), [context runtime](docs/architecture/context-runtime.md),
dan [security model](docs/security/security-model.md). Dokumen archive adalah historical
evidence, bukan status implementasi aktif.

Kebijakan data ada di [data/README.md](data/README.md). Branch
`epic/genesis-agent-factory` adalah source of truth selama pekerjaan arsitektur ini;
setelah PR disetujui, `main` menjadi canonical integration branch dan pekerjaan baru
memakai short-lived feature branch.

Repository ini dilisensikan dengan [MIT License](LICENSE), Copyright (c) 2026
PT Andara Rejo Makmur.
