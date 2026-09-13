# Roles and access

## Actor model

| Actor | Target responsibility | Authority limit |
| --- | --- | --- |
| User ARA | Mengajukan kebutuhan dan memakai capability sesuai scope | Tidak dapat memberi dirinya permission atau melewati lifecycle |
| GENESIS | Analyze, resolve, membuat draft, menjalankan automated evidence | System actor; bukan human approver/releaser |
| Divisi IT | Technical/operator review, configuration, evidence check, submit | Tidak mengambil final Director decision |
| Director | Final approve/reject untuk exact capability version | Approval tidak otomatis release/active |
| Runtime services | Menjalankan version yang sudah active | Tidak membuat authority baru |

Ownership teknis dijelaskan terpisah pada
[team ownership](../development/team-ownership.md). Ownership bukan role RBAC
dan bukan larangan review lintas area.

## CURRENT IMPLEMENTATION

Enum human role aktif memuat `DIRECTOR`, `DIVISION_LEAD`, `DIVISION_MEMBER`,
`IT_ADMIN`, dan `AI_ADMIN`. Authorization platform juga masih membaca role
compatibility `DIVISION_OWNER` dan `IT_LEAD`. Beberapa endpoint Agent/release
lama secara khusus masih memakai `IT_LEAD`; ini gap implementasi yang harus
dimigrasikan secara terkontrol, bukan ditutupi oleh dokumentasi.

Role `BUSINESS_REVIEWER`, `TECHNICAL_REVIEWER`, dan `QA_SECURITY` tetap ada
sebagai **legacy/compatibility roles**. Backend release lama masih memakainya
untuk checker dan dua review gate. Ketiganya bukan akun manusia wajib pada
target governance organisasi.

Duty `maker`, `checker`, `reviewer`, `approver`, `submitter`, dan `operator`
adalah relationship terhadap satu change/version; duty bukan selalu global
role. Segregation of duties harus dihitung dari actor ID dan exact change,
bukan hanya label role.

## Scope model

Access minimum dibatasi oleh:

```text
organization
  → workspace
    → optional division/project
      → optional tenant
        → resource/version/action
```

- Actor hanya dapat membaca/mengubah workspace yang ada pada token scope.
- Division scope mempersempit data kecuali actor memiliki company scope.
- Tenant claim harus cocok dengan Factory, release, schedule, dan Agent Run.
- Scope tidak boleh diperluas oleh prompt, attachment, tool argument, UI state,
  schedule, atau delegation.
- Not-found dapat dipakai untuk resource di luar tenant agar tidak membocorkan
  keberadaan data.

## Permission lifecycle

Permission dan Tool adalah metadata versioned yang harus ditinjau secara
independen. Permission material minimal menyimpan subject/version, capability
atau tool, access mode/effect, scope, lifecycle status, maker, approver,
reason, timestamp, dan audit correlation. ToolExecutor menolak permission yang
tidak `ALLOW` + `APPROVED` atau tidak cocok dengan exact Agent Version.

## Backend versus UI

Menu, disabled button, route guard, dan role label di web bukan security
boundary. Setiap command harus diotorisasi lagi oleh backend dan divalidasi di
repository/service transaction. Tes RBAC wajib membuktikan allow/deny pada API,
bukan hanya snapshot UI.
