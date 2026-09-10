# GENESIS MVP1 / H5 Checklist Traceability

| Requirement | Implementation | Test/evidence | Status |
| --- | --- | --- | --- |
| One GENESIS, shared runtime, logical validation agents | `genesis/agent_designer.py`, `runtime/service.py`, validation catalog | `test_validation_matrix_postgres.py` requires disposable PostgreSQL | BLOCKED |
| Natural language to actual DRAFT Contract | `/api/v1/genesis/agent-requests`, `ModelAgentDesignGenerator` | strict `ProposedAgentDesign`; PostgreSQL audit/version evidence pending | BLOCKED |
| No auto-active high-risk agent | registry + release governance | Designer always calls `create_draft`; integration proof pending | BLOCKED |
| Contract capability/tool/permission/test traceability | capability registry, Tool Registry, Permission Policy, release tests | PostgreSQL Contract snapshot and registry tests pending | BLOCKED |
| Adaptive GENESIS answer | `genesis/chat.py`, `genesis-chat.tsx` | `test_genesis_chat_response.py` | PASS |
| No-source and inference reliability | `GenesisResponseContent` backend validation | no-source/malformed-output tests | PASS |
| Ask does not become task | chat only exposes controlled action draft status | action requires explicit request and separate approved execution | PASS |
| Provider bounded retry/fallback | `RetryingModelGateway`, gateway factory | gateway tests | PASS |
| Budget 70/90 threshold events | runtime budget persistence | exact threshold event evidence | BLOCKED |
| Generic immutable idempotency | Task request digest, Proposed Action digest, DB uniqueness | PostgreSQL duplicate/concurrency evidence | BLOCKED |
| Backup restore | backup + isolated restore scripts | staging artifact | BLOCKED |
| Cross-scope/tool/permission denial | authorization and typed Tool Executor | security/runtime tests | PASS |
| H5 smoke | `scripts/testing/h5-smoke.ps1` | generated JSON artifact with SHA/time/environment | BLOCKED |
| Frontend presentation flow | GENESIS, Document, Agent Registry, Governance, Project controls | frontend quality gate plus manual rehearsal | MANUAL_EVIDENCE_REQUIRED |
| Management live demo | governed create-agent flow | management rehearsal artifact | MANUAL_EVIDENCE_REQUIRED |
| Actual invoices/payments | intentionally outside pilot fixture scope | business evidence | MANUAL_EVIDENCE_REQUIRED |
| Cloudflare/R2 activation | environment integration | organization configuration | NEEDS_CONFIGURATION |
| MFA through external IdP | external identity tenant | IdP configuration | NEEDS_CONFIGURATION |
| Release decision | `compliance.release_decisions`, `/api/v1/readiness/decisions` | fresh migration and human Director record pending | BLOCKED |
