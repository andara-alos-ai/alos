CREATE UNIQUE INDEX IF NOT EXISTS sales_leads_project_phone_unique_idx
    ON sales.leads (organization_id, project_id, phone)
    WHERE phone IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS sales_leads_project_email_unique_idx
    ON sales.leads (organization_id, project_id, lower(email))
    WHERE email IS NOT NULL;
