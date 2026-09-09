-- Digest-bound, one-time material action execution results.
ALTER TABLE operational.proposed_actions
    ADD COLUMN IF NOT EXISTS executed_entity_type text,
    ADD COLUMN IF NOT EXISTS executed_entity_id uuid,
    ADD COLUMN IF NOT EXISTS execution_error_code text;

CREATE UNIQUE INDEX IF NOT EXISTS operational_proposed_action_approval_subject_idx
    ON operational.approval_requests (subject_id)
    WHERE approval_kind = 'PROPOSED_ACTION' AND status <> 'CANCELLED';

-- PostgreSQL treats NULL values as distinct in a normal unique constraint.  Context
-- without an explicit source version must still be idempotent.
CREATE UNIQUE INDEX IF NOT EXISTS genesis_conversation_context_stable_idx
    ON genesis.conversation_context (
        conversation_id, entity_type, entity_id, coalesce(source_version, '')
    );
