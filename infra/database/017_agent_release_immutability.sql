CREATE OR REPLACE FUNCTION agents.enforce_agent_release_immutability()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.agent_id IS DISTINCT FROM OLD.agent_id
       OR NEW.version IS DISTINCT FROM OLD.version THEN
        RAISE EXCEPTION 'agent_id dan version pada Agent Release tidak dapat diubah';
    END IF;

    IF OLD.definition ? 'contract_digest'
       AND NEW.definition IS DISTINCT FROM OLD.definition THEN
        RAISE EXCEPTION 'snapshot Agent Contract yang telah distandardisasi tidak dapat diubah';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS agent_release_immutable_trigger ON agents.agent_releases;

CREATE TRIGGER agent_release_immutable_trigger
BEFORE UPDATE ON agents.agent_releases
FOR EACH ROW
EXECUTE FUNCTION agents.enforce_agent_release_immutability();
