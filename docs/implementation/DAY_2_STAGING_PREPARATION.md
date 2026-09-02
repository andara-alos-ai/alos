# Hari 2 — Staging Preparation

## Objective

Menjalankan satu alur ALOS secara vertikal pada staging:

```text
requirement → registered synthetic source/version → Genesis analysis
→ Blueprint → Agent Contract DRAFT → citation → human review queue
```

ALOS adalah produk. Genesis adalah AI Executive Operating Layer di dalam ALOS.
`MVP1` hanya merupakan milestone pengiriman dan bukan nama aplikasi atau service.

## Prepared inputs

`data/synthetic/requirements/` memuat requirement untuk Daily Brief, Evidence
Checker, dan Permit/Overdue Monitor. `data/synthetic/documents/` memuat source
yang harus diregistrasikan oleh Source Registry besok.

| Scenario | Source pair | Expected result |
| --- | --- | --- |
| Daily Brief | daily division CSV v1 + Sales update v2 | Conflict pipeline Sales Rp1.8B vs Rp1.55B terlihat dengan citation versi. |
| Evidence Checker | revenue claim + Finance report v1/v2 | Claim bernilai `PARTIALLY_SUPPORTED`; seluruh invoice tidak terbukti. |
| Permit Monitor | permit register + policy + legal memo | PRM-001 `DUE_SOON` dengan memo belum approved; PRM-002 `OVERDUE` dan `BLOCKED`. |

## OpenAI staging policy

- Hanya backend Model Gateway yang memanggil OpenAI Responses API.
- Default model policy: `gpt-5.6-terra`, reasoning `medium`, maksimal 3.000
  output token per request, 50 request dan 100.000 output token per hari.
- `store=false`; conversation/artifact history tetap dimiliki ALOS di PostgreSQL.
- Tidak ada web search, file search, MCP, Computer Use, function tool, atau
  provider fallback pada alur pertama.
- Pydantic/JSON Schema, permission, lifecycle, approval, deadline, arithmetic,
  cost cap, dan audit tetap divalidasi deterministik oleh ALOS.
- Tidak ada dokumen perusahaan, personal data, credential, atau data
  `CONFIDENTIAL`/`RESTRICTED` yang dikirim pada Hari 2.

Responses API mendukung instruction, input, output JSON terstruktur, metadata,
token cap, dan pemilihan tool. Konfigurasi ini sengaja tidak melampirkan tool
apa pun sampai Tool Registry dan permission guardrail selesai diimplementasikan.

## Definition of ready for tomorrow

1. `develop` memiliki Compose staging, image definition, HTTPS proxy, dan
   preflight script.
2. Secret staging berada di VPS di luar repository dan seluruh placeholder
   telah diganti secara lokal pada VPS.
3. PostgreSQL tidak memiliki host port dan hanya dapat diakses network Compose.
4. Health endpoint lulus setelah migration one-shot berhasil.
5. Source fixture dapat diregistrasikan tanpa menyentuh data perusahaan.
6. Provider tidak dipanggil sebelum implementasi Model Gateway memiliki schema
   validation, audit event, request cap, dan error handling.

## Deferred to implementation tomorrow

- Endpoint upload/registration source, hashing, chunking, dan citation anchor.
- Genesis conversation/artifact persistence dan requirement API.
- Model Gateway OpenAI nyata, structured output parser, usage ledger, dan
  provider failure handling.
- Blueprint/Contract generation dan human review queue.

Tidak ada agent yang dapat aktif, menjalankan tool, atau mengubah resource pada
persiapan ini.
