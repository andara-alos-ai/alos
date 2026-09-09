# ADR-002: Semua agent menggunakan Agent Contract dan lifecycle manusia

- Status: Accepted
- Tanggal: 2026-09-03

## Context

Genesis harus dapat membuat agent baru tanpa taxonomy tetap, tetapi tidak boleh
auto-approve, auto-active untuk risiko, atau melewati audit dan rollback.

## Decision

Setiap logical agent memiliki Agent Contract versioned yang memuat purpose,
schema, model policy, tool/permission, risk, owner, KPI, evidence, forbidden
actions, dan timeout. Lifecycle minimum adalah:

```text
DRAFT → TESTED → IN_REVIEW → APPROVED → RELEASED → ACTIVE
                                            → SUSPENDED → ROLLED_BACK
```

Maker, checker, business reviewer, technical reviewer, dan approver harus
terpisah untuk satu release request. `ACTIVE` hanya menunjuk version Registry;
ia tidak memberi tool, permission, atau authority baru.

## Consequences

- Genesis dapat membuat draft tetapi tidak dapat menyetujui atau mengaktifkan
  dirinya sendiri.
- Setiap activation dan rollback dapat direplay dari audit/lifecycle event.
- Perubahan contract menghasilkan version baru dan memerlukan lifecycle baru.
