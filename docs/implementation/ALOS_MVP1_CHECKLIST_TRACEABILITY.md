# ALOS — MVP1 Checklist Traceability

Checklist yang diberikan Direksi tetap menjadi acceptance checklist MVP1.
Tabel ini menerjemahkan butir checklist ke evidence teknis tanpa mengubah
mandat atau batas keamanan.

| Area checklist | Bukti MVP1 yang wajib ada | Status desain |
| --- | --- | --- |
| Requirement natural language | Conversation + Change Request + Research Mission versioned | dirancang |
| Source, dokumen, versi | Source Registry, SHA-256, locator, classification | baseline ada; implementasi API diperlukan |
| Analysis/gap/conflict/citation | structured Research Brief dengan citation/evidence status | dirancang |
| Blueprint dan Agent Contract | JSON Schema, draft/version/digest/parent restriction | baseline sebagian; implementasi diperlukan |
| Prompt/model/tool/permission/risk/KPI | definitions registry versioned + contract snapshot | dirancang |
| Validate/test/diff | validation report, test run, contract diff | dirancang |
| Human review/approval | independent reviewer, decision digest, audit | table baseline ada; workflow diperlukan |
| Staging/release/lifecycle | deterministic transition + release proposal + activation | schema baseline ada; enforcement diperlukan |
| Shared runtime | one executor untuk semua logical agent | schema baseline ada; executor diperlukan |
| Suspend/kill/rollback | deny-first check, rollback record, recovery test | schema baseline ada; enforcement diperlukan |
| Audit trail | append-only event untuk command/transition/run | table/trigger ada; writer/query diperlukan |
| Token/provider/model/latency/cost | usage ledger + persistent cap + provider adapter | schema/test guard ada; integration diperlukan |
| Daily Brief Agent | generated Contract/run, read-only recurring task | belum dibuat |
| Evidence Checker Agent | generated Contract/run, citation/evidence test | belum dibuat |
| Permit/Overdue Monitor Agent | generated Contract/run, schedule/escalation test | belum dibuat |
| Enam konteks divisi | scoped fixtures, RBAC/UAT matrix | six division seed ada; UAT diperlukan |
| Negative/security/recovery tests | denial, malformed output, provider failure, cap, kill, rollback | sebagian test gateway; suite diperlukan |

## Definisi evidence PASS

Satu butir tidak dianggap PASS hanya karena schema atau UI tersedia. PASS
memerlukan test otomatis atau run record yang dapat diulang, audit/correlation
ID yang dapat diperiksa, dan hasil yang tidak mengandung secret/data nyata.
Butir yang belum terbukti diberi `HOLD`, lengkap dengan owner, risiko,
workaround, dan exit test.
