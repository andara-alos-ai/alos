-- H2 Registry: Agent hierarchy is limited to core, sub-agent, and sub-sub-agent.
ALTER TABLE agents.contracts
    ADD COLUMN workspace_id uuid NOT NULL REFERENCES workspace.workspaces,
    ADD COLUMN agent_level smallint NOT NULL DEFAULT 0
    CHECK (agent_level IN (0, 1, 2));

CREATE OR REPLACE FUNCTION agents.validate_contract_parent()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    ancestor_id uuid;
    ancestor_level smallint;
BEGIN
    IF NEW.parent_agent_contract_id IS NULL THEN
        IF NEW.agent_level <> 0 THEN
            RAISE EXCEPTION 'root agent must use level 0';
        END IF;
        RETURN NEW;
    END IF;

    SELECT agent_level
    INTO ancestor_level
    FROM agents.contracts
    WHERE agent_contract_id = NEW.parent_agent_contract_id;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'parent agent contract does not exist';
    END IF;

    IF NEW.agent_level <> ancestor_level + 1 OR NEW.agent_level > 2 THEN
        RAISE EXCEPTION 'parent and child agent levels are invalid';
    END IF;

    ancestor_id := NEW.parent_agent_contract_id;
    WHILE ancestor_id IS NOT NULL LOOP
        IF ancestor_id = NEW.agent_contract_id THEN
            RAISE EXCEPTION 'circular agent parent relationship is not allowed';
        END IF;
        SELECT parent_agent_contract_id
        INTO ancestor_id
        FROM agents.contracts
        WHERE agent_contract_id = ancestor_id;
    END LOOP;

    RETURN NEW;
END;
$$;

CREATE TRIGGER agents_contract_parent_guard
BEFORE INSERT OR UPDATE OF parent_agent_contract_id, agent_level ON agents.contracts
FOR EACH ROW EXECUTE FUNCTION agents.validate_contract_parent();

CREATE INDEX contracts_organization_parent_level_idx
    ON agents.contracts (organization_id, parent_agent_contract_id, agent_level);
CREATE INDEX contracts_workspace_idx
    ON agents.contracts (workspace_id);
CREATE INDEX versions_contract_created_idx
    ON agents.versions (agent_contract_id, created_at DESC);
