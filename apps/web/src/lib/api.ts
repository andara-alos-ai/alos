import type {
  ApprovalRecord,
  BudgetRecord,
  CapaRecord,
  ConfigurationRegister,
  DocumentRecord,
  ExecutiveBriefRecord,
  ExecutiveBriefResult,
  ExceptionRecord,
  FinanceWorkflowResult,
  LeadIntakeResult,
  LeadRecord,
  LegalCaseRecord,
  LegalWorkflowResult,
  OperationsHealth,
  PageResult,
  PaymentRequestRecord,
  PersonnelChecklist,
  PilotProfile,
  PilotReadinessReport,
  Principal,
  Project,
  ProjectAssignment,
  Reminder,
  RecruitmentRequestRecord,
  RecruitmentWorkflowResult,
  Role,
  RoleAssignment,
  SalesInteractionRecord,
  SiteEvidenceRecord,
  SourcePack,
  UserDirectoryPage,
  UserDirectoryRecord,
  UserStatus,
  UatRun,
  UatScenarioStatus,
  UatSignoffScope,
  WorkItem,
  WorkflowActionResult,
  WorkQueueScope,
  PropertyWorkflowResult,
  GenesisAnalyzeResult,
  GenesisArtifactVersionView,
  GenesisConversationListItem,
  GenesisConversationView,
  GenesisPipelineView,
  SystemReadinessReport,
} from "./types";

import { COOKIE_SESSION_MARKER, readCsrfToken } from "./session";

const configuredBaseUrl = process.env.NEXT_PUBLIC_ALOS_API_URL?.replace(/\/$/, "");
export const apiBaseUrl = configuredBaseUrl || "http://localhost:8000/api/v1";
export const oidcLoginUrl = `${apiBaseUrl}/auth/oidc/login`;

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  options: RequestInit & { token?: string } = {},
): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set("Accept", "application/json");
  if (options.body) headers.set("Content-Type", "application/json");
  if (options.token && options.token !== COOKIE_SESSION_MARKER) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  const method = (options.method || "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = readCsrfToken();
    if (csrfToken && !headers.has("X-CSRF-Token")) {
      headers.set("X-CSRF-Token", csrfToken);
    }
  }

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...options,
      headers,
      credentials: options.credentials ?? "include",
      cache: "no-store",
    });
  } catch {
    throw new ApiError("API ALOS tidak dapat dijangkau. Pastikan backend sedang aktif.", 0);
  }
  if (!response.ok) {
    let message = `Permintaan gagal (${response.status})`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string") message = body.detail;
      if (Array.isArray(body.detail)) {
        const validationMessages = body.detail
          .map((item) => {
            if (typeof item === "object" && item && "msg" in item) return String(item.msg);
            return null;
          })
          .filter(Boolean);
        if (validationMessages.length) message = validationMessages.join("; ");
      }
    } catch {
      // Keep the safe fallback message when the response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getPilotProfiles() {
  return request<PilotProfile[]>("/auth/pilot-profiles");
}

export function loginPilotProfile(userId: string) {
  return request<{ access_token: string; token_type: string; expires_in: number }>(
    "/auth/pilot-login",
    { method: "POST", body: JSON.stringify({ user_id: userId }) },
  );
}

export function getOidcStatus() {
  return request<{ enabled: boolean; provider: "google" | null }>("/auth/oidc/status");
}

export function exchangeOidcCode(code: string) {
  return request<{ access_token: string; token_type: string; expires_in: number }>(
    "/auth/oidc/exchange",
    { method: "POST", body: JSON.stringify({ code }) },
  );
}

export function logoutApi() {
  return request<{ status: string; message: string }>("/auth/logout", { method: "POST" });
}

export function getCsrfTokenApi() {
  return request<{ csrf_token: string }>("/auth/csrf");
}

export function getPrincipal(token?: string) {
  return request<Principal>("/auth/me", token ? { token } : {});
}

export function getProjects(token?: string) {
  return request<Project[]>("/projects", token ? { token } : {});
}

export function createProject(
  token: string,
  payload: { code: string; name: string },
) {
  return request<Project>("/projects", {
    method: "POST",
    token,
    body: JSON.stringify(payload),
  });
}

