# ADR-005: Governance Factory memakai IT review dan Director decision

- Status: Accepted (target architecture; implementation gap documented)
- Tanggal: 2026-09-13
- Supersedes: bagian pemisahan lima-duty pada [ADR-002](ADR-002-agent-contract-and-human-lifecycle.md)

## Context

GENESIS berkembang dari Agent generator menjadi Capability/Agent Factory.
Requirement dapat menghasilkan Agent, Skill, Workflow, Rule, Validator,
Report, Human Task, Schedule, Event Handler, connector/tool requirement, atau
composite. Governance harus aman tanpa mewajibkan organisasi memelihara akun
business reviewer, technical reviewer, dan QA/security reviewer terpisah untuk
setiap release.

## Decision

Lifecycle target:

```text
GENESIS automated draft + validation/test/eval/security evidence
→ Divisi IT technical/operator review and configuration
→ Submit exact version to Director
→ Director APPROVE or REJECT
→ separate Release
→ separate Active
```

Divisi IT bertanggung jawab memeriksa dependency, configuration, test/eval,
security evidence, scope, permission, rollback plan, dan operational readiness.
Director mengambil keputusan final atas exact version yang akan dirilis.

GENESIS tidak boleh menjadi approver atau releaser. Backend tetap enforcement
authority. UI tidak dapat memberi authority baru. Maker dari perubahan material
tidak boleh menyetujui perubahan yang sama. Director sebagai requester bisnis
tidak otomatis menjadi maker implementasi; identitas requester, maker/editor,
IT reviewer, submitter, dan decision actor harus disimpan terpisah bila berbeda.

## Compatibility

Backend branch saat ADR ini ditulis masih mengharuskan checker serta gate
`BUSINESS` dan `TECHNICAL`, dengan role compatibility
`BUSINESS_REVIEWER`, `TECHNICAL_REVIEWER`, dan `QA_SECURITY`. Implementasi itu
tidak dihapus atau dianggap sudah bermigrasi oleh perubahan dokumentasi ini.
Sampai backend berubah, API lama tetap menjadi enforcement aktual.

## Consequences

- Factory dan governance harus digeneralisasi dari Agent Version ke versioned
  capability artifact.
- Automated evidence menggantikan duty checker sebagai tahapan sistem, tetapi
  bukan persetujuan manusia.
- IT review dan Director decision harus version-bound dan scope-bound.
- Release serta activation tetap command terpisah dan teraudit.
- Perubahan backend untuk menutup gap memerlukan ADR/architectural review,
  migration append-only, regression/RBAC test, dan rollout compatibility.
