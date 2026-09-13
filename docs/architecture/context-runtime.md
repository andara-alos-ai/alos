# Context Runtime

Status: **CURRENT BOUNDARY, PARTIAL IMPLEMENTATION**.

`runtime/context` adalah boundary terpisah untuk membangun model input dan menghitung
conservative token bound. Runtime service tetap bertanggung jawab pada orchestration
dan persistence; context logic baru tidak boleh terus ditambahkan ke file service.

Target context dapat memuat Agent Contract, system instruction, active authorized
Skills, scoped Memory, current goal, recent conversation, approved Tools, evidence,
delegated result, classification, dan budget. Retrieval harus scope-aware dan hasilnya
dibatasi sebelum provider call. Compaction, progressive Skill disclosure, Memory
integration, dan full token budgeting belum diklaim selesai pada v1 ini.
