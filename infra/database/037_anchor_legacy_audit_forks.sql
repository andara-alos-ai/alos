-- Register audit forks that predate the Stage 0 per-organization advisory lock.
-- Anchors preserve the immutable historical entries without treating future forks
-- as valid. New audit writes remain serialized by organization.

INSERT INTO audit.chain_anchors (organization_id, anchored_hash, reason)
SELECT entry.organization_id, entry.previous_hash,
       'LEGACY_FORK_REGISTERED_DURING_STAGE_ZERO_HARDENING'
FROM audit.entries AS entry
WHERE entry.organization_id IS NOT NULL
  AND entry.previous_hash IS NOT NULL
GROUP BY entry.organization_id, entry.previous_hash
HAVING count(*) > 1
ON CONFLICT (organization_id, anchored_hash) DO NOTHING;
