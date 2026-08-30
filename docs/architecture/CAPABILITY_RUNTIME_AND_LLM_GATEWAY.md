# Capability Runtime dan LLM Gateway

| Metadata | Nilai |
|---|---|
| Status | Diimplementasikan untuk Synthetic UAT |
| Versi | 1.0.0 |

## Capability Contract

`definitions/capabilities/registry.json` adalah sumber tunggal untuk seluruh capability Core, Sub-Agent, dan Sub-Sub-Agent. Setiap kontrak menetapkan mode eksekusi, handler, schema input/output, evidence, human review, timeout, retry, versi, dan status rilis.

Agent Registry menolak capability yang tidak terdaftar. Workflow Registry menolak perbedaan mode eksekusi dan penggunaan tool AI pada langkah deterministik. Shared runtime memverifikasi digest Agent Contract, versi/digest Capability Contract, handler yang ditetapkan, kebijakan evidence, serta release tool sebelum dispatch.

## Output Eksekusi

Setiap run menyimpan agent, versi, capability beserta versi/digest kontraknya, workflow step, Agent Contract digest, handler, release tool, status, output terstruktur, evidence, warning, verification status, correlation ID, dan idempotency key. Untuk AI, metadata juga memuat provider, model, prompt version/digest, token, latency, dan field yang disamarkan.

Database tetap menegakkan permission, status transition, approval routing, waktu, aritmetika, dan audit. Handler AI tidak dapat menggantikan keputusan tersebut.

## LLM Gateway

Gateway mendukung mode `disabled`, OpenAI Responses API, dan Anthropic Messages API melalui boundary yang sama. Prompt disimpan berversi pada `definitions/prompts/registry.json`.

Kontrol awal:

- default provider `disabled`;
- structured output wajib dan divalidasi ulang;
- request provider bersifat stateless dan respons OpenAI memakai `store=false`;
- safety identifier di-hash;
- email dan nomor telepon disamarkan;
- data di atas klasifikasi yang diizinkan diblokir sebelum network call;
- budget request/token, timeout, retry terbatas, metadata penggunaan, dan fail-closed;
- seluruh output AI berstatus provisional/unverified dan wajib human review.

Model dan provider tidak ditetapkan dalam repository. Aktivasi membutuhkan credential dari secret manager, model yang disetujui, kebijakan data, dan UAT.
