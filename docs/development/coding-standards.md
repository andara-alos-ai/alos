# Coding standards

- Pertahankan modular monolith dan dependency direction antar-boundary.
- Domain repository dekat dengan domain; hindari global mega-repository.
- Runtime/business logic bergantung pada ModelGateway dan ToolExecutor abstraction,
  bukan adapter/SDK eksternal.
- Gunakan type hints ketat, model tervalidasi, error aman, dan server-side authorization.
- Pertahankan public API dengan compatibility shim dan deprecation path bila memindah file.
- Migration existing immutable; perubahan schema selalu append-only.
- Jangan menambah placeholder yang mengklaim fitur masa depan telah tersedia.
- Perubahan behavior membutuhkan test; perubahan arsitektur besar membutuhkan ADR/review.
