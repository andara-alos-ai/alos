# Governance model

## TARGET ARCHITECTURE

```text
GENESIS
  create DRAFT + automated validation/test/eval/security evidence
    → Divisi IT
      technical/operator review, configure if needed, inspect evidence
        → submit exact version to Director
          → Director APPROVE or REJECT
            → authorized Release
              → authorized Active
                → monitor / suspend / resume or rollback
```

Target ini hanya memerlukan dua human authorities:

1. Divisi IT sebagai reviewer/operator dan submitter;
2. Director sebagai final decision authority.

`CREATE`/`DRAFT != APPROVE != RELEASE != ACTIVE`. Automated PASS bukan approval.
Approval bukan release. Release bukan activation. GENESIS tidak dapat
self-approve, self-release, atau memberi permission kepada hasil buatannya.

## CURRENT IMPLEMENTATION

Release lifecycle Agent di backend saat ini:

```text
DRAFT
→ five categories PASS + successful test Agent Run
→ TESTED → IN_REVIEW
→ BUSINESS and TECHNICAL review APPROVED
→ Director APPROVED
→ Director RELEASED
→ Director ACTIVE
→ SUSPENDED → ROLLED_BACK
```

Test wajib saat ini adalah `POSITIVE`, `NEGATIVE`, `REGRESSION`, `SECURITY`, dan
`RECOVERY`; setiap latest run harus PASS dan memiliki eval evidence. Permission
dan tool memiliki lifecycle approval terpisah. Semua review terikat release
request yang menunjuk satu Agent Version.

Jalur ini adalah compatibility implementation, bukan target organisasi baru.
Dokumentasi tidak menghapus enforcement tersebut. UI juga masih menampilkan
gate legacy sesuai API.

Factory path baru saat ini mencatat analysis actor sebagai release maker.
Target handoff requester → IT reviewer/submitter belum ada; jangan memberi
maker hak approve untuk mengatasi gap tersebut.

## Enforcement boundaries

| Boundary | Authority |
| --- | --- |
| Authentication dan scope | Backend token claims + repository/service checks |
| RBAC | Backend authorization; UI visibility bukan izin |
| Capability/tool availability | Capability Registry + approved Tool Registry |
| Permission | Version-bound policy `ALLOW` + `APPROVED` |
| Model route/provider | Server-side ModelGateway configuration |
| Test/eval evidence | Actual run + append-only eval evidence |
| Lifecycle | Backend transition rules + PostgreSQL constraints |
| Release/active pointer | Release repository + Agent Registry |
| Suspend/kill/rollback | Backend commands + audit/lifecycle records |

## Maker/self-approval

Maker adalah actor yang menghasilkan atau mengubah material version/config,
bukan selalu requester bisnis. Maker tidak boleh menyetujui perubahan material
yang sama. GENESIS selalu system actor dan tidak pernah memenuhi human gate.
Pemecahan pekerjaan di dalam satu tim tidak boleh mengaburkan actor aktual;
requester, editor, reviewer, submitter, decision actor, dan operator dicatat
secara eksplisit.

## Acceptance behavior dari baseline sebelumnya

Setiap migrasi menuju target IT → Director wajib mempertahankan:

- maker/self-approval denial untuk perubahan material;
- organization, workspace, division, project, dan tenant scoping;
- permission lifecycle beserta maker/approver/version/metadata;
- review, return, dan reject yang terikat exact version;
- exact `active_version_id` dan valid rollback target;
- suspend yang menghentikan run baru serta resume yang eksplisit dan tervalidasi;
- immutable/append-only audit dan evidence yang dapat direplay;
- regression, negative, recovery, security, tenant-isolation, dan RBAC tests.

Tidak diperlukan giant governance UI atau login banyak akun untuk membuktikan
behavior tersebut. Bukti utama harus berada pada API/service/database tests;
UI hanya perlu menyajikan state dan command secara jujur.
