export type SessionActor = {
  user_id: string;
  organization_id: string;
  roles: string[];
  division_codes: string[];
  workspace_ids: string[];
  issued_at: string;
  expires_at: string;
};

export type Workspace = {
  workspace_id: string;
  workspace_key: string;
  name: string;
  division_code: string | null;
  access_level: string;
};

export type Budget = {
  workspace_id: string;
  daily_request_limit: number;
  daily_output_token_limit: number;
  daily_cost_cap_usd: string;
};

export type Usage = {
  workspace_id: string;
  request_count: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: string;
};

export type ModelPolicy = {
  provider: string;
  model_light: string;
  model_standard: string;
  model_critical: string;
  max_output_tokens: number;
};

export type Run = {
  agent_run_id: string;
  agent_key: string;
  semantic_version: string;
  status: string;
  correlation_id: string;
  created_at: string;
  completed_at: string | null;
  provider: string | null;
  model: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  latency_milliseconds: number | null;
  estimated_cost_usd: string | null;
};

export type AuditEvent = {
  audit_event_id: string;
  action: string;
  reason: string;
  occurred_at: string;
};

export class ApiError extends Error {
  constructor(readonly status: number, readonly detail?: string) {
    super(`ALOS API request failed with ${status}`);
  }
}

export function apiErrorDetail(payload: unknown): string | undefined {
  if (
    payload !== null
    && typeof payload === "object"
    && "detail" in payload
    && typeof payload.detail === "string"
  ) {
    return payload.detail;
  }
  return undefined;
}

export function canChangeBudget(roles: string[]): boolean {
  return roles.includes("DIRECTOR") || roles.includes("IT_LEAD");
}

export function remainingBudget(budget: Budget, usage: Usage) {
  return {
    requests: Math.max(0, budget.daily_request_limit - usage.request_count),
    tokens: Math.max(0, budget.daily_output_token_limit - usage.output_tokens),
    cost: Math.max(0, Number(budget.daily_cost_cap_usd) - Number(usage.estimated_cost_usd)).toFixed(4),
  };
}

export function formatInteger(value: number): string {
  return new Intl.NumberFormat("id-ID").format(value);
}

export function formatCurrency(value: string): string {
  return new Intl.NumberFormat("en-US", {
    currency: "USD",
    maximumFractionDigits: 4,
    minimumFractionDigits: 2,
    style: "currency",
  }).format(Number(value));
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}
