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
6. [OpenAI staging gateway](implementation/OPENAI_STAGING_GATEWAY.md) —
   konfigurasi provider, routing model, dan urutan validasi VPS staging.
7. [Document Center workflow](product/DOCUMENT_CENTER_WORKFLOW.md) — satu
    repositori dokumen untuk DRAFT Genesis/manual, checklist, dan approval.

## Index

- Architecture: [README](architecture/README.md)
- Governance: [README](governance/README.md)
- Security: [README](security/README.md)
- Development: [README](development/README.md)
- Operations: [README](operations/README.md)
- Archive: [2026-mvp1](archive/2026-mvp1/README.md)

## Status dokumen yang sudah ada

- Laporan delivery dan readiness historis dipindahkan ke
  [archive/2026-mvp1](archive/2026-mvp1/README.md).
- `architecture/GENESIS_MVP1_ARCHITECTURE.md` dan
  `architecture/GENESIS_MVP1_DOMAIN_MODEL.md` adalah baseline ringkas yang
  dilampaui dokumen domain baru, tanpa menghapus bukti keputusan awal.

Dokumen Dirut, Renstra, SOP, portofolio, KPI, approval, dan evidence adalah
**source business baseline**. Dokumen tersebut tidak dapat mengubah security
boundary ALOS, tidak dapat menjadi approval otomatis, dan tidak mengalahkan
keputusan pengguna/Dirut yang lebih baru.
