# ALOS Staging and OpenAI Runbook

Status: preparation only. This runbook does not authorize production release.

## Scope

Staging menjalankan satu ALOS modular monolith: web, platform API, satu
PostgreSQL, filesystem source storage, dan reverse proxy HTTPS. PostgreSQL tidak
memiliki host port. Staging hanya menggunakan fixture `data/synthetic/` sampai
review data governance dan security memperluas scope secara eksplisit.

## Required before deployment

- VPS Linux dengan Docker Engine dan Docker Compose plugin.
- DNS `A`/`AAAA` untuk domain staging menuju VPS, serta port 80/443 terbuka
  untuk provisioning TLS Caddy.
- Port SSH dibatasi ke IP administrator. Port database tidak dibuka.
- Akses Git repository pada branch `develop`.
- OpenAI Project khusus ALOS dan service-account API key khusus aplikasi.
- Spend limit dan alert diatur di OpenAI Project sebelum key dipakai.

Jika domain publik atau DNS belum tersedia, jangan membuka service dengan HTTP
publik. Gunakan akses internal/VPN terlebih dahulu dan tunda proxy TLS sampai
domain tersedia.

## Secret file on the VPS

Salin template ke lokasi di luar repository dan set permission ketat:

```bash
sudo install -d -m 700 /etc/alos
sudo install -o root -g root -m 600 /dev/null /etc/alos/alos.staging.env
sudoedit /etc/alos/alos.staging.env
```

Isi nilai dari `infra/environments/staging/alos.staging.env.example` secara
manual pada VPS. Generate `ALOS_POSTGRES_PASSWORD` dan
`ALOS_AUTH_SIGNING_SECRET` dengan `openssl rand -hex 24` dan
`openssl rand -hex 32`. Masukkan `ALOS_LLM_API_KEY` langsung pada VPS; jangan
mengirimnya melalui chat, issue, terminal history, atau Git.

Set policy awal berikut pada file secret:

```dotenv
ALOS_LLM_PROVIDER=openai
ALOS_LLM_MODEL=gpt-5.6-luna
ALOS_LLM_MODEL_LIGHT=gpt-5.6-luna
ALOS_LLM_MODEL_STANDARD=gpt-5.6-terra
ALOS_LLM_MODEL_CRITICAL=gpt-5.6-sol
ALOS_LLM_STORE_RESPONSES=false
ALOS_LLM_REASONING_EFFORT=low
ALOS_LLM_MAX_OUTPUT_TOKENS=1200
ALOS_LLM_MAX_CONTEXT_TOKENS=12000
ALOS_LLM_DAILY_REQUEST_LIMIT=2
ALOS_LLM_DAILY_OUTPUT_TOKEN_LIMIT=2400
ALOS_LLM_DAILY_COST_CAP_USD=5.00
ALOS_GENESIS_SEMANTIC_ANALYSIS_ENABLED=false
ALOS_GENESIS_SEMANTIC_MAX_OUTPUT_TOKENS=1200
ALOS_GENESIS_CONVERSATION_FOLLOW_UP_ENABLED=false
ALOS_GENESIS_FOLLOW_UP_MAX_OUTPUT_TOKENS=1200
ALOS_SOURCE_CHUNK_MAX_CHARS=1500
ALOS_SOURCE_RETRIEVAL_MAX_CHARS=10000
```

`ALOS_LLM_MAX_CONTEXT_TOKENS` memblokir Agent Run sebelum request provider
jika gabungan instruksi, input, dan evidence diperkirakan melampaui batas.
Sumber versi baru dipecah maksimal `ALOS_SOURCE_CHUNK_MAX_CHARS`, sedangkan
retrieval membatasi total cuplikan menggunakan
`ALOS_SOURCE_RETRIEVAL_MAX_CHARS`. Versi sumber lama tidak diubah; daftarkan
konten sebagai versi baru jika perlu di-chunk ulang, sementara batas retrieval
tetap melindungi versi lama.

`store=false` menghindari penyimpanan response state yang dikontrol aplikasi
provider, tetapi bukan pengganti review data governance. OpenAI menjelaskan
bahwa Responses API dan abuse-monitoring memiliki kontrol retensi tersendiri;
gunakan data sintetis sampai organisasi menyetujui klasifikasi dan retensi data.

## Genesis semantic document analysis (opt-in)

