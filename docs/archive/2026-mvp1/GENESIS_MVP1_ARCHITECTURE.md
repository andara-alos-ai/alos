# Arsitektur Genesis MVP1

```text
Direktur Utama
  └─ Genesis — AI Executive Operating Layer
       ├─ Genesis control plane
       │   source → analyze → blueprint/contract → validate → test → diff
       │   → human review → staging/release
       └─ Shared Agent Runtime
            └─ logical agents scoped to FINANCE, SALES_MARKETING, PROPERTY,
               HR, LEGAL, and IT
```

ALOS menggunakan modular monolith: Next.js web shell, FastAPI platform,
PostgreSQL tunggal, dan definitions versioned. Genesis adalah system actor
pada audit; human actor tetap diperlukan untuk review, approval, dan activation.

Logical agent dapat memiliki parent contract, tetapi hierarchy tidak boleh
mengubah struktur organisasi atau membentuk circular dependency. Child agent
tetap berada dalam registry, permission guardrail, audit, and runtime yang sama.

## Batas execution

Runtime hanya menjalankan version contract yang released dan explicitly active.
Ia memeriksa lifecycle, workspace/division scope, input/output schema, policy,
tool allowlist, evidence, cost limit, dan kill switch sebelum side effect.
MVP1 tidak memiliki tool write production.
