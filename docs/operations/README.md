# Operations

Runbook aktif:

- [Native production VPS deployment](VPS_NATIVE_DEPLOYMENT.md)
- [Staging OpenAI/Compose runbook](STAGING_OPENAI_RUNBOOK.md)
- [OpenAI gateway validation](../implementation/OPENAI_STAGING_GATEWAY.md)
- [Staging governance dashboard](STAGING_GOVERNANCE_DASHBOARD.md)
- [Backup and restore](BACKUP_RESTORE.md)
- [Reset operational data](reset-operational-data.md)

Pilih satu deployment mode per environment. Jangan menggabungkan volume/path
Compose dengan path/systemd native. Keberadaan manifest, runbook, atau health
endpoint bukan bukti readiness; simpan evidence yang terikat exact commit,
environment, timestamp, actor, dan result.
