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

export type PilotReadinessCheck = {
  check_id: string;
  category: string;
  title: string;
  status: "PASS" | "WARNING" | "BLOCKED";
  required: boolean;
  detail: string;
  remediation: string | null;
  actual_count: number | null;
  target_count: number | null;
};

export type PilotReadinessReport = {
  organization_id: string;
  project_id: string;
  environment: string;
  evaluated_at: string;
  overall_status: "READY" | "ATTENTION" | "BLOCKED";
  passed_checks: number;
  warning_checks: number;
  blocked_checks: number;
  checks: PilotReadinessCheck[];
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

export type LeadRecord = {
  lead_id: string;
  project_id: string;
  work_item_id: string;
  workflow_run_id: string;
  full_name: string;
  phone: string | null;
  email: string | null;
  source: string;
  consent_recorded: boolean;
  status: string;
  assigned_user_id: string | null;
  current_step: string;
  workflow_status: string;
  created_at: string;
  updated_at: string;
};

export type SalesInteractionRecord = {
  interaction_id: string;
  lead_id: string;
  workflow_run_id: string;
  actor_user_id: string;
  channel: string;
  outcome: string;
  notes: string;
  evidence_reference: string | null;
  evidence_document_version_id: string | null;
  occurred_at: string;
};

export type LeadIntakeResult = {
  lead_id: string;
  work_item_id: string;
  workflow_run_id: string;
  current_step: string;
  work_item_status: string;
  due_at: string;
  correlation_id: string;
};

export type WorkflowActionResult = {
  workflow_run_id: string;
  work_item_id: string;
  lead_id: string;
  current_step: string;
  workflow_status: string;
  work_item_status: string;
  owner_user_id: string | null;
  due_at: string | null;
  terminal: boolean;
  correlation_id: string;
};

export type BudgetRecord = {
  budget_id: string;
  project_id: string;
  code: string;
  name: string;
  currency: string;
  allocated_amount: string;
  committed_amount: string;
  spent_amount: string;
  available_amount: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type PaymentRequestRecord = {
  payment_request_id: string;
  project_id: string;
  budget_id: string;
  work_item_id: string;
  workflow_run_id: string;
  approval_request_id: string | null;
  document_version_id: string;
  requester_user_id: string;
  payee_name: string;
  purpose: string;
  amount: string;
  currency: string;
  requested_payment_date: string;
  status: string;
  budget_available: boolean;
  current_step: string;
  workflow_status: string;
  created_at: string;
  updated_at: string;
};

export type FinanceWorkflowResult = {
  payment_request_id: string;
  workflow_run_id: string;
  work_item_id: string;
  approval_request_id: string | null;
  current_step: string;
  workflow_status: string;
  payment_status: string;
  work_item_status: string;
  reconciliation_status: string | null;
  difference_amount: string | null;
  exception_id: string | null;
  terminal: boolean;
  correlation_id: string;
};

export type SiteEvidenceRecord = {
  site_evidence_id: string;
  project_id: string;
  work_item_id: string;
  workflow_run_id: string;
  document_version_id: string;
  submitted_by_user_id: string;
  work_package_code: string;
  claim_date: string;
  claimed_progress: string;
  measured_progress: string;
  variance: string;
  measurement_note: string;
  status: string;
  reviewer_user_id: string | null;
  verified_progress: string | null;
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type PropertyWorkflowResult = {
  site_evidence_id: string;
  workflow_run_id: string;
  work_item_id: string;
  current_step: string;
  workflow_status: string;
  evidence_status: string;
  work_item_status: string;
  claimed_progress: string;
  measured_progress: string;
  variance: string;
  kpi_snapshot_id: string | null;
  exception_id: string | null;
  capa_id: string | null;
  terminal: boolean;
  correlation_id: string;
};

export type LegalCaseRecord = {
  legal_case_id: string;
  project_id: string;
  work_item_id: string;
  workflow_run_id: string;
  document_version_id: string;
  submitted_by_user_id: string;
  document_type: "PERMIT" | "CONTRACT";
  reference_code: string;
  title: string;
  counterparty: string | null;
  source_authority: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  status: string;
  legal_status: string | null;
  official_source_verified: boolean;
  reviewer_user_id: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type LegalWorkflowResult = {
  legal_case_id: string;
  workflow_run_id: string;
  work_item_id: string;
  document_type: string;
  current_step: string;
  workflow_status: string;
  case_status: string;
  work_item_status: string;
  exception_id: string | null;
  terminal: boolean;
  correlation_id: string;
};

export type RecruitmentRequestRecord = {
  recruitment_request_id: string;
  project_id: string;
  work_item_id: string;
  workflow_run_id: string;
  submitted_by_user_id: string;
  position_title: string;
  requesting_division_code: string;
  employment_type: string;
  headcount: number;
  justification: string;
  criteria_version: string;
  status: string;
  reviewer_user_id: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
  candidate_alias: string;
  screening_status: string;
  missing_criteria: string[];
};

export type PersonnelChecklist = {
  personnel_checklist_id: string;
  recruitment_request_id: string;
  candidate_id: string;
  status: string;
  created_at: string;
  requirements: { requirement_code: string; status: string }[];
};

export type RecruitmentWorkflowResult = {
  recruitment_request_id: string;
  candidate_id: string;
  workflow_run_id: string;
  work_item_id: string;
  current_step: string;
  workflow_status: string;
  recruitment_status: string;
  screening_status: string;
  missing_criteria: string[];
  work_item_status: string;
  personnel_checklist_id: string | null;
  terminal: boolean;
  correlation_id: string;
};

export type ExecutiveBriefRecord = {
  executive_brief_id: string;
  project_id: string | null;
  workflow_run_id: string;
  period_start: string;
  period_end: string;
  title: string;
  narrative: string;
  source_references: string[];
  summary_counts: Record<string, number>;
  decision_item_count: number;
  status: string;
  reviewer_user_id: string | null;
  review_notes: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type ExecutiveBriefResult = {
  executive_brief_id: string;
  executive_snapshot_id: string;
  workflow_run_id: string;
  current_step: string;
  workflow_status: string;
  brief_status: string;
  title: string;
  summary_counts: Record<string, number>;
  narrative: string;
  source_references: string[];
  decision_item_count: number;
  exception_id: string | null;
  terminal: boolean;
  correlation_id: string;
};
