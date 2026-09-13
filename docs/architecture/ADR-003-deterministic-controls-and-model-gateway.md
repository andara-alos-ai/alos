# ADR-003: LLM melewati satu Model Gateway; kontrol tetap deterministik

- Status: Accepted
- Tanggal: 2026-09-03

## Context

LLM dapat menghasilkan draft/analisis, tetapi tidak dapat dipercaya untuk
memutuskan permission, approval, arithmetic, status transition, audit, atau
budget.

## Decision

Semua provider LLM melewati satu Model Gateway server-side. Saat ini adapter
yang benar-benar didukung adalah OpenAI dan Gemini. OpenAI adalah satu-satunya
adapter yang tersedia saat LLM diaktifkan pada staging/production; Gemini hanya
local/test. Nilai konfigurasi Anthropic/fallback dan local model belum memiliki
adapter runtime. Secret hanya dibaca dari environment/secret manager backend.

ALOS secara deterministik memvalidasi schema, data classification, token/cost
cap, timeout/retry, tool allowlist, permission, lifecycle, approval, audit,
kill switch, dan rollback sebelum atau sesudah model dipanggil.

## Consequences

- Caller tidak dapat memilih provider/model bebas atau menaruh secret di
  frontend.
- Output LLM selalu kandidat terstruktur dan tidak langsung menjadi aksi.
- Provider baru dapat ditambah tanpa membuat jalur security baru.
