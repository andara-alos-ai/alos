# Tool Registry dan Capability Invocation ALOS

| Metadata | Nilai |
|---|---|
| Status | Diimplementasikan untuk Fondasi Genesis G2 |
| Versi | 1.0.0 |
| Pembaruan terakhir | 30 Agustus 2026 |

## 1. Tujuan

Tool Registry menjadi sumber tunggal operasi yang dapat diminta agent. Capability Invocation mengikat satu langkah workflow kepada agent, capability, mode eksekusi, tool, versi, dan kebutuhan review. Dengan pola ini, service operasional tidak menyimpan aturan khusus per agent.

## 2. Tool Contract

Setiap tool memiliki `contract_version`, `tool_id`, `name`, `purpose`, `kind`, `effect`, `credential_mode`, izin penggunaan pada langkah deterministik, timeout, jumlah percobaan, `version`, dan `status`.

Definisi kanonik berada di `definitions/tools/registry.json`. Registry awal memuat 38 operasi internal, komputasi deterministik, dan AI. Kredensial tidak berada dalam Agent Contract atau workflow; kredensial dikelola platform/integration gateway.

## 3. Capability Invocation

Setiap langkah workflow dengan `actor_type=agent` wajib memiliki invocation yang memuat:

- referensi `agent_id` dan versi opsional;
- `capability` yang ada dalam Agent Contract;
- `execution_mode`: `DETERMINISTIC` atau `AI_ASSISTED`;
- daftar tool yang merupakan subset `tools_allowed`;
- selector eksplisit untuk cabang agent;
- penanda review manusia bila diperlukan.

Workflow Registry menolak agent, capability, atau tool yang tidak terdaftar. Langkah deterministik menolak tool AI. FLOW-004 memakai selector `PERMIT` dan `CONTRACT`, sehingga tidak lagi bergantung pada placeholder identitas agent.

## 4. Eksekusi dan Audit

Shared Agent Runtime menyelesaikan invocation dari definisi workflow, memilih kontrak agent dan tool berversi, lalu membentuk execution plan generik. Plan mencatat digest kontrak, capability, mode, tool release, workflow, langkah, korelasi, dan idempotency key.

Handler didaftarkan berdasarkan capability, bukan `agent_id`. Sebelum dispatch, runtime memeriksa ulang status plan, digest Agent Contract, snapshot, dan versi seluruh tool. Capability baru tidak dapat dijalankan sebelum handler yang sesuai didaftarkan melalui release aplikasi.

Migrasi database menyimpan metadata tersebut pada `agents.agent_runs`. Snapshot Agent Release dan Workflow Release bersifat immutable untuk kombinasi identitas dan versi yang sama. Perubahan konten wajib menggunakan versi baru.

## 5. Batas

- Tool Registry adalah allow-list, bukan penyimpan kredensial.
- Runtime tidak memberikan approval bisnis.
- AI tidak digunakan untuk permission, deadline, transisi status, routing approval, aritmetika, atau audit.
- Tool berstatus selain `STAGED` atau `RELEASED` tidak dapat dipakai pada pilot.
- Integrasi provider nyata tetap harus melalui adaptor, kebijakan data, dan release gate terpisah.
