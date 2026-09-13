# ALOS — Target Repository

## Keputusan struktur

Repository memakai modular monolith. Folder menyatakan boundary kode, bukan
deployment unit. Hanya `platform`, `web`, PostgreSQL, dan proxy yang dapat
menjadi container; tidak ada container per domain atau per agent.

```text
alos/
├─ apps/
│  └─ web/                         # Next.js Mission Control, bukan runtime
├─ services/
│  └─ platform/
│     ├─ src/alos/
│     │  ├─ api/                   # FastAPI routes, request/response schemas
│     │  ├─ application/           # use cases dan transaction boundary
│     │  ├─ domain/
│     │  │  ├─ identity/           # user, role, division, workspace
│     │  │  ├─ sources/            # source, version, citation, evidence
│     │  │  ├─ genesis/            # conversation, mission, finding, artifact
│     │  │  ├─ agents/             # contract, registry, prompt/tool policy
│     │  │  ├─ work/               # work item, schedule, assignment, escalation
│     │  │  ├─ governance/         # review, approval, release, rollback
│     │  │  ├─ runtime/            # shared run, tool decision, executor
│     │  │  └─ observability/      # usage, cost, traces, alerts
│     │  ├─ infrastructure/        # PostgreSQL, object store, OpenAI adapters
│     │  ├─ security/              # authN/authZ and deterministic guardrails
│     │  └─ main.py
│     └─ tests/
│        ├─ unit/
│        ├─ integration/
│        ├─ contract/
│        └─ e2e/
├─ definitions/                    # versioned declarative policy; no secrets
│  ├─ contracts/                   # JSON Schema/fixtures Agent Contract
│  ├─ prompts/                     # prompt templates and versions
│  ├─ tools/                       # reviewed tool manifests
│  ├─ policies/                    # model, risk, permission policy
│  └─ schemas/                     # artifact/output JSON Schemas
├─ data/
│  └─ synthetic/                   # only test fixture; no production data
├─ docs/
│  ├─ product/
│  ├─ architecture/
│  ├─ governance/
│  ├─ implementation/
│  ├─ operations/
│  └─ decisions/
├─ infra/
│  ├─ compose/
│  ├─ database/
│  ├─ docker/
│  ├─ environments/
│  └─ proxy/
├─ scripts/
│  ├─ database/
│  ├─ deployment/
│  └─ quality/
└─ tools/                           # local developer tooling only
```

## File ownership dan aturan

| Lokasi | Isi yang boleh | Tidak boleh |
| --- | --- | --- |
| `apps/web` | Mission Control, approval queue, source/work/agent views | API key, business rule final, direct provider call |
| `services/platform/domain` | entity, invariant, lifecycle, policy interface | FastAPI route, SQL vendor code, SDK provider |
| `services/platform/application` | command/query use case, orchestration | policy bypass, HTTP detail |
| `services/platform/infrastructure` | SQL repositories, object storage, provider adapter | domain decision yang tidak dapat diuji tanpa vendor |
| `definitions` | reviewed/versioned declarative config | secret, executable arbitrary script, unreviewed tool |
| `data/synthetic` | fixture non-sensitif dan expected result | actual customer, employee, finance, credential |
| `infra/database` | append-only migration | dump production, destructive reset script |
| `docs` | decision, protocol, evidence index | source secret atau personal data |

## Berkas inti yang akan dibuat pada tahap implementasi

| Berkas/modul | Tanggung jawab |
| --- | --- |
| `domain/genesis/models.py` | ResearchMission, Finding, Opportunity, Artifact |
| `domain/work/models.py` | WorkItem, recurrence, assignment, SLA/escalation |
| `domain/agents/contract.py` | Agent Contract tervalidasi dan inheritance parent-child |
| `domain/governance/lifecycle.py` | transition deterministic dan approval requirement |
| `domain/runtime/guardrail.py` | kill switch, permission, budget, tool decision sebelum side effect |
| `application/create_research_mission.py` | requirement ke research brief/task plan/agent proposal |
| `application/run_work_item.py` | satu jalan eksekusi shared runtime dengan correlation ID |
| `infrastructure/model_gateway/openai.py` | adapter OpenAI server-side; tidak dipanggil UI |
| `api/routes/*.py` | API untuk Mission, Source, Work, Agent, Review, dan Run |
| `definitions/schemas/*.json` | schema strict untuk artifact dan model output |

## Migrasi dari baseline saat ini

Baseline saat ini (`apps/web`, `services/platform`, `infra`, `data/synthetic`,
dan `docs`) dipertahankan. Refactor fisik dilakukan setelah contract dan test
awal ada. Modul lama `alos.identity`, `alos.audit`, serta
`alos.persistence` dipindahkan bertahap ke boundary target melalui compatibility
import; tidak dihapus dalam satu langkah.

Dokumen lama tidak dihapus sekarang. Setelah dokumen kanonik dipakai dan semua
tautannya diperbarui, berkas yang benar-benar superseded dapat dipindahkan ke
`docs/decisions/archive/` melalui commit terpisah dan reversibel.