export function updateProjectStatus(
  token: string,
  projectId: string,
  payload: { status: Project["status"]; reason: string },
) {
  return request<Project>(`/projects/${projectId}/status`, {
    method: "PATCH",
    token,
    body: JSON.stringify(payload),
  });
}

export function getWorkQueue(
  token: string,
  scope: WorkQueueScope,
  projectId: string | null,
) {
  const parameters = new URLSearchParams({ scope, limit: "100" });
  if (projectId) parameters.set("project_id", projectId);
  return request<WorkItem[]>(`/operational/work-queue?${parameters}`, { token });
}

export function getReminders(token: string, limit = 50) {
  return request<Reminder[]>(`/operational/reminders?limit=${limit}`, { token });
}

export function claimWorkItem(token: string, workItemId: string, reason: string) {
  return request<WorkItem>(`/operational/work-items/${workItemId}/claim`, {
    method: "POST",
    token,
    body: JSON.stringify({ reason }),
  });
}

export function releaseWorkItem(token: string, workItemId: string, reason: string) {
  return request<WorkItem>(`/operational/work-items/${workItemId}/release`, {
    method: "POST",
    token,
    body: JSON.stringify({ reason }),
  });
}

export function delegateWorkItem(
  token: string,
  workItemId: string,
  targetUserId: string,
  reason: string,
) {
  return request<WorkItem>(`/operational/work-items/${workItemId}/delegate`, {
    method: "POST",
    token,
    body: JSON.stringify({ target_user_id: targetUserId, reason }),
  });
}

export function updateWorkItemDeadline(
  token: string,
  workItemId: string,
  dueAt: string,
  reason: string,
) {
  return request<WorkItem>(`/operational/work-items/${workItemId}/deadline`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ due_at: dueAt, reason }),
  });
}

export function getOperationsHealth(token: string) {
  return request<OperationsHealth>("/system/operations-health", { token });
}

export function getPilotReadiness(token: string, projectId: string) {
  const parameters = new URLSearchParams({ project_id: projectId });
  return request<PilotReadinessReport>(`/system/pilot-readiness?${parameters}`, { token });
}

export function getGoLiveReadiness(token: string, projectId: string) {
  const parameters = new URLSearchParams({ project_id: projectId });
  return request<PilotReadinessReport>(`/system/go-live-readiness?${parameters}`, { token });
}

export function getSourcePacks(token: string) {
  return request<SourcePack[]>("/genesis/source-packs", { token });
}

export function getConfigurationRegisters(token: string) {
  return request<ConfigurationRegister[]>("/genesis/configuration-registers", { token });
}

export function getUatRuns(token: string, projectId: string) {
  const parameters = new URLSearchParams({ project_id: projectId });
  return request<UatRun[]>(`/uat/runs?${parameters}`, { token });
}

export function createUatRun(token: string, projectId: string, title: string) {
  return request<UatRun>("/uat/runs", {
    method: "POST",
    token,
    body: JSON.stringify({ project_id: projectId, title }),
  });
}

export function startUatRun(token: string, uatRunId: string) {
  return request<UatRun>(`/uat/runs/${uatRunId}/start`, { method: "POST", token });
}

export function recordUatScenario(
  token: string,
  uatRunId: string,
  scenarioId: string,
  input: {
    status: UatScenarioStatus;
    actual_result: string | null;
    defect_severity: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | null;
    defect_summary: string | null;
    evidence: Array<{ document_version_id: string | null; reference: string | null }>;
  },
) {
  return request<UatRun>(`/uat/runs/${uatRunId}/scenarios/${scenarioId}`, {
    method: "PUT",
    token,
    body: JSON.stringify(input),
  });
}

export function signoffUatRun(
  token: string,
  uatRunId: string,
  input: {
    signoff_scope: UatSignoffScope;
    decision: "ACCEPTED" | "ACCEPTED_WITH_RISK" | "REJECTED";
    risk_severity: "LOW" | "MEDIUM" | null;
    notes: string;
  },
) {
  return request<UatRun>(`/uat/runs/${uatRunId}/signoffs`, {
    method: "POST",
    token,
    body: JSON.stringify(input),
  });
}

function queryPath(path: string, projectId: string | null, pageSize = 50): string {
  const parameters = new URLSearchParams({ page: "1", page_size: String(pageSize) });
  if (projectId) parameters.set("project_id", projectId);
  return `${path}?${parameters}`;
}

