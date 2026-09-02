# ALOS — Security Boundary dan Human Approval

## Boundary yang tidak boleh diserahkan kepada LLM

ALOS menghitung dan menegakkan secara deterministik: authentication, RBAC dan
workspace scope, status transition, segregation of duties, deadline/SLA,
arithmetic, budget/cost cap, data classification, tool allowlist, approval,
audit event, kill switch, dan rollback.

LLM hanya menghasilkan kandidat analisis atau structured artifact. Seluruh
keluaran diparsing dengan schema, divalidasi, dan diberi status draft sebelum
dipakai sistem.

## Risk tier dan tindakan

| Risiko | Contoh | Genesis | Human gate |
| --- | --- | --- | --- |
| Low | Ringkasan sumber internal, Daily Brief, test sintetis | dapat menjalankan contract active read-only | review contract pertama kali |
| Medium | Task plan, eksperimen staging, draft website, agent baru | membuat proposal | business dan technical review |
| High | komunikasi calon pelanggan, perubahan integrasi, data personal/finansial | tidak boleh langsung menjalankan | explicit owner + authority approval |
| Critical | payment, kontrak/legal final, HR material, production, delete data, credential/access | hanya dapat mengidentifikasi/escalate | Direksi/authority sesuai policy |

## Approval dan segregation of duties

- Requester/proposer tidak dapat menyetujui request yang sama.
- Genesis tidak pernah menjadi approver manusia.
- Setiap approval menyimpan decision, reason, reviewer, scope/version,
  timestamp, correlation ID, dan evidence link.
- Approval terikat pada digest artifact/contract. Perubahan content, tool,
  permission, risk, atau budget membatalkan approval dan membuat proposal
  baru.
- Aksi eksternal serta side effect tinggi memerlukan approval yang masih valid
  tepat sebelum execution, bukan hanya ketika contract dibuat.

## Data dan provider

- OpenAI adalah provider utama melalui satu Model Gateway server-side.
- Claude adalah fallback yang dipilih policy, bukan route bebas caller.
- Ollama hanya local/test.
- API key hanya environment/secret manager VPS; tidak di repository, frontend,
  log, artifact, audit metadata, atau fixture.
- Staging/production memakai provider response storage `false`; prompt source
  diklasifikasikan sebelum dikirim dan yang melebihi policy ditolak.
- Setiap call mencatat provider, model, token, latency, estimated cost,
  correlation ID, outcome aman, dan redacted error.

## Emergency control

Kill switch bersifat deny-first. Saat aktif, scheduler tidak membuat run baru,
runtime menghentikan langkah berikutnya sebelum tool call, dan Mission Control
menampilkan statusnya. Evidence/audit tidak dihapus. Recovery berarti reviewer
menonaktifkan switch secara eksplisit atau melakukan rollback version yang
tercatat; bukan retry otomatis.
