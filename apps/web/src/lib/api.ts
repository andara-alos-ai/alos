import type {
  ApprovalRecord,
  CapaRecord,
  DocumentRecord,
  ExceptionRecord,
  OperationsHealth,
  PageResult,
  Principal,
  Project,
  ProjectAssignment,
  Reminder,
  Role,
  RoleAssignment,
  UserDirectoryPage,
  UserDirectoryRecord,
  UserStatus,
  WorkItem,
  WorkQueueScope,
} from "./types";

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
  if (options.token) headers.set("Authorization", `Bearer ${options.token}`);

  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...options,
      headers,
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

export function issuePilotToken(input: {
  user_id: string;
  organization_id: string;
  roles: Role[];
  division_codes: string[];
  project_ids: string[];
}) {
  return request<{ access_token: string; token_type: string; expires_in: number }>(
    "/auth/local-token",
    { method: "POST", body: JSON.stringify(input) },
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

export function getPrincipal(token: string) {
  return request<Principal>("/auth/me", { token });
}

export function getProjects(token: string) {
  return request<Project[]>("/projects", { token });
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

function queryPath(path: string, projectId: string | null, pageSize = 50): string {
  const parameters = new URLSearchParams({ page: "1", page_size: String(pageSize) });
  if (projectId) parameters.set("project_id", projectId);
  return `${path}?${parameters}`;
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
