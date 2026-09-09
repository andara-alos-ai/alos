# ADR-004: Local validation terpisah dari staging dan production

- Status: Accepted
- Tanggal: 2026-09-03

## Context

MVP1 perlu membuktikan lifecycle dan Runtime sebelum VPS, identity provider,
OpenAI staging, dan data perusahaan tersedia.

## Decision

Environment `local`/`test` memakai PostgreSQL Docker dan dapat memakai Gemini
untuk test read-only. Bootstrap token serta review team lokal hanya tersedia di
environment ini. Local Runtime memprioritaskan draft untuk release testing dan
menjalankan version active bila tidak ada draft tertunda.

Staging/production menolak bootstrap token lokal dan Gemini. Aktivasi scheduler,
identity reviewer riil, OpenAI, secret manager, backup, HTTPS, dan monitoring
harus tersedia sebelum agent active dipakai di sana.

## Consequences

- Bukti lokal tidak disalahartikan sebagai approval atau readiness production.
- Tidak ada data perusahaan/credential yang dikirim selama validation lokal.
- Jalur production perlu runbook dan quality gate tambahan sebelum deployment.
