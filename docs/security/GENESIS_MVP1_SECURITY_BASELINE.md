# Security Baseline — Hari 1

- Semua secret hanya berada pada environment/vault; `.env` di-ignore Git dan
  `.env.example` hanya placeholder.
- Production tidak memiliki route atau credential pada MVP1.
- Genesis bertindak sebagai system actor; tidak dapat self-approve atau
  mengaktifkan perubahan berisiko sendiri.
- User manusia di-scope berdasarkan organisasi, role, division, dan workspace.
- Source default read-only; tool future harus allowlisted dan direview.
- OpenAI adalah provider utama, Claude fallback, dan Ollama hanya local/test.
  Hari 1 menonaktifkan seluruh provider.
- Audit event append-only dan mencatat actor, correlation ID, entity, reason,
  timestamp, dan metadata aman.
- Token/provider/model/latency/cost akan dicatat sebelum LLM diaktifkan.