function idempotencyHeaders(): HeadersInit {
  return { "Idempotency-Key": crypto.randomUUID() };
}

export function getDocuments(token: string, projectId: string | null) {
  return request<PageResult<DocumentRecord>>(queryPath("/documents", projectId), { token });
}

export function getApprovals(token: string, projectId: string | null) {
  return request<PageResult<ApprovalRecord>>(queryPath("/approvals", projectId), { token });
}

export function getExceptions(token: string, projectId: string | null) {
  return request<PageResult<ExceptionRecord>>(queryPath("/exceptions", projectId), { token });
}

export function getCapas(token: string, projectId: string | null) {
  return request<PageResult<CapaRecord>>(queryPath("/capas", projectId), { token });
}

export function getLeads(token: string, projectId: string | null) {
  return request<PageResult<LeadRecord>>(queryPath("/leads", projectId, 100), { token });
}

export function getLeadInteractions(token: string, leadId: string) {
  return request<PageResult<SalesInteractionRecord>>(
    queryPath(`/leads/${leadId}/interactions`, null, 100),
    { token },
  );
}

export function createLead(
  token: string,
  input: {
    project_id: string;
    full_name: string;
    phone: string | null;
    email: string | null;
    source: string;
    consent_recorded: boolean;
    priority: "LOW" | "NORMAL" | "HIGH" | "CRITICAL";
  },
) {
  return request<LeadIntakeResult>("/leads", {
    method: "POST",
    token,
    headers: idempotencyHeaders(),
    body: JSON.stringify(input),
  });
}

export function assignSalesPic(
  token: string,
  workflowRunId: string,
  salesPicUserId: string,
  firstFollowUpAt?: string,
) {
  return request<WorkflowActionResult>(
    `/workflow-runs/${workflowRunId}/sales-assignment`,
    {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify({
        sales_pic_user_id: salesPicUserId,
        first_follow_up_at: firstFollowUpAt || null,
        objective: "Qualification dan tindak lanjut lead",
      }),
    },
  );
}

export function recordSalesInteraction(
  token: string,
  workflowRunId: string,
  input: {
    outcome: "qualified" | "reserved" | "follow_up" | "lost" | "exception";
    channel: string;
    notes: string;
    evidence_reference: string | null;
    evidence_document_version_id: string | null;
    reservation_reference: string | null;
    reservation_date: string | null;
    qualification_result: "HOT" | "WARM" | "COLD" | null;
    lost_reason: string | null;
    next_follow_up_at: string | null;
  },
) {
  return request<WorkflowActionResult>(`/workflow-runs/${workflowRunId}/interactions`, {
    method: "POST",
    token,
    headers: idempotencyHeaders(),
    body: JSON.stringify(input),
  });
}

export function getBudgets(token: string, projectId: string | null) {
  return request<PageResult<BudgetRecord>>(queryPath("/finance/budgets", projectId, 100), {
    token,
  });
}

export function createBudget(
  token: string,
  input: {
    project_id: string;
    code: string;
    name: string;
    currency: string;
    allocated_amount: string;
  },
) {
  return request<BudgetRecord>("/finance/budgets", {
    method: "POST",
    token,
    body: JSON.stringify(input),
  });
}

export function getPaymentRequests(token: string, projectId: string | null) {
  return request<PageResult<PaymentRequestRecord>>(
    queryPath("/finance/payment-requests", projectId, 100),
    { token },
  );
}

export function createPaymentRequest(
  token: string,
  input: {
    project_id: string;
    budget_id: string;
    document_version_id: string;
    supporting_document_version_ids?: string[];
    payee_name: string;
    vendor_reference?: string | null;
    category_code?: string;
    purpose: string;
    amount: string;
    currency: string;
    requested_payment_date: string;
  },
) {
  return request<Pick<PaymentRequestRecord, "payment_request_id" | "status" | "current_step">>(
    "/finance/payment-requests",
    {
    method: "POST",
    token,
    headers: idempotencyHeaders(),
    body: JSON.stringify(input),
    },
  );
}

export function decidePaymentRequest(
  token: string,
  paymentRequestId: string,
  decision: "APPROVED" | "REJECTED" | "REVISION_REQUESTED",
  reason: string,
) {
  return request<FinanceWorkflowResult>(
    `/finance/payment-requests/${paymentRequestId}/decision`,
    {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify({ decision, reason }),
    },
  );
}

