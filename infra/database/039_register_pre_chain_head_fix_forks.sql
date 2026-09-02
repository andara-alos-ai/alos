-- Register exact fork members created before audit writers selected the graph
-- leaf instead of relying on timestamp/UUID ordering. Future forks remain invalid.

WITH fork_members AS (
    SELECT child.organization_id,
           child.audit_entry_id,
           count(*) OVER (
               PARTITION BY child.organization_id, child.previous_hash
           ) AS sibling_count
    FROM audit.entries AS child
    WHERE child.organization_id IS NOT NULL
      AND child.previous_hash IS NOT NULL
)
INSERT INTO audit.chain_legacy_exceptions (
    organization_id,
    audit_entry_id,
    reason
)
SELECT organization_id,
       audit_entry_id,
       'PRE_CHAIN_HEAD_SELECTION_FIX_FORK_REGISTERED_DURING_STAGE_ZERO_HARDENING'
FROM fork_members
WHERE sibling_count > 1
ON CONFLICT (organization_id, audit_entry_id) DO NOTHING;
