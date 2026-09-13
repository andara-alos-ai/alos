# Staging Compose and OpenAI runbook

Status: CURRENT IMPLEMENTATION runbook. Keberhasilan langkah ini menghasilkan
evidence staging, bukan otomatis production readiness atau approval capability.

## Topology

`infra/compose/compose.staging.yaml` menjalankan PostgreSQL, migration one-shot,
platform API, worker, scheduler, web, dan Caddy. Hanya Caddy mem-publish port
80/443. Object storage default adalah S3-compatible; fallback filesystem hanya
boleh dipakai di staging bila flag explicit diaktifkan.

Jangan mencampur runbook ini dengan
[native production deployment](VPS_NATIVE_DEPLOYMENT.md). Path, service manager,
database, dan rollback keduanya berbeda.

## Prerequisites

- VPS Linux dengan Docker Engine dan Docker Compose plugin.
- DNS untuk staging host dan port 80/443 menuju Caddy.
- SSH dibatasi ke administrator; PostgreSQL tidak dipublish ke host.
- Reviewed immutable commit/tag dari branch aktif, bukan moving branch sebagai
  bukti release.
- `/etc/alos/alos.staging.env` di luar repository, permission `0600` atau lebih
  ketat.
- OpenAI project/service credential khusus environment staging bila provider
  akan diaktifkan.

## Secret and policy configuration

Salin `infra/environments/staging/alos.staging.env.example` ke lokasi di luar
repository, lalu ganti seluruh placeholder langsung pada VPS. Jangan mengirim
secret melalui chat, issue, Git, atau command argument.

Konfigurasi provider yang didukung untuk staging:

```dotenv
ALOS_LLM_PROVIDER=openai
ALOS_LLM_API_KEY=SET_ON_VPS_ONLY
ALOS_LLM_MODEL=gpt-5.6-luna
ALOS_LLM_MODEL_LIGHT=gpt-5.6-luna
ALOS_LLM_MODEL_STANDARD=gpt-5.6-terra
ALOS_LLM_MODEL_CRITICAL=gpt-5.6-sol
ALOS_LLM_STORE_RESPONSES=false
ALOS_LLM_REASONING_EFFORT=medium
ALOS_LLM_MAX_OUTPUT_TOKENS=1200
ALOS_LLM_MAX_CONTEXT_TOKENS=12000
ALOS_LLM_DAILY_REQUEST_LIMIT=2
ALOS_LLM_DAILY_OUTPUT_TOKEN_LIMIT=2400
ALOS_LLM_DAILY_COST_CAP_USD=5.00
```

OpenAI adalah adapter staging yang tersedia. Gemini ditolak pada staging dan
hanya boleh dipakai di `local`/`test`. Tidak ada adapter runtime Anthropic atau
local model; jangan mengonfigurasi nilai tersebut sebagai fallback aktif.

Raw model name hanya berada pada environment backend. Agent Contract memilih
route `light`, `standard`, atau `critical`. `store=false` adalah provider
request setting, bukan pengganti review klasifikasi, retensi, dan data
governance.

## Feature flags

Model-backed document analysis dan conversation follow-up mati secara default:

```dotenv
ALOS_GENESIS_SEMANTIC_ANALYSIS_ENABLED=false
ALOS_GENESIS_CONVERSATION_FOLLOW_UP_ENABLED=false
```

Aktifkan satu per satu hanya setelah cost limit workspace, source
classification, permission, audit, dan rollback/disable plan diverifikasi.
Scope awal tetap dokumen `INTERNAL` non-sensitif yang approved. Jangan gunakan
data `CONFIDENTIAL`/`RESTRICTED` tanpa policy dan evidence baru.

## Deploy

Dari checkout exact reviewed commit/tag:

```bash
bash scripts/deployment/preflight-staging.sh /etc/alos/alos.staging.env
sudo docker compose \
  --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml \
  up --build --detach
sudo docker compose \
  --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml \
  ps
```

Migration service harus selesai sebelum platform start. Jangan mengedit
migration lama untuk memperbaiki deployment; buat migration append-only baru.

## Verify

```bash
curl --fail --show-error https://YOUR_STAGING_HOST/health
curl --fail --show-error https://YOUR_STAGING_HOST/health/ready
sudo docker compose \
  --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml \
  logs --tail=100 migrate platform worker scheduler proxy
```

Kemudian jalankan urutan evidence:

1. bootstrap actor staging sesuai
   [governance dashboard runbook](STAGING_GOVERNANCE_DASHBOARD.md);
2. jalankan satu public/synthetic no-tool gateway smoke;
3. verifikasi provider/model route, usage, correlation ID, dan redacted failure;
4. jalankan regression/RBAC, scope, permission/tool denial, budget, malformed
   output, provider failure, kill/suspend, dan rollback tests;
5. simpan exact commit, environment, time, actor, command, dan result;
6. submit hanya exact version dengan evidence lengkap ke governance.

Health check saja tidak membuktikan Factory, governance, provider, atau UAT.

## Rollback

Untuk menghentikan model traffic, set `ALOS_LLM_PROVIDER=disabled` dan redeploy.
Untuk rollback aplikasi, deploy exact prior known-good commit/tag dengan Compose
file dan secret environment yang sama. Jangan menghapus volume PostgreSQL,
Caddy, atau object storage. Schema tidak di-downgrade; corrective schema change
harus berupa migration append-only.

Capability rollback dilakukan melalui Agent Registry/release governance, bukan
dengan rollback Git. Pastikan active-version dan rollback-target correctness
serta audit record setelah setiap recovery.
