# Dokumentasi ALOS Internal

Dokumentasi ini menjadi dasar implementasi ALOS Internal Agent Pilot v0.1 dan target jangka lanjut ALOS Internal v1. Status seluruh dokumen saat ini adalah rancangan pilot, kecuali keputusan yang secara eksplisit dinyatakan diterima atau terkunci.

## Urutan Baca

1. [Rencana Implementasi](implementation/ALOS_INTERNAL_V1_IMPLEMENTATION_PLAN.md)
2. [Sumber Kebenaran dan Tata Kelola Konfigurasi](architecture/SOURCE_OF_TRUTH_AND_CONFIGURATION.md)
3. [Arsitektur ALOS v1](architecture/ALOS_V1_ARCHITECTURE.md)
4. [Model Domain dan Database](domain-model/ALOS_DOMAIN_AND_DATABASE_MODEL.md)
5. [Spesifikasi Agent Contract](agent-contracts/AGENT_CONTRACT_SPECIFICATION.md)
6. [Registry 18 Core Agent](agent-contracts/18_CORE_AGENT_REGISTRY.md)
7. [Spesifikasi Enam Alur Kerja](workflows/ALOS_V1_WORKFLOW_SPECIFICATION.md)
8. [Dasar Keamanan dan Kebijakan Data AI](security/SECURITY_AND_AI_DATA_POLICY.md)
9. [Strategi Pengujian dan Definisi Selesai](testing/TEST_STRATEGY_AND_DEFINITION_OF_DONE.md)
10. [Register Keputusan Arsitektur](adr/ARCHITECTURE_DECISION_REGISTER.md)

## Aturan Penggunaan

- Struktur organisasi yang terkunci tidak boleh didesain ulang.
- Nilai `TBD` memerlukan validasi pemilik bisnis atau manajemen dan tidak boleh diisi melalui asumsi teknis.
- Dokumentasi menjelaskan keputusan; konfigurasi yang dijalankan nantinya berada di `definitions/` dan harus melalui validasi, pengujian, review, staging, dan rilis.
- Data perusahaan asli tidak disimpan di repository. Pilot menggunakan data sintetis atau data yang telah disanitasi.
- Perubahan material wajib memperbarui dokumen terkait, definisi, pengujian, dan register keputusan bila relevan.

## Dokumentasi yang Ditunda

Folder `api`, `deployment`, `runbooks`, `handover`, dan `uat` tetap kosong sampai implementasi menghasilkan fakta yang dapat didokumentasikan. Bagian tersebut tidak diisi dengan rancangan spekulatif.
