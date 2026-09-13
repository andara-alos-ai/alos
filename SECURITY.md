# Security Policy

Laporkan kerentanan secara privat kepada maintainer keamanan PT Andara Rejo Makmur.
Jangan membuka public issue yang memuat detail eksploit, data sensitif, atau langkah
reproduksi yang dapat disalahgunakan. Sertakan versi/commit, dampak, dan reproduksi
minimum pada kanal privat yang disepakati organisasi.

Jangan pernah commit API key, access token, password, private key, file `.env`, dump
database produksi, data pelanggan/pribadi, atau dokumen perusahaan rahasia. Cabut dan
rotasi secret segera bila terpapar; menghapusnya dari commit terbaru saja tidak cukup.

## Security boundary

- Backend adalah enforcement authority; UI bukan security boundary.
- LLM bukan permission engine dan tidak memiliki otoritas bisnis final.
- Semua model eksternal wajib melalui `ModelGateway`.
- Semua tool dan connector wajib melalui `ToolExecutor`.
- Secret hanya berada server-side dan tidak boleh masuk prompt, browser bundle, atau log.
- Identity, RBAC, tenant, workspace, division, project, klasifikasi data, serta scope
  divalidasi backend sebelum akses atau eksekusi.
- Delegation hanya boleh mempersempit authority, permission, tool, scope, dan budget.
- Perubahan material harus melalui review manusia dan lifecycle yang dapat diaudit.

Panduan lebih rinci ada di [security model](docs/security/security-model.md).
