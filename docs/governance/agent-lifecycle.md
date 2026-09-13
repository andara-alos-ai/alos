# Agent and capability lifecycle

## Lifecycle target

```text
Requirement
→ ANALYZED / RESOLVED
→ DRAFT
→ VALIDATED / TESTED
→ IT_REVIEW
→ SUBMITTED_TO_DIRECTOR
→ APPROVED or REJECTED
→ RELEASED
→ ACTIVE
→ SUSPENDED
→ RESUMED or ROLLED_BACK
```

Nama state target dapat dipetakan ke state database secara bertahap, tetapi
semantiknya tidak boleh digabungkan. Semua implementation type Factory harus
akhirnya memakai lifecycle versioned yang setara.

## CURRENT IMPLEMENTATION untuk Agent

Backend release memakai:

```text
DRAFT → TESTED → IN_REVIEW
      → RETURNED / REJECTED
      → APPROVED → RELEASED → ACTIVE → SUSPENDED → ROLLED_BACK
```

Factory request memiliki lifecycle lebih pendek (`REQUEST`, `ANALYZING`, lalu
`DRAFT`/dependency status/blocker). Factory tidak memajukan state approval atau
release; linkage Agent diserahkan ke release governance.

## Version-bound rules

- Setiap release request menunjuk exact immutable Agent Version.
- Edit material harus menghasilkan draft/version baru; approval lama tidak
  berpindah ke version baru.
- Review, returned/rejected decision, test/eval, permission, dan release harus
  menunjuk version yang sama.
- `active_version_id` adalah pointer authority untuk `LIVE`; status teks pada
  version lain tidak cukup.
- Aktivasi harus menolak tool/dependency yang belum available/configured,
  permission yang belum approved, dan kill switch aktif.

## Suspend, resume, kill, dan rollback

CURRENT IMPLEMENTATION:

- suspend dari `ACTIVE` atau `RELEASED` mengosongkan active pointer;
- kill switch juga mengosongkan active pointer dan menahan run baru;
- clear kill switch hanya membuka blocker, tidak mengaktifkan Agent;
- rollback dari `ACTIVE`/`SUSPENDED` memilih version berbeda dari contract yang
  sama dengan status pernah `ACTIVE`, `SUSPENDED`, atau `RELEASED`;
- rollback ditolak selama kill switch belum di-clear;
- tidak ada endpoint/state `RESUME` eksplisit.

TARGET ARCHITECTURE:

- resume harus command eksplisit, bukan efek samping clear kill switch;
- resume harus mengikat exact version dan memeriksa ulang scope, permission,
  tool/dependency, budget, evidence freshness, serta kill switch;
- jika ada perubahan material selama suspension, buat version baru dan ulangi
  review/Director decision; jangan resume version lama secara diam-diam;
- emergency suspend dapat dilakukan authority operasi sesuai policy, tetapi
  recovery harus memiliki actor, reason, evidence, dan audit.

## Release and rollback correctness

Release hanya boleh memakai version yang telah disetujui. Activation hanya
boleh menunjuk released version tersebut. Rollback target harus version yang
pernah released, bukan latest draft atau version dari Agent lain. Setelah
rollback, registry active/released pointer, lifecycle event, rollback record,
dan audit event harus menunjuk target yang sama.

## Evidence minimum

Sebelum submit ke Director, evidence minimum mencakup positive, negative,
regression, security, recovery, permission/tool denial bila relevan, tenant
isolation bila relevan, budget, source validation, dan actual run linkage.
Evidence proposal atau test definition tanpa execution tidak dihitung PASS.
