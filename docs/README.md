# Dokumentasi ALOS Internal

Dokumentasi ini menjadi dasar implementasi ALOS Internal Agent Pilot v0.1 dan target jangka lanjut ALOS Internal v1. Status seluruh dokumen saat ini adalah rancangan pilot, kecuali keputusan yang secara eksplisit dinyatakan diterima atau terkunci.

## Urutan Baca

1. [Rencana Implementasi](implementation/ALOS_INTERNAL_V1_IMPLEMENTATION_PLAN.md)
2. [Sumber Kebenaran dan Tata Kelola Konfigurasi](architecture/SOURCE_OF_TRUTH_AND_CONFIGURATION.md)
3. [Arsitektur ALOS v1](architecture/ALOS_V1_ARCHITECTURE.md)
4. [Model Domain dan Database](domain-model/ALOS_DOMAIN_AND_DATABASE_MODEL.md)
5. [Spesifikasi Agent Contract](agent-contracts/AGENT_CONTRACT_SPECIFICATION.md)
6. [Registry 18 Core Agent](agent-contracts/18_CORE_AGENT_REGISTRY.md)
7. [Tool Registry dan Capability Invocation](agent-contracts/TOOL_REGISTRY_AND_CAPABILITY_INVOCATION.md)
8. [Interface Design-Time Genesis](architecture/GENESIS_DESIGN_TIME_INTERFACE.md)
9. [Spesifikasi Enam Alur Kerja](workflows/ALOS_V1_WORKFLOW_SPECIFICATION.md)
10. [Dasar Keamanan dan Kebijakan Data AI](security/SECURITY_AND_AI_DATA_POLICY.md)
11. [Strategi Pengujian dan Definisi Selesai](testing/TEST_STRATEGY_AND_DEFINITION_OF_DONE.md)
12. [Register Keputusan Arsitektur](adr/ARCHITECTURE_DECISION_REGISTER.md)
13. [Runbook Pengembangan Lokal](runbooks/LOCAL_DEVELOPMENT.md)
14. [API Foundation Operasional](api/FOUNDATION_API.md)
15. [Worker, Outbox, dan Integrasi n8n](runbooks/WORKER_AND_N8N.md)
16. [Handover Fondasi Genesis](handover/GENESIS_FOUNDATION_HANDOVER.md)

## Aturan Penggunaan

- Struktur organisasi yang terkunci tidak boleh didesain ulang.
- Nilai `TBD` memerlukan validasi pemilik bisnis atau manajemen dan tidak boleh diisi melalui asumsi teknis.
- Dokumentasi menjelaskan keputusan; konfigurasi yang dijalankan nantinya berada di `definitions/` dan harus melalui validasi, pengujian, review, staging, dan rilis.
- Data perusahaan asli tidak disimpan di repository. Pilot menggunakan data sintetis atau data yang telah disanitasi.
- Perubahan material wajib memperbarui dokumen terkait, definisi, pengujian, dan register keputusan bila relevan.

## Dokumentasi Tahap Berikutnya

Runbook pengembangan lokal, API, dan handover Fondasi Genesis telah tersedia sesuai implementasi yang dapat dijalankan. Dokumentasi `deployment` produksi dan `uat` dilengkapi setelah lingkungan serta keputusan bisnis terkait tersedia; bagian tersebut tidak diisi dengan rancangan spekulatif.
