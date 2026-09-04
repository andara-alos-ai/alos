import { describe, expect, it } from "vitest";

import {
  canReadReleaseRegistry,
  defaultTestForm,
  designerPayload,
  releaseErrorMessage,
  testCasePayload,
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
