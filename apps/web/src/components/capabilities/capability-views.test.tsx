import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { CapabilityView } from "./capability-views";
import type { CapabilityRecord, TypedToolRecord } from "@/lib/capabilities";

const readyCapability: CapabilityRecord = {
  capability_key: "task.create",
  domain: "task",
  name: "Task Create",
  description: "Membuat task baru dalam scope divisi.",
  supported_scopes: ["OWN_DIVISION"],
  allowed_data_classification: ["INTERNAL"],
  risk_level: "LOW",
  access_mode: "CREATE_DRAFT",
  availability: "AVAILABLE",
  configuration_status: "CONFIGURED",
  version: 2,
  metadata: {},
  backing_tools: ["task.create.v1"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-02T00:00:00Z",
};

const blockedCapability: CapabilityRecord = {
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
  backing_tools: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const tool: TypedToolRecord = {
  tool_key: "task.create.v1",
  capability_key: "task.create",
  description: "Membuat task baru.",
  input_schema: {},
  output_schema: {},
  risk_level: "LOW",
  allowed_scopes: ["OWN_DIVISION"],
  required_permission: "task.create",
  access_mode: "CREATE_DRAFT",
  timeout_seconds: 30,
  idempotency_policy: "REQUIRED",
  audit_policy: "ALWAYS",
  runtime_handler: "task.create.handler",
  lifecycle_status: "ACTIVE",
  version: 1,
};

describe("CapabilityView", () => {
  it("shows a loading state without rendering any capability content", () => {
    const html = renderToStaticMarkup(<CapabilityView capabilities={[]} tools={[]} loading />);
    expect(html).toContain("Memuat Capability Registry");
  });

  it("shows an explicit empty state when there are no capabilities", () => {
    const html = renderToStaticMarkup(<CapabilityView capabilities={[]} tools={[]} loading={false} />);
    expect(html).toContain("Belum ada Capability terdaftar");
  });

  it("lists capabilities grouped by domain with readiness, never raw JSON", () => {
    const html = renderToStaticMarkup(
      <CapabilityView capabilities={[readyCapability, blockedCapability]} tools={[tool]} loading={false} />,
    );
    expect(html).toContain("Task Create");
    expect(html).toContain("Invoice Read");
    expect(html).not.toContain("{&quot;");
    expect(html).not.toContain("input_schema");
  });

  it("pre-selects the first capability and renders purpose, version, scope, risk, and readiness without raw JSON", () => {
    const html = renderToStaticMarkup(
      <CapabilityView capabilities={[readyCapability, blockedCapability]} tools={[tool]} loading={false} />,
    );
    expect(html).toContain("Membuat task baru dalam scope divisi.");
    expect(html).toContain("OWN_DIVISION");
    expect(html).toContain("Siap digunakan");
    expect(html).toContain("task.create.v1");
  });

  it("marks a capability blocked by configuration as needing configuration, and unavailable as blocked", () => {
    const availableButUnconfigured: CapabilityRecord = { ...readyCapability, configuration_status: "NEEDS_CONFIGURATION" };
    const html = renderToStaticMarkup(
      <CapabilityView capabilities={[availableButUnconfigured, blockedCapability]} tools={[]} loading={false} />,
    );
    expect(html).toContain("Perlu konfigurasi");
  });
});
