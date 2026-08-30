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
8. [Capability Runtime dan LLM Gateway](architecture/CAPABILITY_RUNTIME_AND_LLM_GATEWAY.md)
9. [Pipeline Design-Time Genesis](architecture/GENESIS_DESIGN_TIME_INTERFACE.md)
10. [Spesifikasi Enam Alur Kerja](workflows/ALOS_V1_WORKFLOW_SPECIFICATION.md)
11. [Dasar Keamanan dan Kebijakan Data AI](security/SECURITY_AND_AI_DATA_POLICY.md)
12. [Strategi Pengujian dan Definisi Selesai](testing/TEST_STRATEGY_AND_DEFINITION_OF_DONE.md)
13. [API Genesis dan Agent Runtime](api/GENESIS_AND_AGENT_RUNTIME_API.md)
14. [Register Keputusan Arsitektur](adr/ARCHITECTURE_DECISION_REGISTER.md)
15. [Runbook Pengembangan Lokal](runbooks/LOCAL_DEVELOPMENT.md)
16. [Worker, Outbox, dan Integrasi n8n](runbooks/WORKER_AND_N8N.md)
17. [Runbook Deployment](deployment/DEPLOYMENT_RUNBOOK.md)
18. [UAT Pilot Sintetis](uat/SYNTHETIC_PILOT_UAT.md)
19. [Handover Genesis dan Runtime](handover/GENESIS_FOUNDATION_HANDOVER.md)
20. [Hasil UAT Sintetis 30 Agustus 2026](uat/results/2026-08-30_SYNTHETIC_UAT_REPORT.md)

## Aturan Penggunaan

- Struktur organisasi yang terkunci tidak boleh didesain ulang.
- Nilai `TBD` memerlukan validasi pemilik bisnis atau manajemen dan tidak boleh diisi melalui asumsi teknis.
- Dokumentasi menjelaskan keputusan; konfigurasi yang dijalankan nantinya berada di `definitions/` dan harus melalui validasi, pengujian, review, staging, dan rilis.
- Data perusahaan asli tidak disimpan di repository. Pilot menggunakan data sintetis atau data yang telah disanitasi.
- Perubahan material wajib memperbarui dokumen terkait, definisi, pengujian, dan register keputusan bila relevan.

Runbook deployment dan UAT menjelaskan gate menuju pilot. Nilai vendor, formula bisnis, RTO/RPO, identitas production, serta data asli tetap harus disahkan oleh pemiliknya dan tidak diisi melalui asumsi teknis.
