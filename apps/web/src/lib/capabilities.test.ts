import { describe, expect, it } from "vitest";

import {
  capabilityReadiness,
  capabilityReadinessTone,
  capabilityRiskTone,
  formatCapabilityDomainLabel,
  formatCapabilityScopes,
  groupCapabilitiesByDomain,
  type CapabilityRecord,
} from "./capabilities";

function makeCapability(overrides: Partial<CapabilityRecord> = {}): CapabilityRecord {
  return {
    capability_key: "finance.invoice.read",
    domain: "finance",
    name: "Invoice Read",
    description: "Membaca data invoice untuk keperluan pelaporan.",
    supported_scopes: ["OWN_DIVISION"],
    allowed_data_classification: ["CONFIDENTIAL"],
    risk_level: "HIGH",
    access_mode: "READ",
    availability: "UNAVAILABLE",
    configuration_status: "NEEDS_CONFIGURATION",
    version: 1,
    metadata: {},
    backing_tools: ["finance.invoice.read.v1"],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("capabilityReadiness", () => {
  it("reports UNAVAILABLE first regardless of configuration status", () => {
    expect(
      capabilityReadiness({ availability: "UNAVAILABLE", configuration_status: "CONFIGURED" }),
    ).toBe("UNAVAILABLE");
  });

  it("reports NEEDS_CONFIGURATION when available but not configured", () => {
    expect(
      capabilityReadiness({ availability: "AVAILABLE", configuration_status: "NEEDS_CONFIGURATION" }),
    ).toBe("NEEDS_CONFIGURATION");
  });

  it("reports READY only when available and configured", () => {
    expect(
      capabilityReadiness({ availability: "AVAILABLE", configuration_status: "CONFIGURED" }),
    ).toBe("READY");
  });
});

describe("capability presentation helpers", () => {
  it("maps readiness to a safe visual tone", () => {
    expect(capabilityReadinessTone("READY")).toBe("success");
    expect(capabilityReadinessTone("NEEDS_CONFIGURATION")).toBe("warning");
    expect(capabilityReadinessTone("UNAVAILABLE")).toBe("danger");
  });

  it("maps risk level to a visual tone without downgrading HIGH/CRITICAL", () => {
    expect(capabilityRiskTone("LOW")).toBe("info");
    expect(capabilityRiskTone("MEDIUM")).toBe("info");
    expect(capabilityRiskTone("HIGH")).toBe("warning");
    expect(capabilityRiskTone("CRITICAL")).toBe("danger");
  });

  it("formats scopes and falls back to an explicit empty message", () => {
    expect(formatCapabilityScopes(makeCapability({ supported_scopes: ["OWN_DIVISION", "ALL"] }))).toBe(
      "OWN_DIVISION, ALL",
    );
    expect(formatCapabilityScopes(makeCapability({ supported_scopes: [] }))).toBe("Tidak ada scope");
  });

  it("formats domain labels for display", () => {
    expect(formatCapabilityDomainLabel("sales_marketing")).toBe("Sales Marketing");
    expect(formatCapabilityDomainLabel("finance")).toBe("Finance");
  });

  it("groups and sorts capabilities by domain, then by name", () => {
    const capabilities = [
      makeCapability({ capability_key: "task.create", domain: "task", name: "Task Create" }),
      makeCapability({ capability_key: "finance.invoice.read", domain: "finance", name: "Invoice Read" }),
      makeCapability({ capability_key: "finance.report.generate", domain: "finance", name: "Report Generate" }),
    ];

    const grouped = groupCapabilitiesByDomain(capabilities);

    expect(grouped.map((group) => group.domain)).toEqual(["finance", "task"]);
    expect(grouped[0].items.map((item) => item.name)).toEqual(["Invoice Read", "Report Generate"]);
  });
});
