# ALOS — Operating Model

## Mandat produk

ALOS — **Andara Leaverage Operating Sistem** — adalah satu operating system
internal perusahaan properti. ALOS menyediakan konteks data, aturan,
orchestration, shared runtime, audit, dan Mission Control. Ia bukan kumpulan
aplikasi per divisi atau per agent.

Genesis adalah **AI Executive Operating Layer** sekaligus mesin Research &
Development ALOS. Genesis menerima arah bisnis dari Direksi, mengubahnya
menjadi research mission, work plan, proposal artifact, atau proposal agent.
Genesis tidak memiliki kewenangan final.

```text
Direktur Utama
  └─ ALOS / Genesis — AI Executive Operating Layer dan R&D
       ├─ Research & opportunity engine
       ├─ Work orchestration
       ├─ Agent factory dan shared runtime
       └─ Evidence, audit, observability, Mission Control
            ├─ Keuangan
            ├─ Sales & Marketing
            ├─ Property
            ├─ HR
            ├─ Legal
            └─ IT
```

Direktur Utama dan Genesis adalah layer lintas divisi, bukan divisi ketujuh
atau role yang dapat menggantikan manusia.

## Siklus nilai bisnis

Fokus awal ALOS adalah perusahaan properti: menemukan dan memvalidasi peluang
property, market, customer, partner, dan pendapatan. Output tidak berhenti
pada laporan; Genesis dapat mengusulkan tindakan berikutnya yang aman.

```text
Business goal
  → Research Mission
  → source/evidence collection
  → finding dan opportunity hypothesis
  → feasibility / experiment plan
  → artifact proposal
     (document, workflow, website preview, agent, task plan)
  → human approval bila diperlukan
  → staged execution melalui shared runtime
  → evidence, KPI, cost, learning loop
```

Portofolio, P&L, rekening, CRM, dan bukti proyek tetap terpisah (ring-fenced).
Genesis tidak boleh mencampur forecast, target, atau klaim dengan actual yang
belum diverifikasi. Semua output menyatakan sumber, versi, status bukti, dan
tingkat keyakinan.

## Prinsip desain

1. **Satu platform.** Satu database PostgreSQL, satu backend, satu runtime,
   dan satu registry universal. Tidak ada database, microservice, atau UI
   wajib per agent.
2. **Agent bersifat dinamis.** Agent, sub-agent, dan sub-sub-agent berbagi
   Agent Contract, Agent Registry, lifecycle, tool guardrail, dan audit yang
   sama. `parent_agent_id` hanya membentuk delegasi teknis, bukan struktur
   organisasi atau taxonomy permanen.
3. **Artifact bersifat generik.** Dokumen, research brief, website preview,
   workflow, task plan, dan agent proposal adalah Artifact versi. Agent
   Contract adalah spesialisasi artifact yang dapat dieksekusi setelah lulus
   governance.
4. **Automation dengan batas.** Genesis boleh meneliti, menyusun draft,
   menguji pada data sintetis, membuat preview, serta membuat task yang sudah
   diizinkan. Ia tidak boleh menyetujui dirinya sendiri atau melakukan side
   effect berisiko.
5. **Evidence sebelum klaim.** Setiap insight dan hasil task memiliki source
   locator, source version, classification, evidence status, dan citation.
6. **Manusia pemegang otoritas.** Direksi/reviewer menyetujui rilis, biaya,
   perubahan akses, tindakan eksternal, dan tindakan material/irreversible.

## Wewenang Genesis

| Genesis dapat otomatis | Genesis hanya boleh mengusulkan | Selalu human approval |
| --- | --- | --- |
| Analisis sumber yang diizinkan, draft, test sintetis, preview sandbox, task low-risk yang sudah dikontrak | Agent/sub-agent baru, prompt/tool baru, website staging, experiment, jadwal baru, perubahan policy low-risk | Produksi, pengeluaran/komitmen biaya, pembayaran, aksi legal/HR, komunikasi eksternal, akses/credential, penghapusan data, perubahan organisasi |

## Pembuktian MVP1

MVP1 tidak berusaha mengotomatisasi seluruh perusahaan. Ia membuktikan satu
vertical slice yang dapat diperluas tanpa re-arsitektur:

> Requirement Dirut → Property R&D Mission berbasis sumber sintetis → cited
> research brief dan task plan → Agent Contract → validation/test → human
> review → staging/activation → scheduled/run → evidence, cost, audit →
> suspend/rollback.

Daily Brief Agent, Evidence Checker Agent, dan Permit/Overdue Monitor Agent
adalah tiga **validation agent** untuk membuktikan registry dan runtime yang
sama; bukan struktur produk yang mengunci Genesis hanya pada tiga kemampuan.
