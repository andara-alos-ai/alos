export const roles = [
  "DIRECTOR",
  "AI_EXECUTIVE",
  "DIVISION_HEAD",
  "SALES",
  "FINANCE",
  "PROPERTY",
  "HR",
  "LEGAL",
  "IT_ADMIN",
  "AUDITOR",
] as const;

export type Role = (typeof roles)[number];

export type Principal = {
  user_id: string;
  organization_id: string;
  roles: Role[];
  division_codes: string[];
  project_ids: string[];
};

export type Project = {
  project_id: string;
  organization_id: string;
  code: string;
  name: string;
  status: "DRAFT" | "ACTIVE" | "ON_HOLD" | "CLOSED";
  created_at: string;
};

export type UserStatus = "INVITED" | "ACTIVE" | "SUSPENDED";

export type RoleAssignment = {
  assignment_id: string;
  role: Role;
  division_code: string | null;
  valid_from: string;
  valid_until: string | null;
  reason: string;
  created_at: string;
};

export type ProjectAssignment = {
  assignment_id: string;
  project_id: string;
  project_code: string;
  project_name: string;
  valid_from: string;
  valid_until: string | null;
  reason: string;
  created_at: string;
};

export type UserDirectoryRecord = {
  user_id: string;
  email: string;
  display_name: string;
  status: UserStatus;
  roles: RoleAssignment[];
  projects: ProjectAssignment[];
  created_at: string;
  updated_at: string;
};

export type UserDirectoryPage = PageResult<UserDirectoryRecord>;

export type WorkQueueScope = "mine" | "unassigned" | "division" | "overdue";

export type WorkItem = {
  work_item_id: string;
  organization_id: string;
  project_id: string | null;
  division_code: string;
  title: string;
  work_type: string;
  priority: "LOW" | "NORMAL" | "HIGH" | "CRITICAL";
  status: string;
  owner_user_id: string | null;
  claimed_at: string | null;
  due_at: string | null;
  overdue: boolean;
  escalation_level: number;
  escalated_at: string | null;
  correlation_id: string;
  created_at: string;
  updated_at: string;
};

export type Reminder = {
  reminder_id: string;
  work_item_id: string | null;
  approval_request_id: string | null;
  recipient_user_id: string | null;
  division_code: string | null;
  reminder_type: "DUE_SOON" | "OVERDUE" | "ESCALATION";
  escalation_level: number;
  status: string;
  scheduled_for: string;
  created_at: string;
};

export type OperationsHealth = {
  pending_events: number;
  retry_events: number;
  processing_events: number;
  dead_letter_events: number;
  oldest_pending_at: string | null;
  last_worker_status: string | null;
  last_worker_started_at: string | null;
  last_worker_completed_at: string | null;
};

export type PageResult<T> = {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  pages: number;
};

export type DocumentRecord = {
  document_id: string;
  project_id: string | null;
  division_code: string | null;
  logical_name: string;
  classification: string;
  document_version_id: string;
  version_number: number;
  original_filename: string | null;
  sha256: string;
  media_type: string;
  size_bytes: number;
  storage_provider: string;
  scan_status: string;
  verification_status: string;
  created_at: string;
  updated_at: string;
};

export type ApprovalRecord = {
  approval_request_id: string;
  work_item_id: string;
  project_id: string | null;
  division_code: string;
  requester_user_id: string;
  policy_code: string;
  policy_version: string;
  status: string;
  material_fingerprint: string;
  created_at: string;
  decided_at: string | null;
  approver_user_id: string | null;
  decision_reason: string | null;
};

export type ExceptionRecord = {
  exception_id: string;
  work_item_id: string | null;
  project_id: string | null;
  division_code: string | null;
  category: string;
  severity: string;
  status: string;
  owner_user_id: string | null;
  due_at: string | null;
  created_at: string;
};

export type CapaRecord = {
  capa_id: string;
  exception_id: string;
  work_item_id: string | null;
  project_id: string | null;
  division_code: string | null;
  status: string;
  root_cause: string | null;
  corrective_action: string | null;
  preventive_action: string | null;
  reviewer_user_id: string | null;
  due_at: string | null;
  closed_at: string | null;
  created_at: string;
};
