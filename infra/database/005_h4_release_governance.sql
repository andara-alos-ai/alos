-- H4 Release: explicit governance state and immutable lifecycle evidence.
ALTER TABLE governance.test_cases
    DROP CONSTRAINT IF EXISTS governance_test_cases_category_check;
ALTER TABLE governance.test_cases
    DROP CONSTRAINT IF EXISTS test_cases_category_check;
ALTER TABLE governance.test_cases
    ADD CONSTRAINT governance_test_cases_category_check
    CHECK (category IN ('POSITIVE', 'NEGATIVE', 'REGRESSION', 'SECURITY', 'RECOVERY'));

ALTER TABLE governance.reviews
    DROP CONSTRAINT IF EXISTS governance_reviews_decision_check;
ALTER TABLE governance.reviews
    DROP CONSTRAINT IF EXISTS reviews_decision_check;
ALTER TABLE governance.reviews
    ADD CONSTRAINT governance_reviews_decision_check
    CHECK (decision IN ('APPROVED', 'REJECTED', 'RETURNED'));

CREATE TABLE governance.agent_change_requests (
    change_request_id uuid PRIMARY KEY REFERENCES genesis.change_requests,
    agent_contract_id uuid NOT NULL REFERENCES agents.contracts,
    agent_version_id uuid NOT NULL REFERENCES agents.versions,
    maker_user_id uuid NOT NULL REFERENCES identity.users,
    checker_user_id uuid REFERENCES identity.users,
    approver_user_id uuid REFERENCES identity.users,
    state text NOT NULL DEFAULT 'DRAFT' CHECK (state IN (
        'DRAFT', 'TESTED', 'IN_REVIEW', 'RETURNED', 'REJECTED', 'APPROVED',
        'RELEASED', 'ACTIVE', 'SUSPENDED', 'ROLLED_BACK'
    )),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE governance.agent_lifecycle_events (
    lifecycle_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_sequence bigserial NOT NULL UNIQUE,
    change_request_id uuid NOT NULL REFERENCES genesis.change_requests,
    agent_version_id uuid NOT NULL REFERENCES agents.versions,
    from_state text,
    to_state text NOT NULL,
    actor_user_id uuid NOT NULL REFERENCES identity.users,
    reason text NOT NULL,
    correlation_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX active_kill_switch_per_agent_idx
    ON governance.kill_switches (organization_id, agent_contract_id)
    WHERE active AND agent_contract_id IS NOT NULL;
CREATE UNIQUE INDEX one_review_per_gate_per_change_idx
    ON governance.reviews (change_request_id, review_gate);
CREATE INDEX agent_change_requests_version_state_idx
    ON governance.agent_change_requests (agent_version_id, state);
CREATE INDEX agent_lifecycle_events_request_created_idx
    ON governance.agent_lifecycle_events (change_request_id, event_sequence DESC);
