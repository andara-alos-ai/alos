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

  // M2-H02-FE-05 (R&D Permission UX): allowed/denied/needs-approval and
  // domain/backlog permission surfacing.
  it("defaults every domain and the Production Backlog to a not-yet-verified badge when no backend permission is supplied", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain("Izin belum diverifikasi");
    expect(html).not.toContain("tone-allowed");
  });

  it("renders an explicit ALLOWED domain permission distinctly, without fabricating it for other domains", () => {
    const html = renderToStaticMarkup(
      createElement(RndWorkspace, {
        actor: mockActor,
        domainPermissions: [{ domain: "TECHNOLOGY", status: "ALLOWED" }],
      }),
    );
    expect(html).toContain("tone-allowed");
    expect(html).toContain("Diizinkan");
    expect(html).toContain("Izin belum diverifikasi");
  });

  it("renders a DENIED domain with an understandable message and disables its research entry points", () => {
    const html = renderToStaticMarkup(
      createElement(RndWorkspace, {
        actor: mockActor,
        domainPermissions: [{ domain: "TECHNOLOGY", status: "DENIED", reason: "ACTOR_ROLE_NOT_AUTHORIZED" }],
      }),
    );
    expect(html).toContain("Ditolak");
    expect(html).toContain('role="alert"');
    expect(html).toContain("tidak diizinkan untuk Anda");
    expect(html).not.toContain("ACTOR_ROLE_NOT_AUTHORIZED");
    expect(html).not.toContain('href="/genesis?mode=INTERNAL"');
  });

  it("renders a NEEDS_APPROVAL domain distinctly from DENIED and disables its research entry points", () => {
    const html = renderToStaticMarkup(
      createElement(RndWorkspace, {
        actor: mockActor,
        domainPermissions: [{ domain: "TECHNOLOGY", status: "NEEDS_APPROVAL" }],
      }),
    );
    expect(html).toContain("Perlu Persetujuan");
    expect(html).toContain("memerlukan persetujuan");
    expect(html).not.toContain('href="/genesis?mode=INTERNAL"');
  });

  it("shows a Production Backlog permission badge in the glossary, defaulting to not-yet-verified", () => {
    const html = renderToStaticMarkup(createElement(RndWorkspace, { actor: mockActor }));
    expect(html).toContain("Production Backlog");
    const glossaryIndex = html.indexOf("GLOSARIUM STATUS");
    expect(glossaryIndex).toBeGreaterThan(-1);
  });
});
