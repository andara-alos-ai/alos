# Reset operational data (staging/pilot)

Use `scripts/database/reset-operational-data.sh` only when an authorized owner
has requested removal of pilot/demo/business records. The script creates a
custom-format PostgreSQL backup before changing data and preserves the account
boundary: organizations, divisions, users, credentials, roles, duties,
workspaces, memberships, schema migrations, and capability catalog.

It removes business records, documents and uploads, GENESIS conversations,
agent contracts and governance records, portfolio/operational/reporting data,
audit and usage history, queue state, integration configuration, and filesystem
objects. It requires the staging filesystem object store; it refuses to run for
an external object store because objects cannot be safely verified and removed
by this local reset path.

Run it from the repository root on the staging VPS:

```bash
sudo bash scripts/database/reset-operational-data.sh --confirm-reset-operational-data
```

The script restarts `platform`, `worker`, and `scheduler` after the reset,
including if a command fails. The backup is retained at `/opt/alos/backups`
with a SHA-256 checksum. Restore it only through the documented isolated
restore-drill process first; never restore it automatically over a live system.
