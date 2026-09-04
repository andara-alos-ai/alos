import type { AgentRecord } from "./agent-registry";

export const releaseStates = [
  "DRAFT",
  "TESTED",
  "IN_REVIEW",
  "APPROVED",
  "RELEASED",
  "ACTIVE",
  "SUSPENDED",
  "ROLLED_BACK",
] as const;

export type ReleaseState = (typeof releaseStates)[number] | "RETURNED" | "REJECTED";
export type TestCategory = "POSITIVE" | "NEGATIVE" | "REGRESSION" | "SECURITY" | "RECOVERY";
export type TestStatus = "PASSED" | "FAILED" | "BLOCKED" | "ERROR";
export type ReviewGate = "BUSINESS" | "TECHNICAL";
export type ReviewDecision = "APPROVED" | "REJECTED" | "RETURNED";

export type ReleaseRequest = {
  change_request_id: string;
  agent_key: string;
  agent_version_id: string;
  semantic_version: string;
  state: ReleaseState;
  maker_user_id: string;
  checker_user_id: string | null;
  approver_user_id: string | null;
};

export type TestCase = {
  test_case_id: string;
  agent_key: string;
  agent_version_id: string;
  test_key: string;
  category: TestCategory;
  input_fixture: Record<string, unknown>;
  expected_assertions: Record<string, unknown>;
};

export type TestRunEvidence = {
  test_run_id: string;
  test_case_id: string;
  test_key: string;
  category: TestCategory;
  status: TestStatus;
  agent_run_id: string | null;
  correlation_id: string;
  completed_at: string | null;
};

export type Review = {
  review_gate: ReviewGate;
  decision: ReviewDecision;
  notes: string;
  created_at: string;
};

export type LifecycleEvent = {
  event_sequence: number;
  from_state: ReleaseState | null;
  to_state: ReleaseState;
  reason: string;
  correlation_id: string;
  created_at: string;
};

export type ReleaseRequestDetail = ReleaseRequest & {
  requirement: string;
  test_cases: TestCase[];
  test_runs: TestRunEvidence[];
  reviews: Review[];
  lifecycle_events: LifecycleEvent[];
  kill_switch_active: boolean;
  rollback_targets: string[];
};

export type DesignerResult = {
  blueprint: { requirement: string; agent_key: string; risk_level: string; approval_required: boolean };
  draft: { agent_key: string; semantic_version: string; lifecycle_status: string; correlation_id: string };
};

export const releaseTestCategories: TestCategory[] = ["POSITIVE", "NEGATIVE", "REGRESSION", "SECURITY", "RECOVERY"];

export function canMakeRelease(roles: string[]): boolean {
  return roles.some((role) => ["DIRECTOR", "DIVISION_OWNER", "IT_LEAD"].includes(role));
}

/**
 * Match the backend Agent Registry read authority. H4 reviewers must be able
 * to load release evidence without receiving this broader Registry access.
 */
export function canReadReleaseRegistry(roles: string[]): boolean {
  return canMakeRelease(roles);
}

export function canDesignAgent(roles: string[]): boolean {
  return roles.includes("IT_LEAD");
}

export function canCheckRelease(roles: string[]): boolean {
  return roles.some((role) => ["QA_SECURITY", "TECHNICAL_REVIEWER"].includes(role));
}

export function canReviewGate(roles: string[]): ReviewGate | null {
  if (roles.includes("BUSINESS_REVIEWER")) return "BUSINESS";
  if (roles.includes("TECHNICAL_REVIEWER")) return "TECHNICAL";
  return null;
}

export function canApproveRelease(roles: string[]): boolean {
  return roles.includes("DIRECTOR");
}

export function canOperateKillSwitch(roles: string[]): boolean {
  return roles.some((role) => ["DIRECTOR", "IT_LEAD"].includes(role));
}

export function draftAgents(agents: AgentRecord[]): AgentRecord[] {
  return agents.filter((agent) => agent.versions[0]?.lifecycle_status === "DRAFT");
}

