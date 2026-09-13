# ALOS — MVP1 Checklist Traceability

Checklist yang diberikan Direksi tetap menjadi acceptance checklist MVP1.
Tabel ini menerjemahkan butir checklist ke evidence teknis tanpa mengubah
mandat atau batas keamanan.

| Area checklist | Bukti MVP1 yang wajib ada | Status desain |
| --- | --- | --- |
| Requirement natural language | Conversation + Change Request + Research Mission versioned | H5 conversation + Change Request history implemented; Research Mission HOLD |
| Source, dokumen, versi | Source Registry, SHA-256, locator, classification | H5 local text source/version/verification/citation implemented |
| Analysis/gap/conflict/citation | structured Research Brief dengan citation/evidence status | H5 retrieval/citation guardrail; full Genesis analysis HOLD |
| Blueprint dan Agent Contract | JSON Schema, draft/version/digest/parent restriction | H2–H4 implemented; Designer tetap DRAFT |
| Prompt/model/tool/permission/risk/KPI | definitions registry versioned + contract snapshot | H5 Tool/Permission Registry approval API + contract snapshot; Prompt Config Registry HOLD |
| Validate/test/diff | test case/test run registry positive, negative, regression | H5 five-category test gate; contract diff HOLD |
| Human review/approval | independent reviewer, decision digest, audit | H4 local implementation; staging reviewer provisioning HOLD |
| Staging/release/lifecycle | deterministic transition + release proposal + activation | H4 local implementation; VPS staging HOLD |
| Shared runtime | one executor untuk semua logical agent | H3 local DRAFT fixture implementation |
| Suspend/kill/rollback | deny-first check, rollback record, recovery test | H4 local implementation and PostgreSQL test |
| Audit trail | append-only event untuk command/transition/run | H5 writer + authorized read-only API implemented |
| Token/provider/model/latency/cost | usage ledger + persistent cap + provider adapter | H3–H5 Gemini local + ledger/cap/observability API; staging provider HOLD |
| Daily Brief Agent | generated Contract/run, read-only recurring task | `DAILY_BRIEF` DRAFT lokal; H5 shared-runtime validation fixture PASS; schedule HOLD |
| Evidence Checker Agent | generated Contract/run, citation/evidence test | `EVIDENCE_CHECKER` DRAFT lokal; H5 source/citation validation PASS |
| Permit/Overdue Monitor Agent | generated Contract/run, schedule/escalation test | `PERMIT_OVERDUE_MONITOR` DRAFT lokal; H5 shared-runtime validation fixture PASS; schedule HOLD |
| Enam konteks divisi | scoped fixtures, RBAC/UAT matrix | H5 18 synthetic runtime run PASS; human UAT tetap diperlukan |
| Negative/security/recovery tests | denial, malformed output, provider failure, cap, kill, rollback | H5 local automated suite PASS |

## Definisi evidence PASS

Satu butir tidak dianggap PASS hanya karena schema atau UI tersedia. PASS
memerlukan test otomatis atau run record yang dapat diulang, audit/correlation
ID yang dapat diperiksa, dan hasil yang tidak mengandung secret/data nyata.
Butir yang belum terbukti diberi `HOLD`, lengkap dengan owner, risiko,
workaround, dan exit test.
