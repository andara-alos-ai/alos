# ARA boundary

Status: **CURRENT IMPLEMENTATION + TARGET ARCHITECTURE**.

ARA adalah AI workspace yang dipakai manusia. Ownership ARA mencakup conversation,
context selection, document assistance, upload intake, drafting, user-facing search,
dan follow-up. Implementasi backend berada di `alos/ara/conversations`,
`alos/ara/context`, dan `alos/ara/assistance`.

Route `/api/v1/genesis` dan import `alos.genesis.chat/history/...` masih dipertahankan
sebagai compatibility surface. Keduanya tidak mengubah conceptual ownership: user
berinteraksi dengan ARA; GENESIS mengelola capability. Penghapusan alias memerlukan
deprecation notice, consumer migration, dan regression test pada pekerjaan terpisah.

ARA tidak menentukan permission, scope, provider, approval, atau release. Semua request
melewati backend authority, Capability Registry, ModelGateway, ToolExecutor, dan domain
repository yang relevan.
