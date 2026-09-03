# ALOS — MVP1 Checklist Traceability

Checklist yang diberikan Direksi tetap menjadi acceptance checklist MVP1.
Tabel ini menerjemahkan butir checklist ke evidence teknis tanpa mengubah
mandat atau batas keamanan.

| Area checklist | Bukti MVP1 yang wajib ada | Status desain |
| --- | --- | --- |
| Requirement natural language | Conversation + Change Request + Research Mission versioned | dirancang |
| Source, dokumen, versi | Source Registry, SHA-256, locator, classification | baseline ada; implementasi API diperlukan |
| Analysis/gap/conflict/citation | structured Research Brief dengan citation/evidence status | dirancang |
| Blueprint dan Agent Contract | JSON Schema, draft/version/digest/parent restriction | H2–H4 implemented; Designer tetap DRAFT |
| Prompt/model/tool/permission/risk/KPI | definitions registry versioned + contract snapshot | dirancang |
| Validate/test/diff | test case/test run registry positive, negative, regression | H4 local implementation; contract diff HOLD |
| Human review/approval | independent reviewer, decision digest, audit | H4 local implementation; staging reviewer provisioning HOLD |
| Staging/release/lifecycle | deterministic transition + release proposal + activation | H4 local implementation; VPS staging HOLD |
| Shared runtime | one executor untuk semua logical agent | H3 local DRAFT fixture implementation |
| Suspend/kill/rollback | deny-first check, rollback record, recovery test | H4 local implementation and PostgreSQL test |
| Audit trail | append-only event untuk command/transition/run | H1–H4 writers implemented |
| Token/provider/model/latency/cost | usage ledger + persistent cap + provider adapter | H3 Gemini local implementation; staging provider HOLD |
| Daily Brief Agent | generated Contract/run, read-only recurring task | Contract `DAILY_BRIEF` 0.1.0 DRAFT dibuat lokal; run/schedule HOLD |
| Evidence Checker Agent | generated Contract/run, citation/evidence test | Contract `EVIDENCE_CHECKER` 0.1.0 DRAFT dibuat lokal; run/evidence fixture HOLD |
| Permit/Overdue Monitor Agent | generated Contract/run, schedule/escalation test | Contract `PERMIT_OVERDUE_MONITOR` 0.1.0 DRAFT dibuat lokal; run/schedule HOLD |
| Enam konteks divisi | scoped fixtures, RBAC/UAT matrix | six division seed ada; UAT diperlukan |
| Negative/security/recovery tests | denial, malformed output, provider failure, cap, kill, rollback | sebagian test gateway; suite diperlukan |

## Definisi evidence PASS

Satu butir tidak dianggap PASS hanya karena schema atau UI tersedia. PASS
memerlukan test otomatis atau run record yang dapat diulang, audit/correlation
ID yang dapat diperiksa, dan hasil yang tidak mengandung secret/data nyata.
Butir yang belum terbukti diberi `HOLD`, lengkap dengan owner, risiko,
workaround, dan exit test.
