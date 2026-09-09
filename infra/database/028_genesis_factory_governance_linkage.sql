-- Link Factory proposals to the existing Agent Registry and release-governance lifecycle.
ALTER TABLE genesis.factory_requests
    ADD COLUMN release_change_request_id uuid REFERENCES governance.agent_change_requests;

CREATE UNIQUE INDEX genesis_factory_release_link_idx
    ON genesis.factory_requests (release_change_request_id)
    WHERE release_change_request_id IS NOT NULL;
