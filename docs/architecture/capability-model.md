# Capability model

Status: **CURRENT IMPLEMENTATION + TARGET ARCHITECTURE**.

Capability adalah unit kemampuan yang dapat ditemukan, dikonfigurasi, diversi, diuji,
dan dikelola lifecycle-nya. `capabilities/registry.py` saat ini menjadi katalog
authoritative untuk capability dan backing typed tool. GENESIS Factory lebih dahulu
meresolusi bentuk capability; Agent hanya dipilih bila reasoning/autonomy diperlukan.

Tipe target meliputi `AGENT`, `SKILL`, `WORKFLOW`, `RULE`, `VALIDATOR`, `REPORT`,
`HUMAN_TASK`, `SCHEDULE`, `EVENT_HANDLER`, `CONNECTOR_REQUIREMENT`,
`TOOL_REQUIREMENT`, dan `COMPOSITE`. Generic lifecycle/release untuk seluruh tipe belum
lengkap; saat ini handoff end-to-end paling matang untuk proposal yang memuat Agent.

Setiap capability material harus memiliki exact version, scope, risk, data
classification, dependency/tool, evidence, decision, release, active pointer, serta
rollback semantics. DRAFT dan automated validation tidak memberi authority ACTIVE.
