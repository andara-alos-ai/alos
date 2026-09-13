# Contributing to ALOS

Gunakan focused, short-lived branch dari source of truth yang berlaku. Selama transisi
Repository Architecture v1, branch kerja adalah `epic/genesis-agent-factory`; setelah
PR ini diterima, `main` menjadi basis kanonik. Buat PR kecil, koheren, dan mudah diulas.

## Aturan perubahan

- Pertahankan modular monolith; jangan membuat service baru tanpa kebutuhan terukur dan ADR.
- Jangan bypass backend authority, `ModelGateway`, `ToolExecutor`, RBAC, atau scope policy.
- Migration yang telah diterapkan immutable dan append-only; tambahkan migration bernomor baru.
- Perbarui dokumentasi dan test ketika contract atau behavior berubah.
- Perubahan boundary/arsitektur besar memerlukan ADR dan review lintas domain.
- Jangan commit secret, `.env`, production data, atau dokumen rahasia.
- Pertahankan compatibility behavior; deprecation harus eksplisit dan diuji.

## Quality gate

Jalankan dari root repository:

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Untuk area persistence, jalankan juga backend suite dengan disposable PostgreSQL,
`ALOS_RUN_POSTGRES_TESTS=1`, dan verifikasi fresh migration. PR harus menjelaskan test
yang tidak dapat dijalankan beserta alasannya.
