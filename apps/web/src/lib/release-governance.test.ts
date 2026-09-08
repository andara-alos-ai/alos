import { describe, expect, it } from "vitest";

import {
  canReadReleaseRegistry,
  defaultTestForm,
  designerPayload,
  releaseErrorMessage,
  testCasePayload,
  latestRunByTestCase,
} from "./release-governance";

describe("H4 Release Governance helpers", () => {
  it("creates a prompt-only Designer payload without a model or credential", () => {
    expect(designerPayload({
      workspaceId: "workspace-1",
      requirement: "Buat Agent ringkasan properti internal yang hanya membaca data terdaftar.",
      agentKey: "",
      name: "",
      parentAgentKey: "",
    })).toEqual({
      workspace_id: "workspace-1",
      requirement: "Buat Agent ringkasan properti internal yang hanya membaca data terdaftar.",
    });
  });

  it("uses a blocked fixture by default for non-positive control tests", () => {
    const form = defaultTestForm("SECURITY");
    expect(testCasePayload(form)).toMatchObject({
      category: "SECURITY",
      expected_assertions: { status: "BLOCKED" },
      input_fixture: { requested_tool_keys: ["UNAUTHORIZED_TOOL"] },
    });
  });

  it("uses Evidence Checker's required claim and approved source search for a positive run", () => {
    const form = defaultTestForm("POSITIVE", "EVIDENCE_CHECKER");
    expect(testCasePayload(form)).toMatchObject({
      category: "POSITIVE",
      expected_assertions: { status: "SUCCEEDED" },
      input_fixture: {
        input: { claim: expect.any(String) },
        requested_tool_keys: ["SOURCE_REGISTRY_SEARCH"],
      },
    });
  });

  it("keeps the newest result when a corrected test has an older failed run", () => {
    const latest = latestRunByTestCase([
      {
        test_run_id: "new", test_case_id: "case-1", test_key: "DAILY_POSITIVE", category: "POSITIVE",
        status: "PASSED", agent_run_id: "run-new", correlation_id: "new-correlation", completed_at: "2026-09-08T10:13:30Z", actual_status: "SUCCEEDED", error_code: null,
      },
      {
        test_run_id: "old", test_case_id: "case-1", test_key: "DAILY_POSITIVE", category: "POSITIVE",
        status: "FAILED", agent_run_id: "run-old", correlation_id: "old-correlation", completed_at: "2026-09-08T09:31:16Z", actual_status: "BLOCKED", error_code: "TOOL_OR_INPUT_BLOCKED",
      },
    ]);
    expect(latest.get("case-1")?.status).toBe("PASSED");
  });

  it("keeps lifecycle failures distinct from generic UI errors", () => {
    expect(releaseErrorMessage("maker cannot act as checker")).toContain("Maker");
  });

  it("does not request Agent Registry data for H4-only reviewers", () => {
    expect(canReadReleaseRegistry(["QA_SECURITY"])).toBe(false);
    expect(canReadReleaseRegistry(["BUSINESS_REVIEWER"])).toBe(false);
    expect(canReadReleaseRegistry(["TECHNICAL_REVIEWER"])).toBe(false);
    expect(canReadReleaseRegistry(["DIRECTOR"])).toBe(false);
    expect(canReadReleaseRegistry(["IT_LEAD"])).toBe(true);
  });
});
