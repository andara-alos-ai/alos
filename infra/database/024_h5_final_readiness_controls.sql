-- H5 closure: immutable request digests and human-only pilot-go/no-go decisions.
ALTER TABLE operational.tasks
    ADD COLUMN IF NOT EXISTS request_digest text NOT NULL DEFAULT '';

CREATE SCHEMA IF NOT EXISTS compliance;

CREATE TABLE compliance.release_decisions (
    decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid REFERENCES workspace.workspaces,
    decision text NOT NULL DEFAULT 'PENDING'
        CHECK (decision IN ('PENDING', 'GO', 'HOLD', 'NO_GO')),
    decided_by_user_id uuid REFERENCES identity.users,
    decided_at timestamptz,
    commit_sha text NOT NULL CHECK (char_length(btrim(commit_sha)) BETWEEN 7 AND 128),
    release_version text NOT NULL CHECK (char_length(btrim(release_version)) BETWEEN 1 AND 160),
    technical_readiness text NOT NULL
        CHECK (technical_readiness IN ('PASS', 'HOLD', 'BLOCKED', 'FAIL')),
    uat_report_reference text,
    restore_evidence_reference text,
    known_limitations jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(known_limitations) = 'array'),
    hardening_backlog jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(hardening_backlog) = 'array'),
    notes text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (decision = 'PENDING' AND decided_by_user_id IS NULL AND decided_at IS NULL)
        OR (decision <> 'PENDING' AND decided_by_user_id IS NOT NULL AND decided_at IS NOT NULL)
    )
);

CREATE INDEX compliance_release_decisions_organization_idx
    ON compliance.release_decisions (organization_id, created_at DESC);
