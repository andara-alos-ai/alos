CREATE SCHEMA IF NOT EXISTS genesis;

CREATE TABLE IF NOT EXISTS genesis.change_requests (
    request_id uuid PRIMARY KEY,
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    strategy text NOT NULL CHECK (strategy IN ('REUSE', 'EXTEND', 'CREATE')),
    requested_by_user_id uuid NOT NULL REFERENCES identity.users,
    justification text NOT NULL,
    source_references jsonb NOT NULL,
    request_payload jsonb NOT NULL,
    proposal_payload jsonb NOT NULL,
    test_payload jsonb NOT NULL,
    status text NOT NULL CHECK (
        status IN (
            'INVALID', 'AWAITING_HUMAN_REVIEW', 'REJECTED',
            'APPROVED', 'STAGED', 'RELEASED'
        )
    ),
    production_effect boolean NOT NULL DEFAULT false CHECK (production_effect = false),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS genesis.reviews (
    review_id uuid PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES genesis.change_requests,
    gate text NOT NULL CHECK (gate IN ('BUSINESS', 'TECHNICAL')),
    decision text NOT NULL CHECK (decision IN ('APPROVED', 'REJECTED')),
    reviewer_user_id uuid NOT NULL REFERENCES identity.users,
    notes text NOT NULL,
    reviewed_at timestamptz NOT NULL,
    UNIQUE (request_id, gate)
);

CREATE TABLE IF NOT EXISTS genesis.release_packages (
    release_id uuid PRIMARY KEY,
    request_id uuid NOT NULL UNIQUE REFERENCES genesis.change_requests,
    contract_snapshot jsonb NOT NULL,
    contract_digest char(64) NOT NULL,
    status text NOT NULL CHECK (status IN ('STAGED', 'RELEASED')),
    staged_by_user_id uuid NOT NULL REFERENCES identity.users,
    released_by_user_id uuid REFERENCES identity.users,
    production_effect boolean NOT NULL DEFAULT false CHECK (production_effect = false),
    staged_at timestamptz NOT NULL,
    released_at timestamptz,
    CHECK (
        (status = 'STAGED' AND released_by_user_id IS NULL AND released_at IS NULL)
        OR (status = 'RELEASED' AND released_by_user_id IS NOT NULL AND released_at IS NOT NULL)
    )
);

CREATE TABLE IF NOT EXISTS genesis.stage_events (
    stage_event_id uuid PRIMARY KEY,
    request_id uuid NOT NULL REFERENCES genesis.change_requests,
    stage text NOT NULL CHECK (
        stage IN (
            'SOURCE', 'ANALYZE', 'GENERATE', 'VALIDATE', 'TEST', 'DIFF',
            'HUMAN_REVIEW', 'STAGING', 'RELEASE'
        )
    ),
    actor_user_id uuid NOT NULL REFERENCES identity.users,
    result_payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS genesis_request_queue_idx
    ON genesis.change_requests (organization_id, status, updated_at DESC);

CREATE OR REPLACE FUNCTION genesis.prevent_release_package_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.request_id IS DISTINCT FROM OLD.request_id
       OR NEW.contract_snapshot IS DISTINCT FROM OLD.contract_snapshot
       OR NEW.contract_digest IS DISTINCT FROM OLD.contract_digest
       OR NEW.staged_by_user_id IS DISTINCT FROM OLD.staged_by_user_id
       OR NEW.staged_at IS DISTINCT FROM OLD.staged_at
       OR NEW.production_effect IS DISTINCT FROM OLD.production_effect THEN
        RAISE EXCEPTION 'Genesis release package content is immutable';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS genesis_release_package_immutable_trigger
    ON genesis.release_packages;

CREATE TRIGGER genesis_release_package_immutable_trigger
BEFORE UPDATE ON genesis.release_packages
FOR EACH ROW
EXECUTE FUNCTION genesis.prevent_release_package_mutation();
