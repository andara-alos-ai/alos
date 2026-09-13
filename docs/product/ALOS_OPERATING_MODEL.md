# ALOS operating model

ALOS — Andara Leverage Operating System — adalah satu enterprise platform,
bukan kumpulan aplikasi per divisi atau per Agent.

## Product surfaces

| Surface | Pengguna | Fungsi |
| --- | --- | --- |
| ARA | User perusahaan | AI workspace untuk percakapan, konteks, pencarian, analisis, draft, dan rekomendasi |
| GENESIS | Tim IT dan governance | AI control plane, Capability/Agent Factory, registry, evidence, lifecycle, release, dan monitoring |
| Operational modules | User sesuai scope | Divisi, proyek, task, approval, dokumen, report, finding, dan dashboard |

ARA adalah pengalaman user; GENESIS adalah control plane. Keduanya berada dalam
ALOS dan memakai identity, data scope, capability registry, backend policy,
audit, serta runtime yang sama. ARA tidak mem-bypass GENESIS/governance dan
GENESIS bukan atasan organisasi atau approver manusia.

## Value flow target

```text
Business requirement melalui ARA atau proses terkontrol
→ GENESIS analyze and resolve capability
→ versioned DRAFT
→ automated evidence
→ IT review and configuration
→ Director decision
→ release and activation
→ bounded execution
→ evidence, KPI, cost, audit, and learning
```

Requirement dapat menghasilkan Agent, Skill, Workflow, Rule, Validator,
Report, Human Task, Schedule, Event Handler, connector/tool requirement, atau
composite. Agent hanya dipakai bila reasoning/autonomy memang diperlukan.

## Product principles

1. **One platform.** Satu backend, satu shared runtime, dan satu PostgreSQL;
   bukan service/database per Agent.
2. **Capability first.** Gunakan rule/validator/skill/workflow sebelum Agent
   bila kebutuhan dapat dipenuhi deterministik.
3. **Evidence before claim.** Output menyatakan sumber, version, classification,
   evidence state, dan limitation yang relevan.
4. **Human authority.** GENESIS membuat draft/evidence; Divisi IT meninjau;
   Director memutuskan release candidate.
5. **Separate lifecycle decisions.** Draft, approval, release, active, suspend,
   resume, dan rollback tidak boleh digabung.
6. **Backend enforcement.** UI membantu user tetapi tidak memberi authority.
7. **Scoped execution.** Organization, workspace, division, project, tenant,
   permission, tool, model, dan budget selalu dibatasi.

## CURRENT IMPLEMENTATION

ARA presentation sudah ada pada Next.js, tetapi sebagian interaction masih
local-state dan integrasi end-to-end ARA belum selesai. GENESIS chat/document,
Factory, Agent Registry, release governance, Agent Runtime, ToolExecutor,
worker/scheduler, evidence, dan audit memiliki backend path masing-masing.
Factory baru melakukan governance handoff end-to-end untuk proposal yang
memuat Agent.

Status target/implemented lebih rinci ada di
[peta dokumentasi](../README.md).
