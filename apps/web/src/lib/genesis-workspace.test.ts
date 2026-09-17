import { describe, expect, it } from "vitest";

import { ApiError } from "./api-client";
import {
  canManageDraftAgent,
  canTestActiveAgent,
  citationSourceKindDescription,
  citationSourceKindLabel,
  classifyCitationSourceKind,
  conversationGroup,
  externalResearchPresentation,
  groupConversations,
  normalizeGenesisError,
  reliabilityPresentation,
  type GenesisConversation,
} from "./genesis-workspace";

const now = new Date("2026-09-09T12:00:00+07:00");
const conversation = (id: string, date: string): GenesisConversation => ({ conversation_id: id, workspace_id: "workspace", title: id, context_mode: "AUTO", status: "OPEN", created_at: date, updated_at: date });

describe("GENESIS workspace helpers", () => {
  it("groups conversation navigation by recency", () => {
    expect(conversationGroup("2026-09-09T08:00:00+07:00", now)).toBe("Today");
    expect(conversationGroup("2026-09-08T08:00:00+07:00", now)).toBe("Yesterday");
    expect(groupConversations([conversation("recent", "2026-09-05T08:00:00+07:00")], now)["Previous 7 Days"]).toHaveLength(1);
  });

  it("keeps active testing and draft mutation role-aware", () => {
    expect(canTestActiveAgent(["IT_LEAD"])).toBe(true);
    expect(canTestActiveAgent(["DIRECTOR"])).toBe(false);
    expect(canManageDraftAgent(["IT_LEAD"])).toBe(true);
    expect(canManageDraftAgent(["DIRECTOR"])).toBe(false);
  });

  it("normalizes inactive Agent and unauthorized context failures", () => {
    expect(normalizeGenesisError(new ApiError(403, "selected Agent is no longer ACTIVE or is outside the actor scope", "agent-ref"))).toMatchObject({ title: "Agent tidak dapat digunakan", correlationId: "agent-ref" });
    expect(normalizeGenesisError(new ApiError(403, "attached context is outside the actor scope", "context-ref"))).toMatchObject({ title: "Context gagal dilampirkan", correlationId: "context-ref" });
  });

  // M2-H02-FE-02 (Source Type UX): "Label konsisten tanpa mengekspos detail
  // sensitif" — the raw backend enum (INTERNAL_SOURCE/EXTERNAL_SOURCE) must
  // never leak through the presentation helpers.
  it("classifies the raw backend source_kind into a closed INTERNAL/EXTERNAL/UNKNOWN mapping", () => {
    expect(classifyCitationSourceKind("INTERNAL_SOURCE")).toBe("INTERNAL");
    expect(classifyCitationSourceKind("EXTERNAL_SOURCE")).toBe("EXTERNAL");
    expect(classifyCitationSourceKind("something else")).toBe("UNKNOWN");
    expect(classifyCitationSourceKind(undefined)).toBe("UNKNOWN");
  });

  it("labels each source kind without leaking the raw backend enum string", () => {
    expect(citationSourceKindLabel("INTERNAL")).toBe("Internal");
    expect(citationSourceKindLabel("EXTERNAL")).toBe("External");
    expect(citationSourceKindLabel("UNKNOWN")).not.toMatch(/INTERNAL_SOURCE|EXTERNAL_SOURCE/);
  });

  it("describes External sources as untrusted/without authority, matching governance rules", () => {
    expect(citationSourceKindDescription("EXTERNAL")).toMatch(/belum tepercaya/);
    expect(citationSourceKindDescription("INTERNAL")).not.toMatch(/belum tepercaya/);
  });

  // M2-H02-FE-03: Tampilkan blocked external source, unavailable evidence
  // dan needs-info state. User tidak melihat error teknis mentah dan tidak
  // diberi data authority palsu.
  it("presents a blocked external-research state when the org has not configured it", () => {
    const presentation = externalResearchPresentation("EXTERNAL_RESEARCH_NOT_CONFIGURED");
    expect(presentation.tone).toBe("blocked");
    expect(presentation.label).not.toMatch(/EXTERNAL_RESEARCH_NOT_CONFIGURED/);
    expect(presentation.message).toMatch(/belum dikonfigurasi/i);
  });

  it("presents an unavailable-evidence state distinctly from blocked", () => {
    const presentation = externalResearchPresentation("UNAVAILABLE");
    expect(presentation.tone).toBe("unavailable");
    expect(presentation.message).toMatch(/tidak tersedia/i);
  });

  it("presents a ready state for succeeded external research without granting it extra authority", () => {
    const presentation = externalResearchPresentation("SUCCEEDED");
    expect(presentation.tone).toBe("ready");
    expect(presentation.message).toMatch(/untrusted/);
  });

  it("falls back to a neutral, non-crashing presentation for an unrecognized external status", () => {
    const presentation = externalResearchPresentation("SOME_FUTURE_STATUS");
    expect(presentation.tone).toBe("neutral");
  });

  it("presents NEEDS_INFO reliability as a needs-info state, not a confident answer", () => {
    const presentation = reliabilityPresentation("NEEDS_INFO");
    expect(presentation.tone).toBe("blocked");
    expect(presentation.label).not.toBe("NEEDS_INFO");
    expect(presentation.message).toMatch(/informasi tambahan/i);
  });

  it("presents UNSUPPORTED reliability as an insufficient-evidence state", () => {
    const presentation = reliabilityPresentation("UNSUPPORTED");
    expect(presentation.tone).toBe("blocked");
    expect(presentation.message).toMatch(/belum cukup/i);
  });

  it("presents SUPPORTED reliability distinctly (ready tone) from NEEDS_INFO/UNSUPPORTED", () => {
    const presentation = reliabilityPresentation("SUPPORTED");
    expect(presentation.tone).toBe("ready");
  });
});