export function defaultTestForm(category: TestCategory = "POSITIVE") {
  const blocked = category !== "POSITIVE";
  return {
    category,
    testKey: `H4_${category}_FIXTURE`,
    fixture: JSON.stringify(
      blocked
        ? { input: { query: `${category.toLowerCase()} fixture` }, requested_tool_keys: ["UNAUTHORIZED_TOOL"] }
        : { input: { query: "Buat ringkasan singkat untuk uji positif H4." } },
      null,
      2,
    ),
    expectedStatus: blocked ? "BLOCKED" : "SUCCEEDED",
  };
}

export function testCasePayload(form: { testKey: string; category: TestCategory; fixture: string; expectedStatus: string }) {
  const testKey = form.testKey.trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9_]{2,79}$/.test(testKey)) {
    throw new Error("Test key harus memakai huruf kapital, angka, atau underscore (3–80 karakter).");
  }
  if (!["SUCCEEDED", "FAILED", "BLOCKED"].includes(form.expectedStatus)) {
    throw new Error("Expected status tidak valid.");
  }
  return {
    test_key: testKey,
    category: form.category,
    input_fixture: parseJsonObject(form.fixture, "Fixture test"),
    expected_assertions: { status: form.expectedStatus },
  };
}

export function designerPayload(form: { workspaceId: string; requirement: string; agentKey: string; name: string; parentAgentKey: string }) {
  const requirement = form.requirement.trim();
  if (requirement.length < 20) throw new Error("Requirement minimal 20 karakter.");
  const agentKey = form.agentKey.trim().toUpperCase();
  if (agentKey && !/^[A-Z][A-Z0-9_]{2,79}$/.test(agentKey)) {
    throw new Error("Agent key opsional harus memakai huruf kapital, angka, atau underscore.");
  }
  return {
    workspace_id: form.workspaceId,
    requirement,
    ...(agentKey ? { agent_key: agentKey } : {}),
    ...(form.name.trim() ? { name: form.name.trim() } : {}),
    ...(form.parentAgentKey ? { parent_agent_key: form.parentAgentKey } : {}),
  };
}

export function releaseErrorMessage(detail?: string): string {
  const messages: Record<string, string> = {
    "a DRAFT Agent Contract version is required": "Pilih Agent dengan versi DRAFT untuk memulai release request.",
    "maker cannot act as checker": "Maker tidak dapat menjadi Checker pada request yang sama.",
    "positive, negative, regression, security, and recovery tests must pass": "Lima kategori test wajib lulus sebelum review.",
    "a successful Agent Run is required before review": "Minimal satu Agent Run sukses diperlukan sebelum review.",
    "business and technical review approvals are required": "Approval Business dan Technical wajib tersedia.",
    "only the recorded approver can release an approved request": "Hanya Approver yang tercatat yang dapat release.",
    "only the recorded approver can activate a released request": "Hanya Approver yang tercatat yang dapat mengaktifkan Agent.",
    "kill switch is active": "Kill switch aktif; Agent tidak dapat diaktifkan.",
    "clear the active kill switch before rollback": "Bersihkan kill switch secara eksplisit sebelum rollback.",
  };
  return messages[detail ?? ""] ?? "Aksi H4 ditolak oleh kontrol lifecycle atau separation of duties.";
}

export function latestRunByTestCase(runs: TestRunEvidence[]): Map<string, TestRunEvidence> {
  return new Map(runs.map((run) => [run.test_case_id, run]));
}

function parseJsonObject(value: string, label: string): Record<string, unknown> {
  try {
    const parsed: unknown = JSON.parse(value);
    if (parsed === null || Array.isArray(parsed) || typeof parsed !== "object") throw new Error();
    return parsed as Record<string, unknown>;
  } catch {
    throw new Error(`${label} harus berupa objek JSON yang valid.`);
  }
}
