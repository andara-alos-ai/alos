# Native production VPS deployment

Status: CURRENT IMPLEMENTATION runbook untuk topology native production.

ALOS berjalan langsung melalui systemd. PostgreSQL dan S3-compatible object
storage adalah layanan eksternal; Caddy adalah reverse proxy host. Topology ini
tidak memakai Compose service untuk runtime.

## Prerequisites

- User sistem `alos` dan exact immutable release checkout di `/opt/alos`.
- Python 3.12, Node.js 22, pnpm, Caddy, dan `/opt/alos/.venv`.
- PostgreSQL TLS eksternal, bucket S3-compatible, DNS, dan port 80/443.
- `/etc/alos/alos.production.env`, owner `root:alos`, mode `0640`.
- Backup/restore drill serta rollback commit telah diverifikasi sebelum change.

Gunakan `infra/environments/production/alos.production.env.example` sebagai
daftar variable. Credential tidak boleh ditulis ke repository, unit systemd,
shell history, atau journal.

## Build and migrate

```bash
sudo install -d -o alos -g alos /opt/alos/data
cd /opt/alos
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e 'services/platform[dev]'
corepack enable
pnpm install --frozen-lockfile
pnpm --filter @andara/alos-web build
sudo env ALOS_DEPLOYMENT_MODE=native \
  ALOS_PYTHON_BIN=/opt/alos/.venv/bin/python \
  scripts/deployment/preflight-staging.sh /etc/alos/alos.production.env
sudo -u alos bash -c 'set -a; source /etc/alos/alos.production.env; set +a; /opt/alos/.venv/bin/python -m alos.persistence.migrations'
```

`ALOS_DEPLOYMENT_MODE=native` harus diberikan ke process preflight; nilai di
environment file baru dibaca setelah pemilihan mode oleh script saat ini.

## Activate services

Install `infra/systemd/alos-platform.service`, `alos-worker.service`, dan
`alos-scheduler.service` ke `/etc/systemd/system/`. Install
`infra/proxy/Caddyfile.vps` sebagai Caddy configuration.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now alos-platform alos-worker alos-scheduler caddy
sudo systemctl status alos-platform alos-worker alos-scheduler --no-pager
curl --fail https://YOUR_HOST/health/ready
```

Verifikasi juga `GET /api/v1/system/background-services`, audit, queue,
scheduler heartbeat, object storage, dan satu synthetic scoped flow. Health
endpoint saja bukan production readiness.

## Rollback

Deploy exact prior known-good application release, jalankan migration runner
tanpa schema downgrade, restart platform/worker/scheduler, lalu verifikasi
health, heartbeat, active-version pointers, audit, dan queued work. Jangan
restore database hanya untuk rollback aplikasi.

Database restore adalah change-controlled incident action dan mengikuti
[backup/restore](BACKUP_RESTORE.md). Hentikan writer sebelum restore, verifikasi
checksum/compatibility, dan simpan actor, reason, time, serta evidence.
