# ADR-004: Validation non-production terpisah dari live production

- Status: Accepted
- Tanggal awal: 2026-09-03
- Implementation note: 2026-09-13

## Context

Lifecycle dan Runtime perlu diuji dengan data/provider aman tanpa menjadikan
hasil uji sebagai approval atau production readiness.

## Decision

- `local`/`test` dapat memakai Gemini dan bootstrap identity khusus development.
- Staging/production menolak Gemini. Adapter OpenAI atau provider `disabled`
  adalah konfigurasi yang valid sesuai environment policy.
- Runtime test-mode dapat menjalankan exact Agent Version `DRAFT` di local,
  test, atau staging untuk menghasilkan evidence. Bila exact version tidak
  diberikan, version `ACTIVE` diprioritaskan.
- Production tidak boleh menjalankan draft test-mode.
- Test run tidak mengubah `active_version_id`, tidak memberi permission, dan
  tidak memenuhi human approval dengan sendirinya.
- Data perusahaan/credential tidak boleh masuk local validation fixture.

## Consequences

- Evidence harus menyimpan environment, exact version, correlation ID, actor,
  waktu, evaluator, expected/actual, dan status.
- Staging evidence tidak boleh dipromosikan sebagai production evidence tanpa
  review scope/configuration.
- Local bootstrap team dan role compatibility bukan model akun organisasi.
- Provider, identity, object storage, backup, HTTPS, monitoring, serta rollback
  harus divalidasi pada topology deployment yang benar sebelum release.
