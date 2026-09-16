import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { createElement } from "react";

import { RndWorkspace, rndDomains, rndStatusConcepts, rndToBacklogFlow } from "./rnd-views";
import type { SessionActor } from "@/lib/governance";

describe("RndWorkspace Presentation Component", () => {
  const mockActor: SessionActor = {
    user_id: "test.analyst",
    organization_id: "org-1",
    roles: ["IT_LEAD"],
    division_codes: ["IT"],
    workspace_ids: ["ws-1"],
    issued_at: "2026-09-01T00:00:00Z",
    expires_at: "2026-12-31T23:59:59Z",
  };

  it("defines exactly the four business R&D domains", () => {
    expect(rndDomains.map((domain) => domain.key)).toEqual([
      "TECHNOLOGY",
      "PROPERTY_BUSINESS_MODEL",
      "CORPORATE_MANAGEMENT",
      "PROPERTY_MARKET",
    ]);
  });

  it("renders all four domain cards without raw schema", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain("R&amp;D Teknologi");
    expect(html).toContain("R&amp;D Model Bisnis Properti");
    expect(html).toContain("R&amp;D Manajemen Perusahaan");
    expect(html).toContain("R&amp;D Properti");
  });

  it("lets a user select a domain via an accessible, actionable control", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain('role="tablist"');
    expect(html).toContain('role="tab"');
    expect(html).toContain('aria-current="true"');
    // The first domain is preselected by default, so its status card is shown.
    expect(html).toContain("STATUS DOMAIN TERPILIH");
  });

  it("renders the Finding -> Production Backlog flow with governance separation", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    for (const step of rndToBacklogFlow) {
      expect(html).toContain(step.stage.replace("R&D", "R&amp;D"));
    }
    expect(html).toContain("Recommendation R&amp;D tidak dapat langsung mengubah production");
    expect(html).toContain("Production Backlog hanya terbentuk setelah review/approval");
  });

  it("defines exactly the four status concepts distinguishing Finding, Recommendation, Backlog Candidate, and Production Backlog", () => {
    expect(rndStatusConcepts.map((concept) => concept.key)).toEqual([
      "FINDING",
      "RECOMMENDATION",
      "BACKLOG_CANDIDATE",
      "PRODUCTION_BACKLOG",
    ]);
  });

  it("explains each status concept explicitly (what it is, its authority, and what it is not) without raw schema", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain("GLOSARIUM STATUS");
    for (const concept of rndStatusConcepts) {
      const escape = (value: string) => value.replace("R&D", "R&amp;D");
      expect(html).toContain(escape(concept.label));
      expect(html).toContain(escape(concept.whatItIs));
      expect(html).toContain(escape(concept.authority));
      expect(html).toContain(escape(concept.whatItIsNot));
    }
    expect(html).not.toContain("{&quot;");
    expect(html).not.toContain("schema");
  });

  it("shows an explicit not-yet-connected state per status instead of fabricating counts", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain("Belum terhubung");
    expect(html).toContain("M2-H01-BE-06");
  });

  it("distinguishes Internal and External research sources without exposing authority", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain("Internal");
    expect(html).toContain("External");
    expect(html).toContain("untrusted information");
  });

  it("provides an interactive entry point that opens GENESIS with the right source mode preselected", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain('href="/genesis?mode=INTERNAL"');
    expect(html).toContain('href="/genesis?mode=INTERNAL_AND_EXTERNAL"');
    expect(html).toContain("Authority ALOS");
    expect(html).toContain("Untrusted, tanpa authority");
  });

  it("states the baseline/no-mock-data limitation explicitly", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain("baseline H1");
  });
});