export function recordPayment(
  token: string,
  paymentRequestId: string,
  input: {
    payment_reference: string;
    amount: string;
    currency: string;
    paid_at: string;
    evidence_document_version_id: string;
  },
) {
  return request<FinanceWorkflowResult>(
    `/finance/payment-requests/${paymentRequestId}/payment`,
    {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify(input),
    },
  );
}

export function cancelPaymentRequest(token: string, paymentRequestId: string, reason: string) {
  return request<FinanceWorkflowResult>(
    `/finance/payment-requests/${paymentRequestId}/cancel`,
    {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify({ reason }),
    },
  );
}

export function revisePaymentRequest(
  token: string,
  paymentRequestId: string,
  input: {
    project_id: string;
    budget_id: string;
    document_version_id: string;
    supporting_document_version_ids?: string[];
    payee_name: string;
    vendor_reference: string | null;
    category_code: string;
    purpose: string;
    amount: string;
    currency: string;
    requested_payment_date: string;
    reason: string;
  },
) {
  return request<FinanceWorkflowResult>(
    `/finance/payment-requests/${paymentRequestId}/revision`,
    {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify(input),
    },
  );
}

export function reconcilePayment(
  token: string,
  paymentRequestId: string,
  input: { transaction_reference: string; transaction_amount: string; currency: string },
) {
  return request<FinanceWorkflowResult>(
    `/finance/payment-requests/${paymentRequestId}/reconciliation`,
    {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify(input),
    },
  );
}

export function getSiteEvidence(token: string, projectId: string | null) {
  return request<PageResult<SiteEvidenceRecord>>(
    queryPath("/property/site-evidence", projectId, 100),
    { token },
  );
}

export function submitSiteEvidence(
  token: string,
  input: {
    project_id: string;
    document_version_id: string;
    work_package_code: string;
    claim_date: string;
    claimed_progress: string;
    measured_progress: string;
    measurement_note: string;
  },
) {
  return request<PropertyWorkflowResult>("/property/site-evidence", {
    method: "POST",
    token,
    headers: idempotencyHeaders(),
    body: JSON.stringify(input),
  });
}

export function reviewSiteEvidence(
  token: string,
  siteEvidenceId: string,
  input: {
    decision: "ACCEPTED" | "VARIANCE";
    verified_progress: string;
    notes: string;
  },
) {
  return request<PropertyWorkflowResult>(
    `/property/site-evidence/${siteEvidenceId}/review`,
    {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify(input),
    },
  );
}

export function getLegalCases(token: string, projectId: string | null) {
  return request<PageResult<LegalCaseRecord>>(queryPath("/legal/cases", projectId, 100), {
    token,
  });
}

export function submitLegalDocument(
  token: string,
  input: {
    project_id: string;
    document_version_id: string;
    document_type: "PERMIT" | "CONTRACT";
    reference_code: string;
    title: string;
    counterparty: string | null;
    source_authority: string | null;
    effective_date: string | null;
    expiry_date: string | null;
  },
) {
  return request<LegalWorkflowResult>("/legal/documents", {
    method: "POST",
    token,
    headers: idempotencyHeaders(),
    body: JSON.stringify(input),
  });
}

export function reviewLegalDocument(
  token: string,
  legalCaseId: string,
  input: {
    decision: "APPROVED" | "REVISION_REQUESTED" | "REJECTED";
    legal_status: "VERIFIED" | "CONDITIONAL" | "NOT_APPROVED";
    official_source_verified: boolean;
    notes: string;
  },
) {
  return request<LegalWorkflowResult>(`/legal/documents/${legalCaseId}/review`, {
    method: "POST",
    token,
    body: JSON.stringify(input),
  });
}

export function getRecruitmentRequests(token: string, projectId: string | null) {
  return request<PageResult<RecruitmentRequestRecord>>(
    queryPath("/hr/recruitment-requests", projectId, 100),
    { token },
  );
}

