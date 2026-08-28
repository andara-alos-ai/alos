# Runbook Pengembangan Lokal

## Tujuan

Menjalankan fondasi ALOS Internal v1 dengan data sintetis pada workstation pengembang. Prosedur ini tidak mengaktifkan integrasi produksi atau LLM.

## Prasyarat

- Git dan GitHub CLI;
- Node.js 22 atau lebih baru dan pnpm 11;
- Python 3.12;
- Docker Desktop dengan Docker Compose.

## Persiapan

1. Clone repository privat dan masuk ke direktori root.
2. Salin `.env.example` menjadi `.env`; ganti seluruh nilai `change-me` untuk penggunaan lokal.
3. Jalankan `pnpm install`.
4. Buat virtual environment: `python -m venv .venv`.
5. Aktifkan environment dan jalankan `python -m pip install -e "services/platform[dev]"`.

Jangan menyimpan `.env`, kredensial, dokumen perusahaan, atau hasil ekspor ke Git.

## Menjalankan Layanan

```powershell
docker compose -f infra/compose/compose.yaml up -d
pnpm dev:api
pnpm dev:web
```

Periksa API melalui `http://localhost:8000/api/v1/health` dan web melalui `http://localhost:3000`.

## Validasi

```powershell
pnpm validate:definitions
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Registry valid hanya jika tepat 18 Core Agent dan enam workflow dapat dimuat. Workflow harus menolak transisi yang tidak didefinisikan.

## Menghentikan Layanan

```powershell
docker compose -f infra/compose/compose.yaml down
```

Tambahkan `--volumes` hanya jika data lokal memang boleh dihapus. Jangan gunakan opsi tersebut pada lingkungan bersama.

## Kendala Umum

- Jika port 3000, 5432, atau 8000 dipakai aplikasi lain, ubah pemetaan lokal tanpa mengubah port internal service.
- Jika registry gagal, periksa file `definitions/agents/core/*/agent.json` dan jangan mengosongkan bidang wajib.
- Jika aturan perusahaan masih `TBD`, pertahankan tindakan material dalam status `BLOCKED`; jangan mengisi nilai asumsi.
