import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GenesisMessage } from "./genesis-chat";

// M2-H02-FE-02 (Source Type UX): "Label konsisten tanpa mengekspos detail
// sensitif" — the citation list must render a consistent Internal/External
// badge and must never leak the raw backend enum (INTERNAL_SOURCE /
// EXTERNAL_SOURCE) into the rendered HTML.
function baseMessage(citations: Array<Record<string, unknown>>) {
  return {
    message_id: "msg-1",
    actor_kind: "SYSTEM" as const,
    content: "Jawaban GENESIS",
    status: "COMPLETED",
    structured_content: {},
    citations,
    tool_activity: [],
    created_at: "2026-09-17T08:00:00Z",
  };
}

describe("GenesisMessage citation source-kind badges", () => {
  it("renders an Internal badge for INTERNAL_SOURCE citations without leaking the raw backend string", () => {
    const message = baseMessage([{ source_kind: "INTERNAL_SOURCE", title: "SOP Internal" }]);
    const html = renderToStaticMarkup(<GenesisMessage message={message} />);
    expect(html).toContain("Internal");
    expect(html).toContain("kind-internal");
    expect(html).not.toContain("INTERNAL_SOURCE");
  });

  it("renders an External badge for EXTERNAL_SOURCE citations without leaking the raw backend string", () => {
    const message = baseMessage([{ source_kind: "EXTERNAL_SOURCE", title: "Artikel Pasar" }]);
    const html = renderToStaticMarkup(<GenesisMessage message={message} />);
    expect(html).toContain("External");
    expect(html).toContain("kind-external");
    expect(html).not.toContain("EXTERNAL_SOURCE");
  });

  it("renders both Internal and External badges distinctly when a message has mixed citations", () => {
    const message = baseMessage([
      { source_kind: "INTERNAL_SOURCE", title: "SOP Internal" },
      { source_kind: "EXTERNAL_SOURCE", title: "Artikel Pasar" },
    ]);
    const html = renderToStaticMarkup(<GenesisMessage message={message} />);
    expect(html).toContain("kind-internal");
    expect(html).toContain("kind-external");
  });

  it("falls back to an Unknown badge for an unrecognized source_kind instead of guessing", () => {
    const message = baseMessage([{ source_kind: "SOMETHING_ELSE", title: "Ambigu" }]);
    const html = renderToStaticMarkup(<GenesisMessage message={message} />);
    expect(html).toContain("kind-unknown");
    expect(html).toContain("Sumber tidak diketahui");
  });
});

// M2-H02-FE-03 (Safe Error UX): a NEEDS_INFO/UNSUPPORTED reliability must
// render as an honest, alert-toned state — never as a confident SUPPORTED
// answer — and must never leak the raw backend enum value to the user.
describe("GenesisMessage reliability badge", () => {
  function messageWithReliability(reliability: string) {
    return {
      message_id: "msg-2",
      actor_kind: "SYSTEM" as const,
      content: "Jawaban GENESIS",
      status: "COMPLETED",
      structured_content: { response: { answer: "Jawaban GENESIS", reliability } },
      citations: [],
      tool_activity: [],
      created_at: "2026-09-17T08:00:00Z",
    };
  }

  it("renders NEEDS_INFO as a blocked-tone, human-readable badge, not the raw enum", () => {
    const html = renderToStaticMarkup(<GenesisMessage message={messageWithReliability("NEEDS_INFO")} />);
    expect(html).toContain("tone-blocked");
    expect(html).toContain("Perlu informasi tambahan");
    expect(html).not.toContain(">NEEDS_INFO<");
  });

  it("renders UNSUPPORTED as a blocked-tone badge distinct from SUPPORTED", () => {
    const html = renderToStaticMarkup(<GenesisMessage message={messageWithReliability("UNSUPPORTED")} />);
    expect(html).toContain("tone-blocked");
    expect(html).toContain("Evidence belum cukup");
  });

  it("renders SUPPORTED as a ready-tone badge", () => {
    const html = renderToStaticMarkup(<GenesisMessage message={messageWithReliability("SUPPORTED")} />);
    expect(html).toContain("tone-ready");
    expect(html).toContain("Didukung evidence");
  });
});
