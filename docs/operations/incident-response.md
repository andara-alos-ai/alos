# Incident response

1. Batasi dampak: disable provider, suspend capability/Agent, request cancellation, atau
   aktifkan kill switch sesuai scope; jangan menghapus audit/evidence.
2. Catat waktu, environment, exact version/commit, correlation ID, actor, dan data class.
3. Rotasi credential bila ada kemungkinan exposure dan perlakukan log/prompt sebagai data.
4. Pulihkan dengan exact known-good version atau governed rollback; schema database tidak
   di-downgrade dengan mengubah migration lama.
5. Verifikasi scope, active pointer, job backlog, provider/tool traffic, dan audit setelah
   recovery. Buat corrective action dan regression test sebelum menutup incident.

Detail vulnerability sensitif dilaporkan privat sesuai root `SECURITY.md`.
