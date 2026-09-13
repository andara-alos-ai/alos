# Data policy

Folder `data/` hanya untuk data sintetis, fixture yang telah disanitasi, import
development/test, template non-sensitif, dan artefak test. File runtime pada inbox,
processed, rejected, exports, dan object storage lokal diabaikan Git kecuali `.gitkeep`.

Dilarang menyimpan dump database produksi, API key, access token, password, private key,
credential, data pelanggan pribadi, data keuangan/HR/legal rahasia, atau dokumen internal
yang tidak diizinkan. Gunakan generator fixture atau data anonim yang tidak dapat
direkonstruksi menjadi data asli.
