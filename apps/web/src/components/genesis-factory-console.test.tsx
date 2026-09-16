import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FactoryDetail, GenesisFactoryConsole } from "./genesis-factory-console";
import type { FactoryRequest } from "../lib/genesis-factory";
import type { SessionActor } from "../lib/governance";

const actor: SessionActor = {
  user_id: "00000000-0000-0000-0000-000000000001",
  organization_id: "00000000-0000-0000-0000-000000000002",
  roles: ["DIRECTOR"],
  division_codes: ["PROPERTY"],
  workspace_ids: ["00000000-0000-0000-0000-000000000003"],
  issued_at: "2026-09-09T00:00:00Z",
  expires_at: "2026-09-10T00:00:00Z",
};

const request: FactoryRequest = {
  factory_request_id: "f1",
  organization_id: "o1",
  workspace_id: "w1",
  division_id: null,
  project_id: null,
  tenant_id: null,
  requirement: "Check expired records and create a task.",
  source_type: "DIRECT",
  source_research_id: null,
  status: "NEEDS_CONFIGURATION",
  requirement_understanding: { objective: "Check records" },
  implementation_decision: {
    implementation_type: "AGENT",
    reason: "Requires reasoning.",
    required_capabilities: ["records.read"],
    required_data: ["records"],
    risk: "MEDIUM",
    human_gate_required: true,
  },
  dependency_resolution: {
    capability_keys: [],
    tool_keys: ["records.read"],
    permission_keys: [],
    readiness: "NEEDS_IMPLEMENTATION",
    missing_dependencies: [{ key: "records.read", reason: "not registered" }],
  },
  factory_proposal: { agent_contract: { agent_key: "EXPIRY_AGENT", name: "Expiry Agent" } },
  blockers: [],
  agent_contract_id: null,
  agent_version_id: null,
  release_change_request_id: null,
  requested_by_user_id: "u1",
  owner_user_id: null,
  reviewer_user_id: null,
  idempotency_key: "k1",
  correlation_id: "c1",
  last_error_code: null,
  created_at: "2026-01-01T00:00:00Z",
  analyzed_at: null,
  updated_at: "2026-01-01T00:00:00Z",
  generated_tests: [{
    factory_test_id: "t1",
    category: "POSITIVE",
    objective: "Verify read",
    expected_status: "PASS",
    execution_status: "NOT_RUN",
    agent_version_id: null,
    created_at: "2026-01-01T00:00:00Z",
  }],
};

describe("GENESIS Factory console", () => {
  it("shows a loading state before the backend contract resolves (no local authority fallback)", () => {
    const html = renderToStaticMarkup(<GenesisFactoryConsole actor={actor} />);
    expect(html).toContain("Memuat GENESIS Factory");
  });

  it("renders requirement, capability decision, and DRAFT-oriented fields from the backend contract", () => {
    const html = renderToStaticMarkup(<FactoryDetail request={request} />);
    expect(html).toContain("Check expired records and create a task.");
    expect(html).toContain("NEEDS CONFIGURATION");
    expect(html).toContain("AGENT");
    expect(html).toContain("records.read");
    expect(html).toContain("MEDIUM");
    expect(html).toContain("REQUIRED");
    expect(html).toContain("POSITIVE:NOT_RUN");
    expect(html).toContain("EXPIRY_AGENT");
  });

  it("shows an empty state instead of fabricating a request when none is selected", () => {
    const html = renderToStaticMarkup(<FactoryDetail request={undefined} />);
    expect(html).toContain("Pilih request untuk melihat detail.");
  });
});
