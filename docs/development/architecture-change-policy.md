# Architecture change policy

Perubahan berikut wajib melalui architectural review dan ADR sebelum dianggap
kanonik:

- RBAC dan segregation of duties;
- organization/workspace/division/project/tenant data scope;
- Agent lifecycle;
- Factory lifecycle atau implementation type;
- `ModelGateway` dan provider routing;
- `ToolExecutor`, tool contract, atau connector execution;
- permission model;
- approval/release/activation policy;
- tenant isolation;
- kill, cancellation, suspend, resume, atau rollback semantics.

## ADR requirements

ADR minimal memuat context, decision, status, consequences, migration/compatibility
plan, security impact, data impact, operational impact, tests/evidence, dan
rollback. ADR harus menyebut apakah ia mendeskripsikan current implementation
atau target architecture.

Jika keputusan menggantikan ADR lama:

1. jangan menghapus atau menulis ulang alasan lama;
2. ubah status ADR lama menjadi `Superseded` dan tautkan penggantinya;
3. ADR baru harus menyebut bagian yang tetap berlaku dan bagian yang berubah;
4. implementasi dilakukan melalui migration/change append-only bila data atau
   lifecycle persistence berubah.

[ADR-002](../architecture/ADR-002-agent-contract-and-human-lifecycle.md) dan
[ADR-005](../architecture/ADR-005-genesis-factory-governance.md) adalah contoh
supersession yang eksplisit.

## Review evidence

Architectural review belum selesai hanya dengan persetujuan dokumen. Pull
request implementasi harus membawa test untuk invariant terkait, termasuk
negative/RBAC/regression/recovery/tenant-isolation bila relevan, serta perubahan
runbook dan observability. Migration `001`–`036` tetap immutable.
