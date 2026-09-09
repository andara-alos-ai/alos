# ADR-001: ALOS menggunakan modular monolith dan satu PostgreSQL

- Status: Accepted
- Tanggal: 2026-09-03

## Context

ALOS perlu memungkinkan Genesis membuat logical agent secara generik, tanpa
mengubah setiap agent menjadi aplikasi, database, atau microservice tersendiri.
MVP1 harus dapat dibangun serta divalidasi dalam satu minggu.

## Decision

ALOS menggunakan satu aplikasi internal modular-monolith, satu shared Agent
Runtime, satu Model Gateway, dan satu PostgreSQL. Domain dipisahkan secara
modul dan schema database (`identity`, `workspace`, `agents`, `governance`,
`runtime`, `observability`, `audit`, `genesis`), bukan deployment terpisah.

Agent core, sub-agent, dan sub-sub-agent adalah record Agent Contract dalam
Agent Registry yang sama, dengan hubungan parent dan version history.

## Consequences

- Deploy, audit, migration, backup, dan security boundary lebih sederhana.
- Satu bug aplikasi dapat berdampak lintas modul; karena itu lint, type check,
  migration test, integration test, dan rollback version wajib dijalankan.
- Pemisahan service hanya dipertimbangkan setelah ada bukti kebutuhan scale,
  isolation, atau ownership yang tidak dapat dipenuhi modular-monolith.