Fitur ini **mati secara default**, termasuk ketika Model Gateway OpenAI sudah
tersedia. Aktivasi hanya dilakukan setelah Direktur menyetujui uji satu dokumen
INTERNAL dan IT memastikan `governance.cost_limits` untuk workspace tersebut
aktif. Ubah hanya pada secret file VPS:

```dotenv
ALOS_GENESIS_SEMANTIC_ANALYSIS_ENABLED=true
ALOS_GENESIS_SEMANTIC_MAX_OUTPUT_TOKENS=1200
```

Percakapan dua arah dikendalikan secara terpisah. Aktifkan hanya setelah
analisis dokumen dan cost limit workspace telah diverifikasi:

```dotenv
ALOS_GENESIS_CONVERSATION_FOLLOW_UP_ENABLED=true
ALOS_GENESIS_FOLLOW_UP_MAX_OUTPUT_TOKENS=1200
```

Follow-up hanya dapat berjalan selama workflow masih `ANALYSIS_DRAFT`. Ia
memakai sumber, versi, dan SHA-256 analisis awal; menyertakan maksimal delapan
turn sukses terbaru atau sekitar 4.000 token riwayat; dan tidak memajukan
workflow maupun mengubah dokumen.

Satu permintaan hanya dapat memakai dokumen `MANUAL`, berklasifikasi
`INTERNAL`, berstatus `APPROVED` atau `ACTIVE`, dengan ekstrak teks maksimal
60.000 karakter. ALOS mengirim teks ekstrak itu langsung ke satu request
Responses melalui Model Gateway—bukan file, vector store, tool, browser, atau
research eksternal. Jawaban serta metadata token/biaya disimpan di ALOS sebagai
artifact dan dokumen `DRAFT`; dokumen sumber tidak pernah ditulis ulang.

`store=false` mencegah application state response pada Responses API. Itu tidak
sendiri berarti pemrosesan ber-retensi nol: kebijakan data OpenAI tetap dapat
memiliki abuse-monitoring logs hingga 30 hari pada konfigurasi standar. Baca
[OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data)
sebelum mengganti scope data atau mengaktifkan fitur ini untuk dokumen bisnis.

Urutan uji yang diperbolehkan: gunakan satu dokumen INTERNAL non-sensitif yang
sudah approved, kirim satu pertanyaan, periksa jawaban dan sitasi di DRAFT,
lalu nonaktifkan flag jika ada ketidaksesuaian. Jangan gunakan dokumen
`CONFIDENTIAL` atau `RESTRICTED` pada MVP ini.

`light`, `standard`, dan `critical` adalah route Contract, bukan nama model
yang dapat ditentukan agent. Backend memetakan route tersebut ke Luna, Terra,
dan Sol melalui environment VPS di atas.

## Deploy staging

Jalankan dari root checkout branch `develop` pada VPS:

```bash
bash scripts/deployment/preflight-staging.sh /etc/alos/alos.staging.env
sudo docker compose \
  --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml \
  up --build --detach
sudo docker compose \
  --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml ps
```

Compose menjalankan migration sebagai service one-shot sebelum platform API
diizinkan start. Caddy hanya menerima 80/443; platform dan PostgreSQL tidak
dipublish sebagai host port.

## Immediate verification

```bash
curl --fail --show-error https://YOUR_STAGING_HOST/health
curl --fail --show-error https://YOUR_STAGING_HOST/health/ready
sudo docker compose \
  --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml logs --tail=100 migrate platform proxy
```

Endpoint health membuktikan deploy dasar saja. Model Gateway belum boleh
memanggil OpenAI hingga implementation Hari 2 memvalidasi structured output,
audit event, token cap, provider failure, dan source citation.

## OpenAI boundary

ALOS akan memakai endpoint Responses dari backend saja. Respons harus meminta
JSON Schema untuk artifact Blueprint/Agent Contract, dengan `tools=[]`,
`store=false`, request timeout, output-token cap, dan correlation ID. Simpan
usage, model, latency, provider request ID, error code, serta artifact hash di
audit/observability ALOS; jangan simpan API key atau source mentah di log.

Referensi: [Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)
dan [OpenAI data controls](https://developers.openai.com/api/docs/guides/your-data).

## Rollback

Untuk rollback aplikasi, checkout commit `develop` sebelumnya yang telah lulus
quality gate, lalu jalankan kembali perintah Compose yang sama. Jangan menghapus
volume `alos-postgres` atau `/etc/alos/alos.staging.env` ketika rollback. Semua
rollback schema setelah Hari 2 harus memakai migration baru yang append-only,
bukan mengubah migration yang telah diterapkan.
