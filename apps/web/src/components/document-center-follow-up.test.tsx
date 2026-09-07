import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { GenesisFollowUpFeedback, GenesisFollowUpMessage } from "./document-center";
import type { GenesisFollowUpFailure, GenesisHistoryMessage } from "../lib/genesis-follow-up";

function message(actorKind: "HUMAN" | "SYSTEM", content: string): GenesisHistoryMessage {
  return {
    message_id: `${actorKind}-1`,
    conversation_id: "conversation-1",
    actor_kind: actorKind,
    actor_user_id: actorKind === "HUMAN" ? "director-1" : null,
    system_actor: actorKind === "SYSTEM" ? "GENESIS" : null,
    content,
    created_at: "2026-09-07T00:00:00Z",
  };
}

function failure(status: "BLOCKED" | "FAILED"): GenesisFollowUpFailure {
  return {
    status,
    correlation_id: "correlation-1",
    error: {
      code: status === "BLOCKED" ? "CONTEXT_LIMIT_EXCEEDED" : "MODEL_ANSWER_INVALID",
      message: status === "BLOCKED" ? "Konteks terlalu besar." : "Jawaban tidak valid.",
    },
  };
}

describe("Genesis follow-up view", () => {
  it("renders restored Director and Genesis bubbles with citations", () => {
    const director = renderToStaticMarkup(
      <GenesisFollowUpMessage actorInitial="D" message={message("HUMAN", "Prioritaskan owner.")} />,
    );
    const genesis = renderToStaticMarkup(
      <GenesisFollowUpMessage actorInitial="D" message={message("SYSTEM", "## Jawaban ringkas\nOwner belum ada. [Sumber L1-L1]")} />,
    );

    expect(director).toContain("Direktur Utama");
    expect(director).toContain("Prioritaskan owner.");
    expect(genesis).toContain("GENESIS");
    expect(genesis).toContain("alos-genesis-citation");
  });

  it("renders loading and distinguishes BLOCKED from FAILED", () => {
    const loading = renderToStaticMarkup(<GenesisFollowUpFeedback failure={null} sending />);
    const blocked = renderToStaticMarkup(
      <GenesisFollowUpFeedback failure={failure("BLOCKED")} sending={false} />,
    );
    const failed = renderToStaticMarkup(
      <GenesisFollowUpFeedback failure={failure("FAILED")} sending={false} />,
    );

    expect(loading).toContain("Genesis sedang menganalisis…");
    expect(blocked).toContain("blocked");
    expect(blocked).toContain("Genesis belum dapat menjawab");
    expect(failed).toContain("failed");
    expect(failed).toContain("Balasan Genesis gagal");
  });
});
