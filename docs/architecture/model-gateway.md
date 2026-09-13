# ModelGateway

Status: **CURRENT IMPLEMENTATION** untuk OpenAI; **TARGET ARCHITECTURE** untuk provider
tambahan.

Dependency direction wajib:

```text
ARA / GENESIS / Runtime
        → ModelGateway protocol + logical route
        → provider factory/registry
        → approved provider adapter
```

Package `alos/model_gateway` memisahkan request/response model, gateway protocol dan
error, deterministic policy, logical routing, pricing, factory registry, serta adapter
di `providers/`. OpenAI adalah current implementation. `disabled` dan provider yang
tidak terdaftar gagal tertutup; tidak ada fallback tersembunyi.

Agent Contract memilih `light`, `standard`, atau `critical`, bukan raw provider/model.
Backend memetakan route ke model aktual. Menambah provider memerlukan adapter baru,
registrasi factory, config/secret, pricing, egress/classification policy, dan test;
Runtime, GENESIS Factory, Skill, ToolExecutor, dan business logic tidak boleh berubah.

Compatibility import `alos.model_gateway_factory` dan `alos.openai_gateway` tetap ada
sementara agar consumer lama tidak putus.
