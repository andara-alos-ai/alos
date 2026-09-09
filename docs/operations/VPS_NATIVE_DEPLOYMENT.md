# ALOS Native VPS Deployment

ALOS berjalan langsung pada VPS Linux melalui systemd. PostgreSQL dan object
storage adalah layanan terkelola/eksternal; tidak ada service Docker yang
diperlukan untuk runtime ini.

## Prasyarat

- User sistem `alos` dan checkout release immutable pada `/opt/alos`.
- Python 3.12, Node.js 22, pnpm, Caddy, dan virtual environment
  `/opt/alos/.venv`.
- PostgreSQL TLS terkelola, bucket S3-compatible, DNS publik, serta port
  80/443 ke Caddy.
- File `/etc/alos/alos.production.env`, owner `root:alos`, mode `0640`.

Environment harus memuat `ALOS_DATABASE_URL`, `ALOS_PUBLIC_HOST`,
`ALOS_AUTH_SIGNING_SECRET`, dan seluruh konfigurasi object storage. Jangan
menulis credential ke repository, systemd unit, atau journal.

## Rilis

```bash
sudo install -d -o alos -g alos /opt/alos/data
cd /opt/alos
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e 'services/platform[dev]'
corepack enable
pnpm install --frozen-lockfile
pnpm --filter @andara/alos-web build
sudo ALOS_PYTHON_BIN=/opt/alos/.venv/bin/python scripts/deployment/preflight-staging.sh /etc/alos/alos.production.env
sudo -u alos bash -c 'set -a; source /etc/alos/alos.production.env; set +a; /opt/alos/.venv/bin/python -m alos.persistence.migrations'
```

Install `infra/systemd/alos-*.service` into `/etc/systemd/system/`, install
`infra/proxy/Caddyfile.vps` as Caddy configuration with the same environment,
then activate:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now alos-platform alos-worker alos-scheduler caddy
sudo systemctl status alos-platform alos-worker alos-scheduler --no-pager
curl --fail https://YOUR_HOST/health/ready
```

## Operasi dan rollback

Periksa `GET /api/v1/system/background-services` memakai role observability.
Untuk rollback, deploy release Git sebelumnya yang telah diuji, jalankan migrasi
append-only (tidak pernah downgrade schema), restart tiga service ALOS, lalu
verifikasi health, heartbeat, dan audit. Restore database mengikuti
[backup/restore](BACKUP_RESTORE.md) dan membutuhkan change approval.
