-- Durable workflow state for the governed Genesis document path.
-- The workflow records only DRAFT artifacts and a handoff to H4; it never
-- creates an active agent or mutates the source document.
CREATE TABLE genesis.document_workflows (
    workflow_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    conversation_id uuid NOT NULL UNIQUE REFERENCES genesis.conversations,
    source_document_id uuid NOT NULL REFERENCES documents.records,
    source_version_number integer NOT NULL CHECK (source_version_number > 0),
    source_content_sha256 char(64) NOT NULL,
    analysis_document_id uuid NOT NULL UNIQUE REFERENCES documents.records,
    rnd_document_id uuid UNIQUE REFERENCES documents.records,
    checklist_document_id uuid UNIQUE REFERENCES documents.records,
    completion_document_id uuid UNIQUE REFERENCES documents.records,
    agent_proposal_artifact_id uuid UNIQUE REFERENCES genesis.artifacts,
    h4_handoff_artifact_id uuid UNIQUE REFERENCES genesis.artifacts,
    status text NOT NULL DEFAULT 'ANALYSIS_DRAFT' CHECK (status IN (
        'ANALYSIS_DRAFT',
        'RND_DRAFT',
        'CHECKLIST_DRAFT',
        'COMPLETION_DRAFT',
        'AGENT_PROPOSAL_DRAFT',
        'READY_FOR_H4'
    )),
    created_by_user_id uuid NOT NULL REFERENCES identity.users,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX genesis_document_workflows_workspace_updated_idx
    ON genesis.document_workflows (workspace_id, updated_at DESC);
CREATE INDEX genesis_document_workflows_source_idx
    ON genesis.document_workflows (source_document_id, created_at DESC);
