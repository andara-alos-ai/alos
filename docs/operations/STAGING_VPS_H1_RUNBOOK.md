# Runbook H1 — Aktivasi Staging VPS (Biznet GIO 8 GB) + OpenAI Low-Cap

**Tujuan checklist H1:** App aktif di VPS staging (bukan laptop), PostgreSQL +
health + auth/RBAC jalan di server, dan Model Gateway menyambung ke provider
nyata (OpenAI) dengan **cap rendah** sebagai pagar biaya.

> Batasan H1 tetap: **staging-only**, belum ada data nyata, belum ada aksi yang
> mengubah uang/record. OpenAI dipakai dengan cap harian kecil dan
> `ALOS_LLM_MAX_DATA_CLASSIFICATION=INTERNAL`.

---

## 0. Prasyarat (yang harus sudah ada)

- VPS Linux (Ubuntu 24.04 LTS disarankan), **8 GB RAM**, akses SSH + user sudo.
- Domain/subdomain yang diarahkan (A record) ke IP VPS, mis. `alos-staging.<domain>`.
- Akun OpenAI + **API key** (dibuat di platform OpenAI), dengan **usage limit /
  billing cap rendah** di sisi OpenAI juga (jangan andalkan cap aplikasi saja).
- Repo `andara-alos-ai/alos`, branch `develop-hasyim`, ter-clone di VPS.
- Docker Engine + Docker Compose plugin terpasang di VPS.

Catatan keamanan: **tempel API key langsung di VPS** (`/etc/alos/alos.staging.env`,
permission `600`). Jangan kirim key lewat chat, email, atau commit ke git.

---

## 1. Pasang Docker di VPS (sekali saja)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
  sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | \
  sudo tee /etc/apt/sources.list.d/docker.list >/dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER   # lalu logout/login ulang
docker --version && docker compose version
```

---

## 2. Ambil kode dan siapkan environment

```bash
git clone https://github.com/andara-alos-ai/alos.git /opt/alos
cd /opt/alos
git checkout develop-hasyim
git pull

sudo mkdir -p /etc/alos
sudo cp infra/environments/staging/alos.staging.env.example /etc/alos/alos.staging.env
sudo chmod 600 /etc/alos/alos.staging.env
```

Edit `/etc/alos/alos.staging.env` dan isi **semua** placeholder:

```bash
sudo nano /etc/alos/alos.staging.env
```

Nilai minimal yang wajib diganti:

| Variabel | Cara mengisi |
| --- | --- |
| `ALOS_PUBLIC_HOST` | subdomain VPS, mis. `alos-staging.example.com` |
| `ALOS_TLS_EMAIL` | email untuk notifikasi Let's Encrypt (Caddy auto-TLS) |
| `ALOS_POSTGRES_PASSWORD` | `openssl rand -hex 24` |
| `ALOS_AUTH_SIGNING_SECRET` | `openssl rand -hex 32` (wajib ≥32 char di staging) |
| `ALOS_LLM_PROVIDER` | `openai` |
| `ALOS_LLM_API_KEY` | **tempel langsung di VPS**, jangan dari chat/git |
| `ALOS_LLM_MODEL` | model OpenAI yang dipilih, mis. `gpt-5.6-terra` |
| `ALOS_LLM_BASE_URL` | kosongkan untuk endpoint resmi OpenAI |
| `ALOS_LLM_DAILY_REQUEST_LIMIT` | `50` (cap rendah H1) |
| `ALOS_LLM_DAILY_OUTPUT_TOKEN_LIMIT` | `100000` (cap rendah H1) |
| `ALOS_LLM_MAX_DATA_CLASSIFICATION` | `INTERNAL` |
| `ALOS_LLM_STORE_RESPONSES` | `false` (wajib di staging) |

> ⚠️ **Catatan kode (H1):** adapter OpenAI **belum ada** di repo saat ini.
> Mengisi `ALOS_LLM_PROVIDER=openai` saja belum memanggil OpenAI — lihat
> bagian 6. Tanpa adapter, jalankan dulu dengan `ALOS_LLM_PROVIDER=disabled`
> untuk memvalidasi deploy, lalu sambungkan OpenAI setelah adapter dibuat.

---

## 3. Preflight (gagal lebih awal sebelum menyentuh internet)

```bash
cd /opt/alos
bash scripts/deployment/preflight-staging.sh /etc/alos/alos.staging.env
# Harus mencetak: "Preflight staging PASS."
```

Script ini menolak deploy jika masih ada placeholder (`REPLACE_WITH`,
`SET_ON_VPS_ONLY`, `example.com`).

---

## 4. Build, migrasi, dan jalankan stack

```bash
cd /opt/alos
docker compose --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml build

docker compose --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml up -d
```

Urutan otomatis oleh compose: `postgres` (healthcheck) → `migrate`
(menjalankan `001` + `002` lalu exit 0) → `platform` (healthcheck
`/health/ready`) → `web` → `proxy` (Caddy, sertifikat TLS otomatis).

Cek status dan log:

```bash
docker compose -f infra/compose/compose.staging.yaml ps
docker compose -f infra/compose/compose.staging.yaml logs -f platform
```

---

## 5. Verifikasi H1 di server (bukti PASS)

Jalankan **dari VPS** dan **dari browser eksternal**:

```bash
# Liveness/readiness di dalam jaringan
curl -fsS http://127.0.0.1:8000/health        && echo
curl -fsS http://127.0.0.1:8000/health/ready  && echo
```

Dari luar, buka:

- `https://ALOS_PUBLIC_HOST/health/ready` → `200` (membuktikan TLS + proxy + app).
- `https://ALOS_PUBLIC_HOST/` → shell web Next.js termuat.

