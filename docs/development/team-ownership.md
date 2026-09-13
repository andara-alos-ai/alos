# Team ownership

Ownership berarti primary responsibility untuk quality, operability, dan
keputusan di suatu area. Ownership bukan hak veto tunggal dan bukan larangan
review lintas area.

| Owner area | Primary responsibility | Contoh scope repository |
| --- | --- | --- |
| Architecture / AI / GENESIS owner | System boundaries, Factory resolution, Agent Contract, ModelGateway, prompt/model policy, eval, runtime semantics, ADR consistency | `services/platform/src/alos/genesis`, `agents`, `runtime/agentic`, model gateway modules, `definitions`, architecture docs |
| Frontend / Product owner | ARA dan operational UX, accessibility, state representation, API client contract, product terminology | `apps/web`, product docs |
| Backend / Platform / Infra owner | API enforcement, identity/RBAC, persistence, ToolExecutor, jobs, audit, database, deployment, observability, backup/recovery | platform modules di luar AI-specific core, `infra`, `scripts`, operations docs |

Area yang beririsan memiliki co-review wajib. Contoh: perubahan lifecycle
memerlukan Architecture/AI dan Backend/Platform; perubahan governance UI
memerlukan Frontend/Product tetapi backend owner tetap memverifikasi
enforcement. Security, data scope, dan operability dapat direview oleh semua
owner.

## Definition of ownership done

Owner memastikan:

- current implementation dan target architecture dibedakan;
- API/schema/state punya test sesuai risiko;
- error, audit, metrics, rollback, dan runbook dipertimbangkan;
- perubahan lintas boundary mendapat reviewer area terkait;
- dokumentasi kanonik dan ADR diperbarui dalam change yang sama;
- tidak ada keputusan arsitektur tersembunyi hanya di UI, migration, atau chat.
