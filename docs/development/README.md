# Development

## Local setup

Prasyarat: Python 3.12, Node.js 22, pnpm 11, Docker, dan PostgreSQL client yang
kompatibel.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
docker compose -f infra/compose/compose.yaml up -d postgres
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e "services/platform[dev]"
pnpm install --frozen-lockfile
.\.venv\Scripts\python.exe -m alos.persistence.migrations
```

Isi `.env` lokal dengan password/URL yang cocok dengan Compose. Jangan commit
`.env` atau credential.

Jalankan API dan web dari root repository:

```powershell
pnpm dev:api
pnpm dev:web
```

## Quality gate

```powershell
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Backend PostgreSQL integration tests di-skip secara default. Untuk menjalankan
suite penuh terhadap service lokal:

```powershell
$env:ALOS_RUN_POSTGRES_TESTS = "1"
$env:ALOS_DATABASE_URL = "postgresql+psycopg://alos:change-me@127.0.0.1:5433/alos"
python -m pytest services/platform/tests
```

Gunakan database disposable/non-production. Suite integration membuat dan
menghapus database uji turunan.

## Engineering guides

- [Team ownership](team-ownership.md)
- [Architecture change policy](architecture-change-policy.md)
- [Branch strategy](branch-strategy.md)
- [Database migrations](database-migrations.md)

Source of truth command berada di root `package.json`, web
`apps/web/package.json`, platform `services/platform/pyproject.toml`, dan CI
`.github/workflows/quality.yml`. Jika dokumen berbeda, perbaiki dokumen dan
jelaskan apakah command atau policy yang memang berubah.