export function submitRecruitmentRequest(
  token: string,
  input: {
    project_id: string;
    candidate_document_version_id: string;
    position_title: string;
    requesting_division_code: string;
    employment_type: "PERMANENT" | "CONTRACT" | "INTERNSHIP";
    headcount: number;
    justification: string;
    criteria_version: string;
    candidate_alias: string;
    required_criteria: string[];
    met_criteria: string[];
  },
) {
  return request<RecruitmentWorkflowResult>("/hr/recruitment-requests", {
    method: "POST",
    token,
    headers: idempotencyHeaders(),
    body: JSON.stringify(input),
  });
}

export function decideRecruitment(
  token: string,
  recruitmentRequestId: string,
  input: {
    decision: "SELECTED" | "REJECTED";
    notes: string;
    personnel_requirements: string[];
  },
) {
  return request<RecruitmentWorkflowResult>(
    `/hr/recruitment-requests/${recruitmentRequestId}/decision`,
    {
      method: "POST",
      token,
      headers: idempotencyHeaders(),
      body: JSON.stringify(input),
    },
  );
}

export function getPersonnelChecklist(token: string, recruitmentRequestId: string) {
  return request<PersonnelChecklist>(
    `/hr/recruitment-requests/${recruitmentRequestId}/personnel-checklist`,
    { token },
  );
}

export function getExecutiveBriefs(token: string, projectId: string | null) {
  return request<PageResult<ExecutiveBriefRecord>>(
    queryPath("/executive/briefs", projectId, 100),
    { token },
  );
}

export function generateExecutiveBrief(
  token: string,
  input: {
    title: string;
    period_start: string;
    period_end: string;
    project_id: string | null;
  },
) {
  return request<ExecutiveBriefResult>("/executive/briefs", {
    method: "POST",
    token,
    headers: idempotencyHeaders(),
    body: JSON.stringify(input),
  });
}

export function reviewExecutiveBrief(
  token: string,
  executiveBriefId: string,
  input: { decision: "PUBLISHED" | "REVISION_REQUESTED"; notes: string },
) {
  return request<ExecutiveBriefResult>(`/executive/briefs/${executiveBriefId}/review`, {
    method: "POST",
    token,
    body: JSON.stringify(input),
  });
}

export function getUsers(
  token: string,
  filters: {
    search?: string;
    status?: UserStatus | "";
    role?: Role | "";
    division_code?: string;
  } = {},
) {
  const parameters = new URLSearchParams({ page: "1", page_size: "100" });
  if (filters.search?.trim()) parameters.set("search", filters.search.trim());
  if (filters.status) parameters.set("status", filters.status);
  if (filters.role) parameters.set("role", filters.role);
  if (filters.division_code) parameters.set("division_code", filters.division_code);
  return request<UserDirectoryPage>(`/users?${parameters}`, { token });
}

export function createUser(
  token: string,
  input: { email: string; display_name: string; role: Role; division_code: string | null },
) {
  return request<{ user_id: string }>("/users", {
    method: "POST",
    token,
    body: JSON.stringify(input),
  });
}

export function updateUserStatus(
  token: string,
  userId: string,
  status: Exclude<UserStatus, "INVITED">,
  reason: string,
) {
  return request<UserDirectoryRecord>(`/users/${userId}/status`, {
    method: "PATCH",
    token,
    body: JSON.stringify({ status, reason }),
  });
}

export function addUserRole(
  token: string,
  userId: string,
  input: { role: Role; division_code: string | null; valid_until: string | null; reason: string },
) {
  return request<RoleAssignment>(`/users/${userId}/role-assignments`, {
    method: "POST",
    token,
    body: JSON.stringify(input),
  });
}

export function revokeUserRole(
  token: string,
  userId: string,
  assignmentId: string,
  reason: string,
) {
  return request<void>(`/users/${userId}/role-assignments/${assignmentId}/revoke`, {
    method: "POST",
    token,
    body: JSON.stringify({ reason }),
  });
}

export function addUserProject(
  token: string,
  userId: string,
  input: { project_id: string; valid_until: string | null; reason: string },
) {
  return request<ProjectAssignment>(`/users/${userId}/project-assignments`, {
    method: "POST",
    token,
    body: JSON.stringify(input),
  });
}

export function revokeUserProject(
  token: string,
  userId: string,
  assignmentId: string,
  reason: string,
) {
  return request<void>(`/users/${userId}/project-assignments/${assignmentId}/revoke`, {
    method: "POST",
    token,
    body: JSON.stringify({ reason }),
  });
}

