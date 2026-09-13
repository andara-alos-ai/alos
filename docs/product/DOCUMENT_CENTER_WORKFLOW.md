# Document Center workflow

Document Center adalah repositori dokumen kanonik per workspace. Tampilan ARA
atau GENESIS tidak boleh membuat salinan authority kedua dari record yang sama.

## CURRENT IMPLEMENTATION

Setiap document record memiliki version content, digest SHA-256, owner,
classification, status, checklist, dan audit. Alur dokumen saat ini:

```text
manual or GENESIS document DRAFT
→ automated and human checklist
→ IN_REVIEW
→ APPROVED or REJECTED
```

`APPROVED` pada document lifecycle bukan `RELEASED` atau `ACTIVE` pada
capability lifecycle. Publikasi eksternal dan write-back connector memerlukan
gate/ToolExecutor terpisah.

Backend document path masih menerima checker dari beberapa role compatibility,
termasuk `BUSINESS_REVIEWER`, `TECHNICAL_REVIEWER`, dan `QA_SECURITY`, serta
role lama `DIVISION_OWNER`/`IT_LEAD`. Ini adalah compatibility implementation,
bukan kewajiban akun manusia pada governance Factory target.

## Safety rules

- Maker document tidak dapat menyelesaikan independent human check atau
  menyetujui document material miliknya sendiri.
- Semua checklist wajib PASS sebelum submit.
- Review/decision terikat document version/digest.
- GENESIS hanya membuat draft dan tidak mempublikasikan atau memberi approval.
- Credential, API key, dan raw secret tidak boleh masuk content atau audit.
- Write ke sistem eksternal selalu melalui connector/tool yang approved dan
  permission yang tepat.

Governance capability/Agent dijelaskan pada
[governance model](../governance/governance-model.md); alur ini tidak boleh
dipakai sebagai pengganti lifecycle release capability.
