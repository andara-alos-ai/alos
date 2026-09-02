-- Bind every Stage 0 audit exception to an exact immutable entry. Hash anchors
-- remain useful checkpoints, but cannot authorize a newly inserted fork.

CREATE TABLE audit.chain_legacy_exceptions (
    organization_id uuid NOT NULL REFERENCES identity.organizations,
    audit_entry_id uuid NOT NULL REFERENCES audit.entries (audit_entry_id),
    reason text NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (organization_id, audit_entry_id)
);

WITH chain_shape AS (
    SELECT child.organization_id,
           child.audit_entry_id,
           child.previous_hash,
           predecessor.audit_entry_id AS predecessor_id,
           count(*) OVER (
               PARTITION BY child.organization_id, child.previous_hash
           ) AS sibling_count
    FROM audit.entries AS child
    LEFT JOIN audit.entries AS predecessor
      ON predecessor.organization_id = child.organization_id
     AND predecessor.entry_hash = child.previous_hash
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
       CASE
           WHEN predecessor_id IS NULL
               THEN 'LEGACY_MISSING_PREDECESSOR_REGISTERED_DURING_STAGE_ZERO_HARDENING'
           ELSE 'LEGACY_FORK_MEMBER_REGISTERED_DURING_STAGE_ZERO_HARDENING'
       END
FROM chain_shape
WHERE predecessor_id IS NULL OR sibling_count > 1;

CREATE TRIGGER audit_chain_legacy_exceptions_append_only
BEFORE UPDATE OR DELETE ON audit.chain_legacy_exceptions
FOR EACH ROW
EXECUTE FUNCTION audit.reject_entry_mutation();