Uji auth + GENESIS end-to-end di staging (token local/test hanya untuk smoke;
di staging sebaiknya lewat identitas resmi — lihat catatan di bawah):

```bash
TOK=$(curl -fsS -X POST https://ALOS_PUBLIC_HOST/api/v1/auth/local-token \
  -H 'content-type: application/json' \
  -d '{"user_id":"11111111-1111-1111-1111-111111111111",
       "organization_id":"22222222-2222-2222-2222-222222222222",
       "roles":["IT_LEAD"],"division_codes":["IT"],"workspace_ids":[]}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

curl -fsS https://ALOS_PUBLIC_HOST/api/v1/genesis/agents \
  -H "Authorization: Bearer $TOK"
```

Simpan output perintah di atas sebagai **bukti PASS H1** (termasuk waktu &
Decision ID aktivasi VPS). Tidak boleh ada secret dalam bukti.

---

## 6. Menyambungkan OpenAI (poin penting H1)

Ada dua lapis yang harus benar:

1. **Konfigurasi (sudah siap di repo).** `config.py` sudah:
   - mengizinkan `ALOS_LLM_PROVIDER=openai`,
   - mewajibkan `ALOS_LLM_API_KEY` + `ALOS_LLM_MODEL` bila provider aktif,
   - menjadikan OpenAI satu-satunya primary provider di produksi,
   - memblokir `store_responses` di staging/produksi,
   - menerapkan cap harian (`ALOS_LLM_DAILY_REQUEST_LIMIT`,
     `ALOS_LLM_DAILY_OUTPUT_TOKEN_LIMIT`) dan batas klasifikasi data.

2. **Adapter runtime (BELUM ada — perlu ditulis).** Saat ini baru ada
   `GeminiModelGateway` (local/test) dan `FakeModelGateway`. Untuk OpenAI
   dibutuhkan `OpenAIModelGateway` yang mengimplementasikan `ModelGateway`
   (`generate(ModelRequest) -> ModelResponse`), memanggil API Chat Completions
   via `httpx`, lalu dibungkus `GuardedModelGateway` dan di-wire ke runtime
   GENESIS. Detail daftar kebutuhan ada di ringkasan chat; ini pekerjaan
   kode terpisah (sejalan dengan pengingat adapter Postgres).

**Urutan aman H1:** deploy dulu dengan `ALOS_LLM_PROVIDER=disabled` untuk
membuktikan infra/health/migrasi/TLS, lalu aktifkan OpenAI setelah adapter +
factory ada dan lulus uji cap (lihat bagian 7).

---

## 7. Uji pagar biaya (low-cap) — wajib sebelum dianggap PASS

Setelah OpenAI tersambung, buktikan cap bekerja dan dapat diulang:

- [ ] Permintaan normal di bawah cap → sukses, `usage` tercatat.
- [ ] Tembus `ALOS_LLM_DAILY_REQUEST_LIMIT` → error budget `REQUEST_LIMIT`,
      tidak ada panggilan provider lanjutan.
- [ ] Tembus token limit → `OUTPUT_TOKEN_LIMIT`.
- [ ] Klasifikasi data `CONFIDENTIAL/RESTRICTED` ditolak (`DATA_CLASSIFICATION`).
- [ ] Timeout provider → `TIMEOUT` yang aman (tidak membocorkan key).
- [ ] Billing cap di dashboard OpenAI juga diset rendah (pertahanan berlapis).

---

## 8. Backup/restore drill (menutup UAT-14, quality gate Hari 5)

Catatan: script backup yang ada di repo adalah PowerShell
(`scripts/database/*.ps1`, untuk Windows). Di VPS Linux gunakan `pg_dump`/
`pg_restore` dalam container:

```bash
# Backup
docker compose -f infra/compose/compose.staging.yaml exec -T postgres \
  pg_dump -U alos -d alos -Fc > /var/backups/alos-$(date +%F).dump

# Restore drill (ke database scratch untuk diuji, bukan menimpa yang aktif)
docker compose -f infra/compose/compose.staging.yaml exec -T postgres \
  pg_restore -U alos -d postgres --create < /var/backups/alos-YYYY-MM-DD.dump
```

Lakukan restore ke instance scratch dan verifikasi jumlah baris tabel kunci
(agents, governance, runtime, audit) sebelum menandai UAT-14 PASS.

---

## 9. Rollback / stop

```bash
cd /opt/alos
docker compose --env-file /etc/alos/alos.staging.env \
  -f infra/compose/compose.staging.yaml down      # data tetap di volume
# Menghapus data volume (HATI-HATI, hanya untuk reset penuh):
# docker compose ... down -v
```

---

## 10. Checklist bukti H1 (untuk diisi)

- [ ] VPS aktif, Docker terpasang, domain + TLS (Caddy) hijau.
- [ ] `/health/ready` `200` dari internet.
- [ ] Migrasi `001`+`002` sukses (log service `migrate` exit 0).
- [ ] Auth + RBAC + endpoint GENESIS merespons benar di server.
- [ ] `.env` berisi secret asli hanya di VPS (`600`), tidak ter-commit.
- [ ] OpenAI: adapter tersambung + uji low-cap lolos (atau provider `disabled`
      dengan catatan adapter menyusul).
- [ ] Billing cap OpenAI diset rendah di sisi OpenAI.
- [ ] Decision ID aktivasi VPS tercatat; bukti tanpa secret.
