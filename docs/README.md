# Dokumentasi ALOS

Dokumentasi ini membedakan **arah produk ALOS**, **bukti MVP1**, dan catatan
historis. ALOS bukan bernama "MVP"; MVP1 adalah batas pembuktian pertama yang
terukur untuk produk ALOS.

## Urutan baca kanonik

1. [Operating model](product/ALOS_OPERATING_MODEL.md) — tujuan bisnis,
   struktur organisasi, dan batas mandat Genesis.
2. [Target repository](architecture/ALOS_TARGET_REPOSITORY.md) — folder,
   modul, serta kepemilikan file.
3. [Domain dan lifecycle](architecture/ALOS_DOMAIN_AND_LIFECYCLE.md) — entitas
   universal, state machine, dan hubungan antar-domain.
4. Architecture Decision Records — keputusan arsitektur yang diterima dan
   alasan konsekuensinya:
   [ADR-001](architecture/ADR-001-modular-monolith.md),
   [ADR-002](architecture/ADR-002-agent-contract-and-human-lifecycle.md),
   [ADR-003](architecture/ADR-003-deterministic-controls-and-model-gateway.md),
   dan [ADR-004](architecture/ADR-004-local-validation-boundary.md).
5. [Security dan human approval](governance/ALOS_SECURITY_AND_HUMAN_APPROVAL.md)
   — batas deterministik dan keputusan yang selalu dipegang manusia.
6. [Delivery plan](implementation/ALOS_MVP1_DELIVERY_PLAN.md) — lima hari
   pembuktian dan vertical slice pertama.
7. [Checklist traceability](implementation/ALOS_MVP1_CHECKLIST_TRACEABILITY.md)
   — checklist penerimaan MVP1 beserta bukti yang harus dihasilkan.
8. [H5 backend stability report](implementation/H5_BACKEND_STABILITY_REPORT.md)
   — status backend lokal, evidence quality gate, dan limitation yang masih HOLD.
9. [OpenAI staging gateway](implementation/OPENAI_STAGING_GATEWAY.md) —
   konfigurasi provider, routing model, dan urutan validasi VPS staging.
10. [Document Center workflow](product/DOCUMENT_CENTER_WORKFLOW.md) — satu
    repositori dokumen untuk DRAFT Genesis/manual, checklist, dan approval.

## Status dokumen yang sudah ada

- `implementation/DAY_1_FOUNDATION_REPORT.md` adalah evidence foundation yang
  sudah dilakukan; bukan spesifikasi target terbaru.
- `implementation/GENESIS_MVP1_EXECUTION_PLAN.md` tetap referensi H0/Hari 1
  dan quality gate awal. Ia dibaca bersama delivery plan kanonik di atas.
- `architecture/GENESIS_MVP1_ARCHITECTURE.md` dan
  `architecture/GENESIS_MVP1_DOMAIN_MODEL.md` adalah baseline ringkas yang
  dilampaui dokumen domain baru, tanpa menghapus bukti keputusan awal.

Dokumen Dirut, Renstra, SOP, portofolio, KPI, approval, dan evidence adalah
**source business baseline**. Dokumen tersebut tidak dapat mengubah security
boundary ALOS, tidak dapat menjadi approval otomatis, dan tidak mengalahkan
keputusan pengguna/Dirut yang lebih baru.
