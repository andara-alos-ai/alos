import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { createElement } from "react";

import { AraContextPanel } from "./ara-context-panel";
import type { AraContextViewState } from "@/lib/ara-context";

// M2-H02-FE-01 (Tampilkan loading, permission denied, source/evidence dan
// context state) + M2-H02-FE-04 (Test rendering state
// success/denied/loading/error — tidak ada state ACTIVE/authorized yang
// dibuat lokal). Every state this component can render is exercised here,
// including the UI-only states (LOADING, NOT_CONNECTED, ERROR) that must
// never be confused with a backend-authorized READY state.
describe("AraContextPanel", () => {
  it("renders the LOADING state without claiming any backend result", () => {
    const state: AraContextViewState = { status: "LOADING" };
    const html = renderToStaticMarkup(createElement(AraContextPanel, { state }));
    expect(html).toContain("Memuat konteks");
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-busy="true"');
    expect(html).not.toContain("Konteks siap digunakan");
  });

  it("renders the NOT_CONNECTED state honestly, referencing the pending backend items", () => {
    const state: AraContextViewState = { status: "NOT_CONNECTED" };
    const html = renderToStaticMarkup(createElement(AraContextPanel, { state }));
    expect(html).toContain("Belum terhubung ke Context Builder");
    expect(html).toContain("M2-H02-BE-01");
    expect(html).toContain("M2-H02-BE-02");
    expect(html).not.toContain("Konteks siap digunakan");
  });

  it("renders a BLOCKED (permission denied) state with an understandable, non-technical message", () => {
    const state: AraContextViewState = {
      status: "BLOCKED",
      errorCode: "ACTOR_ROLE_NOT_AUTHORIZED",
      reason: "actor role MEMBER is not in allowed roles",
    };
    const html = renderToStaticMarkup(createElement(AraContextPanel, { state }));
    expect(html).toContain('role="alert"');
    expect(html).toContain("Role Anda belum diizinkan");
    expect(html).toContain("Langkah berikutnya:");
    expect(html).not.toContain("ACTOR_ROLE_NOT_AUTHORIZED");
  });

  it("renders a NEEDS_INFORMATION state distinctly from BLOCKED", () => {
    const state: AraContextViewState = {
      status: "NEEDS_INFORMATION",
      errorCode: "RESEARCH_DOMAIN_REQUIRED",
    };
    const html = renderToStaticMarkup(createElement(AraContextPanel, { state }));
    expect(html).toContain("Domain riset perlu dipilih");
    expect(html).toContain("needs-info");
    expect(html).not.toContain("class=\"alos-ara-ctx-panel denied\"");
  });

  it("renders a READY state with source trust badges, distinguishing INTERNAL_APPROVED and EXTERNAL_UNTRUSTED", () => {
    const state: AraContextViewState = {
      status: "READY",
      usedTokens: 1200,
      tokenLimit: 8000,
      bundleItems: [
        { key: "doc-1", purpose: "SOP internal terkait proyek", trust: "INTERNAL_APPROVED", estimatedTokens: 400 },
        { key: "src-1", purpose: "Artikel pasar dari sumber resmi eksternal", trust: "EXTERNAL_UNTRUSTED", estimatedTokens: 800 },
      ],
      omittedItemKeys: ["doc-2"],
      limitations: ["Satu dokumen tidak disertakan karena melebihi kapasitas."],
    };
    const html = renderToStaticMarkup(createElement(AraContextPanel, { state }));
    expect(html).toContain("Konteks siap digunakan");
    expect(html).toContain("1.200 / 8.000 token");
    expect(html).toContain("Internal (disetujui)");
    expect(html).toContain("External (untrusted)");
    expect(html).toContain("1 item konteks tidak disertakan");
    expect(html).toContain("Satu dokumen tidak disertakan karena melebihi kapasitas.");
  });

  it("renders a READY state with no items as an honest empty state, not fabricated context", () => {
    const state: AraContextViewState = { status: "READY", usedTokens: 0, tokenLimit: 8000, bundleItems: [] };
    const html = renderToStaticMarkup(createElement(AraContextPanel, { state }));
    expect(html).toContain("Belum ada item konteks yang dipilih");
  });

  // M2-H02-FE-04 (Context Contract Tests): a technical/transport ERROR
  // (network failure, 5xx) must render distinctly from a BLOCKED
  // (authoritative permission denial) state, and must never expose the raw
  // technical failure message nor fabricate an ACTIVE/authorized READY
  // state.
  it("renders an ERROR (technical failure) state distinctly from BLOCKED, without leaking raw failure detail", () => {
    const state: AraContextViewState = { status: "ERROR", reason: "TypeError: Failed to fetch at internal endpoint 10.0.0.4:8080" };
    const html = renderToStaticMarkup(createElement(AraContextPanel, { state }));
    expect(html).toContain('role="alert"');
    expect(html).toContain("Konteks tidak dapat dimuat saat ini");
    expect(html).toContain("bukan penolakan izin");
    expect(html).not.toContain("class=\"alos-ara-ctx-panel denied\"");
    expect(html).not.toContain("TypeError");
    expect(html).not.toContain("10.0.0.4");
  });

  // Documents the full contract surface required by M2-H02-FE-04: every
  // state the panel supports is exercised somewhere in this file, and no
  // test exercises a locally-fabricated ACTIVE/authorized state — READY is
  // only ever reached via an explicit backend-shaped state object, never a
  // default.
  it("covers the full success/denied/loading/error state contract required by M2-H02-FE-04", () => {
    const statuses: AraContextViewState["status"][] = [
      "LOADING",
      "NOT_CONNECTED",
      "BLOCKED",
      "NEEDS_INFORMATION",
      "ERROR",
      "READY",
    ];
    for (const status of statuses) {
      const state = { status } as AraContextViewState;
      const html = renderToStaticMarkup(createElement(AraContextPanel, { state }));
      if (status !== "READY") {
        expect(html).not.toContain("Konteks siap digunakan");
      }
    }
  });
});
