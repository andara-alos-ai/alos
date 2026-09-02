ALTER TABLE platform.reminders
    DROP CONSTRAINT IF EXISTS reminders_work_item_id_fkey;

ALTER TABLE platform.reminders
    ADD CONSTRAINT reminders_work_item_id_fkey
    FOREIGN KEY (work_item_id)
    REFERENCES platform.work_items (work_item_id)
    ON DELETE CASCADE;

ALTER TABLE platform.reminders
    DROP CONSTRAINT IF EXISTS reminders_approval_request_id_fkey;

ALTER TABLE platform.reminders
    ADD CONSTRAINT reminders_approval_request_id_fkey
    FOREIGN KEY (approval_request_id)
    REFERENCES governance.approval_requests (approval_request_id)
    ON DELETE CASCADE;
