# Versioned definitions

Folder ini menyimpan contract deklaratif dan berversi yang dapat divalidasi tanpa
menjalankan implementation. Definition bukan secret, runtime state, atau bukti bahwa
suatu capability sudah ACTIVE.

Struktur bertumbuh berdasarkan kebutuhan nyata: `contracts/` saat ini memuat schema
Agent Contract. Definition capability, tool, dan eval ditambahkan ketika memiliki
consumer, owner, lifecycle, serta test; repository tidak membuat folder/dummy definition.

Agent Contract memilih logical model route dan tidak membawa credential. Semua Agent
dibuat sebagai logical/versioned artifact melalui governed Factory/Registry, bukan
sebagai source-code package per Agent.
