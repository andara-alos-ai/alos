-- Canonical provenance metadata for every immutable source version.
ALTER TABLE sources.versions
    ADD COLUMN retrieved_at timestamptz,
    ADD COLUMN lineage jsonb NOT NULL DEFAULT '{}'::jsonb
        CHECK (jsonb_typeof(lineage) = 'object'),
    ADD COLUMN reliability numeric(4,3) NOT NULL DEFAULT 1.000
        CHECK (reliability >= 0 AND reliability <= 1),
    ADD COLUMN freshness text NOT NULL DEFAULT 'UNKNOWN'
        CHECK (char_length(freshness) BETWEEN 1 AND 40);

UPDATE sources.versions
SET retrieved_at = received_at
WHERE retrieved_at IS NULL;

ALTER TABLE sources.versions
    ALTER COLUMN retrieved_at SET NOT NULL;

CREATE INDEX source_versions_retrieved_idx
    ON sources.versions (source_id, retrieved_at DESC);
