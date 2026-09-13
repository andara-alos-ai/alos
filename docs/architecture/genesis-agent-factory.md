# GENESIS Capability/Agent Factory

## Tujuan kanonik

Factory menerjemahkan requirement menjadi capability yang paling kecil dan
aman. Ia tidak boleh mengasumsikan bahwa setiap kebutuhan harus menjadi Agent.

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

Jenis resolusi kanonik sama dengan enum `ImplementationType`:

| Type | Makna |
| --- | --- |
| `AGENT` | Reasoning/autonomy terbatas di dalam runtime |
| `SKILL` | Kemampuan reusable tanpa agent baru |
| `WORKFLOW` | Orkestrasi langkah dan gate |
| `RULE` | Keputusan deterministik |
| `VALIDATOR` | Pemeriksaan schema/policy/evidence |
| `REPORT` | Artifact laporan terstruktur |
| `HUMAN_TASK` | Pekerjaan yang memerlukan judgement manusia |
| `SCHEDULE` | Pemicu waktu, bukan authority baru |
| `EVENT_HANDLER` | Pemicu event yang tetap melewati policy |
| `CONNECTOR_REQUIREMENT` | Dependency integrasi yang harus disediakan/dikonfigurasi |
| `TOOL_REQUIREMENT` | Dependency tool typed yang harus diregistrasi dan disetujui |
| `COMPOSITE` | Kombinasi dua atau lebih type di atas |

Resolver memprioritaskan primitive deterministik; komponen Agent hanya dipilih
untuk bagian yang benar-benar membutuhkan reasoning.

## CURRENT IMPLEMENTATION

Factory API menyediakan create, get, list/pagination, dan analyze untuk request
yang authenticated dan scoped. State persistence saat ini:

```text
REQUEST → ANALYZING
        → DRAFT
        → NEEDS_CONFIGURATION
        → NEEDS_IMPLEMENTATION
        → BLOCKED
```

Schema juga menyediakan `TESTING`, `TESTED`, dan `IN_REVIEW`, tetapi service
Factory belum memindahkan request melewati state tersebut. Untuk proposal
`DRAFT` yang memuat Agent, service:

1. membuat Agent Contract/version `DRAFT`;
2. membuat release request terikat exact Agent Version;
3. mendaftarkan kategori test yang dihasilkan;
4. menyimpan linkage Factory → contract → version → release request.

Pada path Factory baru, actor yang menjalankan analysis juga dicatat sebagai
release maker. Handoff duty dari requester ke reviewer/operator IT belum
diimplementasikan. Karena backend melarang maker menjadi approver, kasus
Director yang menjadi analysis actor harus diperlakukan sebagai gap workflow,
bukan alasan untuk melemahkan self-approval protection.

Generated test dimulai sebagai `NOT_RUN`/`EVIDENCE_REQUIRED`. Status itu bukan
evidence PASS. Evidence eval aktual disimpan append-only di
`governance.agent_eval_evidence` setelah execution.

Dependency resolution hanya menerima capability/tool dari authoritative
registry. Capability hilang menjadi `NEEDS_IMPLEMENTATION`; capability belum
terkonfigurasi menjadi `NEEDS_CONFIGURATION`; tool yang belum approved menjadi
blocker. Factory tidak membuat entry catalog palsu dan tidak memberikan
permission secara otomatis.

Resolver aktif saat ini dapat mengeluarkan `AGENT`, `SKILL`, `WORKFLOW`,
`RULE`, `VALIDATOR`, `REPORT`, `HUMAN_TASK`, `SCHEDULE`, `EVENT_HANDLER`, atau
`COMPOSITE`. `CONNECTOR_REQUIREMENT` dan `TOOL_REQUIREMENT` sudah didefinisikan
pada enum, tetapi resolver belum memilih keduanya sebagai implementation type;
dependency tool yang hilang masih direpresentasikan sebagai blocker/dependency.

## TARGET ARCHITECTURE dan gap

| Target | Status branch |
| --- | --- |
| Semua implementation type menghasilkan artifact/version yang governable | Belum; non-Agent berhenti sebagai Factory proposal |
| Connector/tool requirement menjadi hasil resolusi eksplisit | Belum; enum ada, resolver belum mengeluarkan type tersebut |
| Automated test/eval/security evidence terorkestrasi dari Factory | Sebagian; proposal dan evidence store ada, lifecycle Factory belum lengkap |
| Divisi IT review dan submit | Belum; release backend masih workflow compatibility lima-duty |
| Requester/analysis actor diserahkan ke IT maker/reviewer terpisah | Belum; analysis actor menjadi release maker |
| Director approve/reject | Ada untuk release Agent, tetapi masih mensyaratkan dua review gate legacy |
| Release terpisah dari approval | Ada untuk Agent |
| Active terpisah dari release | Ada untuk Agent |
| Monitor/suspend/rollback | Ada untuk Agent; explicit resume belum ada |

## Invariant

- `CREATE` hanya mencatat requirement; bukan approval.
- `DRAFT` dapat diedit/versioned; bukan release candidate yang approved.
- Hasil analysis, test proposal, atau model output bukan evidence sampai
  validator/evaluator benar-benar dijalankan.
- GENESIS tidak boleh menjadi actor manusia, approver, releaser, atau grantor.
- Tool/connector yang hilang menghasilkan dependency requirement, bukan bypass.
- Review, decision, release, activation, suspend, rollback, dan evidence harus
  terikat exact version, tenant/workspace scope, actor, reason, correlation ID,
  dan waktu.
- UI tidak boleh mengubah lifecycle tanpa command backend yang valid.

Governance target dijelaskan pada
[governance model](../governance/governance-model.md); lifecycle version pada
[agent lifecycle](../governance/agent-lifecycle.md).
