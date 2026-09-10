export type FactoryStatus =
  | "REQUEST"
  | "ANALYZING"
  | "DRAFT"
  | "NEEDS_CONFIGURATION"
  | "NEEDS_IMPLEMENTATION"
  | "BLOCKED"
  | "TESTING"
  | "TESTED"
  | "IN_REVIEW";

export type FactoryGeneratedTest = {
  factory_test_id: string;
  category: string;
  objective: string;
  expected_status: string;
  execution_status: string;
  agent_version_id: string | null;
  created_at: string;
};

export type FactoryRequest = {
  factory_request_id: string;
  organization_id: string;
  workspace_id: string;
  division_id: string | null;
  project_id: string | null;
  tenant_id: string | null;
  requirement: string;
  source_type: "DIRECT" | "RESEARCH";
  source_research_id: string | null;
  status: FactoryStatus;
  requirement_understanding: {
    objective: string;
    trigger_kind?: string;
    required_capabilities?: string[];
    required_data?: string[];
    desired_outputs?: string[];
    material_actions?: string[];
  } | null;
  implementation_decision: {
    implementation_type: string;
    components?: string[];
    reason: string;
    required_capabilities: string[];
    required_data: string[];
    risk: string;
    human_gate_required: boolean;
  } | null;
  dependency_resolution: {
    capability_keys: string[];
    tool_keys: string[];
    permission_keys: string[];
    readiness: string;
    missing_dependencies?: Array<{ key: string; reason: string }>;
  } | null;
  factory_proposal: {
    agent_contract?: { agent_key: string; name: string; semantic_version?: string } | null;
  } | null;
  blockers: Array<Record<string, unknown>>;
  agent_contract_id: string | null;
  agent_version_id: string | null;
  release_change_request_id: string | null;
  requested_by_user_id: string;
  owner_user_id: string | null;
  reviewer_user_id: string | null;
  idempotency_key: string;
  correlation_id: string;
  last_error_code: string | null;
  created_at: string;
  analyzed_at: string | null;
  updated_at: string;
  generated_tests: FactoryGeneratedTest[];
};

export type FactoryPage = {
  items: FactoryRequest[];
  limit: number;
  offset: number;
  has_more: boolean;
};

export function factoryStatusLabel(status: FactoryStatus): string {
  return status.replaceAll("_", " ");
}

export function factoryStatusTone(status: FactoryStatus): string {
  if (["REQUEST", "DRAFT", "TESTING", "IN_REVIEW"].includes(status)) return "info";
  if (["NEEDS_CONFIGURATION", "NEEDS_IMPLEMENTATION"].includes(status)) return "warning";
  if (["BLOCKED"].includes(status)) return "danger";
  if (["TESTED"].includes(status)) return "success";
  return "neutral";
}

export function factoryMissingDependencies(request: FactoryRequest): string[] {
  const resolution = request.dependency_resolution;
  if (!resolution) return [];
  const explicit = (resolution.missing_dependencies ?? []).map((item) => item.key);
  return [...new Set(explicit)].sort();
}
