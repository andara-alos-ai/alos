ALTER TABLE finance.payment_checks
    DROP CONSTRAINT IF EXISTS payment_checks_payment_request_id_fkey;

ALTER TABLE finance.payment_checks
    ADD CONSTRAINT payment_checks_payment_request_id_fkey
    FOREIGN KEY (payment_request_id)
    REFERENCES finance.payment_requests (payment_request_id)
    ON DELETE CASCADE;

ALTER TABLE platform.work_item_assignments
    DROP CONSTRAINT IF EXISTS work_item_assignments_work_item_id_fkey;

ALTER TABLE platform.work_item_assignments
    ADD CONSTRAINT work_item_assignments_work_item_id_fkey
    FOREIGN KEY (work_item_id)
    REFERENCES platform.work_items (work_item_id)
    ON DELETE CASCADE;