export function analyzeGenesis(
  requestData: {
    prompt: string;
    source_references?: string[];
    division_code?: string;
  },
  token?: string | null,
) {
  return request<GenesisAnalyzeResult>("/genesis/analyze", {
    method: "POST",
    token: token || undefined,
    body: JSON.stringify({
      prompt: requestData.prompt,
      source_references: requestData.source_references || [],
      division_code: requestData.division_code || null,
    }),
  });
}

export function createGenesisConversation(
  requestData: {
    title: string;
    project_id?: string | null;
    initial_prompt?: string | null;
    source_references?: string[];
    division_code?: string | null;
  },
  token?: string | null,
) {
  return request<GenesisConversationView>("/genesis/conversations", {
    method: "POST",
    token: token || undefined,
    body: JSON.stringify({
      title: requestData.title,
      project_id: requestData.project_id || null,
      initial_prompt: requestData.initial_prompt || null,
      source_references: requestData.source_references || [],
      division_code: requestData.division_code || null,
    }),
  });
}

export function listGenesisConversations(
  params?: { limit?: number; offset?: number },
  token?: string | null,
) {
  const limit = params?.limit ?? 50;
  const offset = params?.offset ?? 0;
  return request<GenesisConversationListItem[]>(
    `/genesis/conversations?limit=${limit}&offset=${offset}`,
    { token: token || undefined },
  );
}

export function getGenesisConversation(conversationId: string, token?: string | null) {
  return request<GenesisConversationView>(`/genesis/conversations/${conversationId}`, {
    token: token || undefined,
  });
}

export function sendGenesisMessage(
  conversationId: string,
  requestData: {
    message_text: string;
    source_references?: string[];
    division_code?: string | null;
  },
  token?: string | null,
) {
  return request<GenesisConversationView>(
    `/genesis/conversations/${conversationId}/messages`,
    {
      method: "POST",
      token: token || undefined,
      body: JSON.stringify({
        message_text: requestData.message_text,
        source_references: requestData.source_references || [],
        division_code: requestData.division_code || null,
      }),
    },
  );
}

export function getGenesisArtifactVersions(conversationId: string, token?: string | null) {
  return request<GenesisArtifactVersionView[]>(
    `/genesis/conversations/${conversationId}/artifacts`,
    { token: token || undefined },
  );
}

export function listGenesisRequests(
  params?: { limit?: number; offset?: number },
  token?: string | null,
) {
  const limit = params?.limit ?? 50;
  const offset = params?.offset ?? 0;
  return request<GenesisPipelineView[]>(
    `/genesis/requests?limit=${limit}&offset=${offset}`,
    { token: token || undefined },
  );
}

export function getGenesisRequest(requestId: string, token?: string | null) {
  return request<GenesisPipelineView>(`/genesis/requests/${requestId}`, {
    token: token || undefined,
  });
}

export function submitGenesisRequest(
  payload: {
    strategy: "REUSE" | "EXTEND" | "CREATE";
    justification: string;
    source_references: string[];
    target?: { agent_id: string; version?: string } | null;
    base?: { agent_id: string; version?: string } | null;
    candidate?: Record<string, unknown> | null;
  },
  token?: string | null,
) {
  return request<GenesisPipelineView>("/genesis/requests", {
    method: "POST",
    token: token || undefined,
    body: JSON.stringify(payload),
  });
}

export function reviewGenesisRequest(
  requestId: string,
  payload: {
    gate: "BUSINESS" | "TECHNICAL";
    decision: "APPROVED" | "REJECTED";
    notes: string;
  },
  token?: string | null,
) {
  return request<GenesisPipelineView>(`/genesis/requests/${requestId}/reviews`, {
    method: "POST",
    token: token || undefined,
    body: JSON.stringify(payload),
  });
}

export function stageGenesisRequest(requestId: string, token?: string | null) {
  return request<GenesisPipelineView>(`/genesis/requests/${requestId}/stage`, {
    method: "POST",
    token: token || undefined,
  });
}

export function releaseGenesisRequest(requestId: string, token?: string | null) {
  return request<GenesisPipelineView>(`/genesis/requests/${requestId}/release`, {
    method: "POST",
    token: token || undefined,
  });
}

export function getSystemReadiness(token?: string | null) {
  return request<SystemReadinessReport>("/ready", { token: token || undefined });
}
