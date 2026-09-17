import { ApiError } from "./api-client";

export type ContextEntityType = "DOCUMENT" | "PROJECT" | "TASK" | "EVIDENCE" | "FINDING" | "REPORT";

export type GenesisConversation = {
  conversation_id: string;
  workspace_id: string | null;
  title: string | null;
  context_mode: "AUTO" | "INTERNAL" | "EXTERNAL" | "INTERNAL_AND_EXTERNAL";
  status: "OPEN" | "CLOSED";
  created_at: string;
  updated_at: string | null;
  last_message_preview?: string | null;
};

export type GenesisContextOption = {
  entity_type: ContextEntityType;
  entity_id: string;
  title: string;
  source_version: string | null;
  status: string;
  scope: string;
};

export type GenesisConversationContext = {
  conversation_context_id: string;
  conversation_id: string;
  entity_type: ContextEntityType;
  entity_id: string;
  source_version: string | null;
  created_at: string;
};

export type GenesisActiveAgent = {
  agent_key: string;
  name: string;
  semantic_version: string;
  purpose: string;
  risk_level: string;
  division_scope: string[];
  capability_keys: string[];
};

export type GenesisUiError = {
  title: string;
  reason: string;
  nextAction: string;
  correlationId: string | null;
};

export type ConversationGroup = "Today" | "Yesterday" | "Previous 7 Days" | "Older";

export function conversationGroup(value: string, now = new Date()): ConversationGroup {
  const updated = new Date(value);
  const start = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const item = new Date(updated.getFullYear(), updated.getMonth(), updated.getDate()).getTime();
  const days = Math.floor((start - item) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days <= 7) return "Previous 7 Days";
  return "Older";
}

export function groupConversations(items: GenesisConversation[], now = new Date()) {
  const groups: Record<ConversationGroup, GenesisConversation[]> = {
    Today: [], Yesterday: [], "Previous 7 Days": [], Older: [],
  };
  for (const item of items) groups[conversationGroup(item.updated_at ?? item.created_at, now)].push(item);
  return groups;
}

export function normalizeGenesisError(error: unknown): GenesisUiError {
  if (error instanceof ApiError) {
    const detail = safeDetail(error.detail);
    if (detail === "selected Agent is no longer ACTIVE or is outside the actor scope") {
      return { title: "Agent tidak dapat digunakan", reason: "Agent sudah tidak ACTIVE atau berada di luar scope Anda.", nextAction: "Pilih Agent ACTIVE lain atau buka Governance.", correlationId: error.correlationId };
    }
    if (detail.includes("context is outside") || detail.includes("outside the actor scope")) {
      return { title: "Context gagal dilampirkan", reason: "Entitas berada di luar scope akses Anda.", nextAction: "Pilih context lain yang tersedia pada picker.", correlationId: error.correlationId };
    }
    if (error.status === 409) return { title: "Data telah berubah", reason: detail, nextAction: "Daftar telah dimuat ulang. Periksa state terbaru lalu ulangi bila masih relevan.", correlationId: error.correlationId };
    if (error.status === 403) return { title: "Aksi tidak diizinkan", reason: detail, nextAction: "Pilih data dalam scope Anda atau gunakan role yang berwenang.", correlationId: error.correlationId };
    if (error.status === 422) return { title: "Input belum valid", reason: detail, nextAction: "Periksa field yang ditandai lalu kirim kembali.", correlationId: error.correlationId };
    if (error.status >= 500) return { title: "Layanan GENESIS tidak tersedia", reason: "Server tidak dapat menyelesaikan permintaan tanpa mengekspos detail internal.", nextAction: "Coba kembali; jika berulang berikan Reference ID kepada IT Lead.", correlationId: error.correlationId };
    return { title: "Permintaan tidak berhasil", reason: detail, nextAction: "Muat ulang data lalu coba kembali.", correlationId: error.correlationId };
  }
  return { title: "Permintaan tidak berhasil", reason: error instanceof Error ? error.message : "Kegagalan tidak dikenali.", nextAction: "Periksa input lalu coba kembali.", correlationId: null };
}

export function canTestActiveAgent(roles: string[], permissions: string[] = []): boolean {
  return roles.some((role) => ["IT_LEAD", "IT_ADMIN", "AI_ADMIN"].includes(role)) || permissions.some((permission) => ["IT_ADMIN", "AI_ADMIN"].includes(permission));
}

export function canManageDraftAgent(roles: string[]): boolean {
  return roles.includes("IT_LEAD");
}

export function contextHref(type: ContextEntityType): string {
  return { DOCUMENT: "/documents", PROJECT: "/projects", TASK: "/tasks", EVIDENCE: "/evidence", FINDING: "/findings", REPORT: "/reports" }[type];
}

function safeDetail(detail: string): string {
  return /stack|traceback|postgres|sql|database_url|password|secret|api[_ -]?key/i.test(detail)
    ? "Server menolak aksi tanpa mengekspos detail internal."
    : detail;
}

