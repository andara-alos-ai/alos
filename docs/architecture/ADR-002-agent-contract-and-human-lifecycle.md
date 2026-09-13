# ADR-002: Agent Contract dan lifecycle lima-duty

- Status: **Superseded by [ADR-005](ADR-005-genesis-factory-governance.md)**
- Tanggal keputusan awal: 2026-09-03
- Tanggal superseded: 2026-09-13

## Context historis

Keputusan awal menetapkan Agent Contract versioned dan lifecycle:

```text
DRAFT → TESTED → IN_REVIEW → APPROVED → RELEASED → ACTIVE
                                            → SUSPENDED → ROLLED_BACK
```

ADR ini juga mewajibkan maker, checker, business reviewer, technical reviewer,
dan approver sebagai manusia yang terpisah untuk setiap release request.

## Bagian yang tetap berlaku

- Agent Contract dan version bersifat immutable setelah keluar dari draft.
- GENESIS tidak dapat self-approve, self-release, atau self-activate.
- `APPROVED`, `RELEASED`, dan `ACTIVE` adalah state berbeda.
- Lifecycle event, evidence, actor, reason, correlation ID, dan rollback harus
  traceable.
- Maker/self-approval tetap dilarang untuk perubahan material.

## Bagian yang digantikan

Kewajiban lima akun manusia terpisah tidak lagi menjadi governance target.
Target organisasi sekarang adalah automated validation oleh GENESIS, review
teknis/operator oleh Divisi IT, lalu keputusan final Director. Role dan duty
lama tetap terbaca di kode/database sebagai compatibility path sampai migrasi
implementasi dilakukan melalui perubahan terpisah.

Dokumen ini dipertahankan agar history keputusan tidak ditulis ulang diam-diam.
