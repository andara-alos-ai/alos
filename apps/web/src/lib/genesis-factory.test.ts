import { describe, expect, it } from "vitest";

import {
  factoryMissingDependencies,
  factoryStatusLabel,
  type FactoryRequest,
} from "./genesis-factory";

const base: FactoryRequest = {
  factory_request_id: "f1",
  organization_id: "o1",
  workspace_id: "w1",
  division_id: null,
  project_id: null,
  tenant_id: null,
  requirement: "Check expired records and create a task.",
  source_type: "DIRECT",
  source_research_id: null,
  status: "DRAFT",
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
  generated_tests: [],
};

describe("genesis factory presentation", () => {
  it("renders status labels in human language", () => {
    expect(factoryStatusLabel("NEEDS_CONFIGURATION")).toBe("NEEDS CONFIGURATION");
  });

  it("surfaces missing dependencies from the authoritative resolution", () => {
    expect(factoryMissingDependencies(base)).toEqual(["records.read"]);
  });
});