// M2-H02-FE-02 (Source Type UX): the backend already returns
// citation.source_kind as INTERNAL_SOURCE / EXTERNAL_SOURCE (see
// alos.ara.conversations.service._citations). This module classifies that
// raw backend value into a small, closed presentation so the UI shows a
// consistent Internal/External label without leaking backend enum
// vocabulary or any sensitive detail beyond the label itself.
export type CitationSourceKind = "INTERNAL" | "EXTERNAL" | "UNKNOWN";

export function classifyCitationSourceKind(rawSourceKind: unknown): CitationSourceKind {
  if (rawSourceKind === "INTERNAL_SOURCE") return "INTERNAL";
  if (rawSourceKind === "EXTERNAL_SOURCE") return "EXTERNAL";
  return "UNKNOWN";
}

export function citationSourceKindLabel(kind: CitationSourceKind): string {
  if (kind === "INTERNAL") return "Internal";
  if (kind === "EXTERNAL") return "External";
  return "Sumber tidak diketahui";
}

export function citationSourceKindDescription(kind: CitationSourceKind): string {
  if (kind === "INTERNAL") return "Dokumen/data internal ALOS dalam scope Anda.";
  if (kind === "EXTERNAL") return "Sumber eksternal — diperlakukan sebagai informasi belum tepercaya, tidak memberi authority.";
  return "Jenis sumber belum dapat ditentukan oleh sistem.";
}

// M2-H02-FE-03 (Safe Error UX): translate the backend's external-research
// status (alos.ara.conversations.service.ExternalStatus) into a tone +
// human message, so "blocked external source" / "unavailable evidence" are
// shown as an understandable state instead of a bare backend enum string.
export type ExternalResearchStatus =
  | "NOT_REQUESTED"
  | "EXTERNAL_RESEARCH_NOT_CONFIGURED"
  | "UNAVAILABLE"
  | "SUCCEEDED";

export type SafeStateTone = "neutral" | "blocked" | "unavailable" | "ready";

export function externalResearchPresentation(status: string): {
  tone: SafeStateTone;
  label: string;
  message: string;
} {
  switch (status as ExternalResearchStatus) {
    case "NOT_REQUESTED":
      return { tone: "neutral", label: "Tidak diminta", message: "Riset eksternal tidak diminta untuk permintaan ini." };
    case "SUCCEEDED":
      return { tone: "ready", label: "Tersedia", message: "Sumber eksternal berhasil diambil dan disertakan sebagai evidence untrusted." };
    case "EXTERNAL_RESEARCH_NOT_CONFIGURED":
      return {
        tone: "blocked",
        label: "Diblokir",
        message: "Riset eksternal belum dikonfigurasi untuk organisasi Anda. Sumber eksternal tidak dapat diakses saat ini.",
      };
    case "UNAVAILABLE":
      return {
        tone: "unavailable",
        label: "Tidak tersedia",
        message: "Penyedia riset eksternal sedang tidak tersedia. Coba lagi nanti, atau lanjutkan dengan sumber internal saja.",
      };
    default:
      return { tone: "neutral", label: "Tidak diketahui", message: "Status riset eksternal tidak dikenali." };
  }
}

// M2-H02-FE-03: translate the backend's reliability status
// (alos.ara.conversations.service.ReliabilityStatus) into a human message.
// "NEEDS_INFO" and "UNSUPPORTED" must read as an honest needs-info /
// unavailable-evidence state, never as a polished, confident answer.
export type ReliabilityStatus =
  | "SUPPORTED"
  | "PARTIALLY_SUPPORTED"
  | "UNSUPPORTED"
  | "AI_INFERRED"
  | "CONFLICTING_SOURCES"
  | "NEEDS_INFO";

export function reliabilityPresentation(status: string): {
  tone: SafeStateTone;
  label: string;
  message: string;
} {
  switch (status as ReliabilityStatus) {
    case "SUPPORTED":
      return { tone: "ready", label: "Didukung evidence", message: "Jawaban didukung oleh evidence internal yang diotorisasi." };
    case "PARTIALLY_SUPPORTED":
      return { tone: "unavailable", label: "Sebagian didukung", message: "Sebagian jawaban didukung evidence; sebagian lain masih memerlukan konfirmasi." };
    case "AI_INFERRED":
      return { tone: "unavailable", label: "Inferensi AI", message: "Jawaban merupakan inferensi AI, bukan kutipan langsung dari evidence yang tersedia." };
    case "CONFLICTING_SOURCES":
      return { tone: "unavailable", label: "Sumber bertentangan", message: "Ditemukan sumber yang saling bertentangan; jawaban ini belum dapat dijadikan keputusan final." };
    case "UNSUPPORTED":
      return {
        tone: "blocked",
        label: "Evidence belum cukup",
        message: "Sumber yang tersedia belum cukup untuk mendukung jawaban ini secara faktual.",
      };
    case "NEEDS_INFO":
      return {
        tone: "blocked",
        label: "Perlu informasi tambahan",
        message: "GENESIS memerlukan informasi tambahan sebelum dapat memberi jawaban terverifikasi.",
      };
    default:
      return { tone: "neutral", label: "Tidak diketahui", message: "Status keandalan jawaban tidak dikenali." };
  }
}
