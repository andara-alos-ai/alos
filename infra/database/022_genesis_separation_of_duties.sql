CREATE UNIQUE INDEX IF NOT EXISTS genesis_reviews_request_reviewer_idx
    ON genesis.reviews (request_id, reviewer_user_id);

CREATE OR REPLACE FUNCTION genesis.enforce_review_separation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    requester_id uuid;
BEGIN
    SELECT requested_by_user_id
    INTO requester_id
    FROM genesis.change_requests
    WHERE request_id = NEW.request_id;

    IF requester_id = NEW.reviewer_user_id THEN
        RAISE EXCEPTION 'Genesis requester cannot review the same request';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS genesis_review_separation_trigger ON genesis.reviews;

CREATE TRIGGER genesis_review_separation_trigger
BEFORE INSERT OR UPDATE ON genesis.reviews
FOR EACH ROW
EXECUTE FUNCTION genesis.enforce_review_separation();

CREATE OR REPLACE FUNCTION genesis.enforce_release_separation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    requester_id uuid;
BEGIN
    SELECT requested_by_user_id
    INTO requester_id
    FROM genesis.change_requests
    WHERE request_id = NEW.request_id;

    IF requester_id = NEW.staged_by_user_id THEN
        RAISE EXCEPTION 'Genesis requester cannot stage the same request';
    END IF;
    IF NEW.status = 'RELEASED'
       AND (
           NEW.released_by_user_id = requester_id
           OR NEW.released_by_user_id = NEW.staged_by_user_id
       ) THEN
        RAISE EXCEPTION 'Genesis release actor must be separated from requester and stager';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS genesis_release_separation_trigger
    ON genesis.release_packages;

CREATE TRIGGER genesis_release_separation_trigger
BEFORE INSERT OR UPDATE ON genesis.release_packages
FOR EACH ROW
EXECUTE FUNCTION genesis.enforce_release_separation();
