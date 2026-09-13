# Testing strategy

Unit test membuktikan policy/model murni dan failure behavior tanpa network. Contract
test membuktikan ModelGateway, ToolExecutor, schema, dan compatibility import.
Integration test memakai disposable PostgreSQL/pgvector untuk RBAC, scope, lifecycle,
budget, audit, persistence, dan fresh migration. Regression test ditambahkan saat bug
atau compatibility risk ditemukan.

Default quality gate adalah `pnpm lint`, `pnpm typecheck`, `pnpm test`, dan `pnpm build`.
PostgreSQL suite diaktifkan dengan `ALOS_RUN_POSTGRES_TESTS=1`. Test provider memakai
injected fake/HTTP mock, tidak memerlukan credential nyata dan tidak memanggil network.
