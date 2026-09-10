-- Carry authenticated Factory tenant scope into release governance before linkage completes.
ALTER TABLE genesis.change_requests
    ADD COLUMN tenant_id uuid;

CREATE INDEX genesis_change_requests_tenant_idx
    ON genesis.change_requests (organization_id, workspace_id, tenant_id, created_at DESC);
