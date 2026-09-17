// Presentation-layer mirror of the backend Context Builder contract
// (alos.runtime.context, branch mvp2/ai/h2-context-manager — not yet merged to
// main and not yet exposed over HTTP). These types intentionally match the
// backend's fail-closed shape 1:1 so the UI never invents a status the
// backend did not send once the endpoint exists (M2-H02-BE-01/BE-02).
//
// IMPORTANT: as of this checklist item (M2-H02-FE-01), there is no live API
// route returning ContextBuildResult. Every consumer of this module MUST
// treat the absence of a response as ContextStatus.NOT_CONNECTED (a
// UI-only, additive state — never sent by the backend) and render the
// honest "belum terhubung" empty state, never a fabricated READY status.

export type ContextStatus = "READY" | "NEEDS_INFORMATION" | "BLOCKED";

// UI-only additions, never emitted by the backend:
// - NOT_CONNECTED: no backend response exists yet (endpoint not deployed).
// - LOADING: a request is in flight.
// - ERROR: the request reached (or tried to reach) the backend but failed
//   technically (network failure, 5xx, malformed response) — this is
//   distinct from BLOCKED (the backend explicitly, authoritatively denied
//   the request for a permission/policy reason). Conflating ERROR with
//   BLOCKED would either scare a user with a technical failure disguised
//   as "denied", or, worse, dress up a real permission denial as "just a
//   glitch, try again". Kept separate from the backend's own three
//   statuses so a real BLOCKED/NEEDS_INFORMATION/READY is never confused
//   with a client-side or transport failure (M2-H02-FE-04).
export type AraContextViewStatus = ContextStatus | "NOT_CONNECTED" | "LOADING" | "ERROR";

export type ContextErrorCode =
  | "EXECUTION_SCOPE_MISMATCH"
  | "ACTOR_ROLE_NOT_AUTHORIZED"
  | "CONTEXT_SCOPE_MISMATCH"
  | "DATA_CLASSIFICATION_EXCEEDED"
  | "UNAUTHORIZED_TOOL_CONTEXT"
  | "UNAUTHORIZED_CAPABILITY_CONTEXT"
  | "UNTRUSTED_AUTHORITY_CONTEXT"
  | "MANDATORY_CONTEXT_TOO_LARGE"
  | "EVIDENCE_CONTEXT_MISSING"
  | "RESEARCH_DOMAIN_REQUIRED"
  | "RESEARCH_DOMAIN_NOT_AUTHORIZED"
  | "RESEARCH_DOMAIN_SCOPE_MISMATCH"
  | "RESEARCH_SOURCE_NOT_AUTHORIZED"
  | "RESEARCH_CONTEXT_REQUIRED"
  | "RESEARCH_SOURCE_REQUIREMENTS_MISSING"
  | "INTERNAL_EVIDENCE_INSUFFICIENT"
  | "EXTERNAL_RESEARCH_NOT_AUTHORIZED"
  | "EXTERNAL_SOURCE_GOVERNANCE_REQUIRED"
  | "EXTERNAL_RESEARCH_RISK_EXCEEDED"
  | "EXTERNAL_RESEARCH_COST_EXCEEDED";

export type ContextTrust = "AUTHORITATIVE" | "INTERNAL_APPROVED" | "EXTERNAL_UNTRUSTED";

export type SourceKind = "INTERNAL" | "EXTERNAL";

export type ContextItemView = {
  key: string;
  purpose: string;
  trust: ContextTrust;
  estimatedTokens: number;
};

export type AraContextViewState = {
  status: AraContextViewStatus;
  bundleItems?: ContextItemView[];
  usedTokens?: number;
  tokenLimit?: number;
  omittedItemKeys?: string[];
  limitations?: string[];
  errorCode?: ContextErrorCode;
  reason?: string;
};

// Human-readable, non-technical presentation for each error code. Every
// string here must be understandable by a business user and must not leak
// backend/schema vocabulary (per M2-H02-FE-01 acceptance criteria: "Pesan
// dapat dipahami user").
const ERROR_PRESENTATION: Record<
  ContextErrorCode,
  { title: string; message: string; nextAction: string }
> = {
  EXECUTION_SCOPE_MISMATCH: {
    title: "Permintaan berada di luar scope Anda",
    message: "Permintaan ini menyentuh divisi/workspace/project yang bukan bagian dari akses Anda saat ini.",
    nextAction: "Pindah ke workspace yang sesuai atau hubungi IT Lead untuk perluasan scope.",
  },
  ACTOR_ROLE_NOT_AUTHORIZED: {
    title: "Role Anda belum diizinkan",
    message: "Role Anda saat ini tidak termasuk role yang diizinkan untuk permintaan ini.",
    nextAction: "Hubungi Division Lead/IT Lead bila Anda merasa seharusnya berwenang.",
  },
  CONTEXT_SCOPE_MISMATCH: {
    title: "Konteks di luar scope Anda",
    message: "Salah satu dokumen/data yang ingin dipakai berada di luar scope akses Anda.",
    nextAction: "Pilih dokumen/data lain yang berada dalam scope Anda.",
  },
  DATA_CLASSIFICATION_EXCEEDED: {
    title: "Klasifikasi data melebihi izin Anda",
    message: "Data yang dibutuhkan permintaan ini memiliki klasifikasi lebih tinggi dari izin akses Anda.",
    nextAction: "Ajukan permintaan akses tambahan kepada pemilik data/IT Lead.",
  },
  UNAUTHORIZED_TOOL_CONTEXT: {
    title: "Tool tidak diizinkan untuk Anda",
    message: "Permintaan ini membutuhkan tool yang belum diotorisasi untuk role Anda.",
    nextAction: "Hubungi IT Lead untuk otorisasi tool, atau gunakan permintaan lain.",
  },
  UNAUTHORIZED_CAPABILITY_CONTEXT: {
    title: "Capability tidak diizinkan untuk Anda",
    message: "Permintaan ini membutuhkan capability yang belum diotorisasi untuk role Anda.",
    nextAction: "Hubungi IT Lead untuk otorisasi capability, atau gunakan permintaan lain.",
  },
  UNTRUSTED_AUTHORITY_CONTEXT: {
    title: "Sumber ini tidak dapat memberi otoritas",
    message: "Sistem mendeteksi sumber tidak tepercaya mencoba dipakai sebagai dasar keputusan/otoritas.",
    nextAction: "Gunakan sumber internal resmi sebagai dasar keputusan.",
  },
  MANDATORY_CONTEXT_TOO_LARGE: {
    title: "Konteks wajib melebihi kapasitas",
    message: "Informasi wajib yang harus disertakan melebihi kapasitas pemrosesan saat ini.",
    nextAction: "Persempit permintaan Anda atau pisahkan menjadi beberapa permintaan lebih kecil.",
  },
  EVIDENCE_CONTEXT_MISSING: {
    title: "Evidence pendukung belum tersedia",
    message: "Permintaan ini membutuhkan evidence/citation yang belum tersedia.",
    nextAction: "Lengkapi dokumen/evidence pendukung terlebih dahulu.",
  },
  RESEARCH_DOMAIN_REQUIRED: {
    title: "Domain riset perlu dipilih",
    message: "Permintaan ini memerlukan domain R&D yang jelas sebelum dapat diproses.",
    nextAction: "Pilih salah satu dari empat domain R&D sebelum melanjutkan.",
  },
  RESEARCH_DOMAIN_NOT_AUTHORIZED: {
    title: "Domain riset ini tidak diizinkan untuk Anda",
    message: "Anda belum memiliki akses ke domain R&D yang diminta.",
    nextAction: "Hubungi Domain Owner untuk permintaan akses domain ini.",
  },
  RESEARCH_DOMAIN_SCOPE_MISMATCH: {
    title: "Domain riset di luar scope Anda",
    message: "Domain R&D ini berada di luar scope organisasi/workspace Anda saat ini.",
    nextAction: "Pindah ke workspace yang berwenang atas domain ini.",
  },
  RESEARCH_SOURCE_NOT_AUTHORIZED: {
    title: "Sumber riset ini tidak diizinkan",
    message: "Sumber yang diminta belum termasuk sumber yang disetujui organisasi.",
    nextAction: "Gunakan sumber dari daftar yang telah disetujui, atau ajukan penambahan sumber ke IT Lead.",
  },
  RESEARCH_CONTEXT_REQUIRED: {
    title: "Konteks riset belum lengkap",
    message: "Sistem memerlukan informasi riset tambahan sebelum dapat memutuskan sumber yang tepat.",
    nextAction: "Lengkapi informasi yang diminta pada form riset.",
  },
  RESEARCH_SOURCE_REQUIREMENTS_MISSING: {
    title: "Kebutuhan sumber belum ditentukan",
    message: "Permintaan riset ini belum menentukan jenis sumber (internal/external) yang dibutuhkan.",
    nextAction: "Tentukan jenis sumber yang dibutuhkan sebelum melanjutkan.",
  },
  INTERNAL_EVIDENCE_INSUFFICIENT: {
    title: "Evidence internal belum mencukupi",
    message: "Dokumen dan data internal yang tersedia belum cukup untuk menjawab permintaan ini.",
    nextAction: "Lengkapi evidence internal, atau ajukan riset eksternal bila diizinkan.",
  },
  EXTERNAL_RESEARCH_NOT_AUTHORIZED: {
    title: "Riset eksternal belum diizinkan",
    message: "Permintaan ini membutuhkan riset dari sumber eksternal, namun belum diotorisasi untuk Anda.",
    nextAction: "Ajukan persetujuan riset eksternal kepada Domain Owner/IT Lead.",
  },
  EXTERNAL_SOURCE_GOVERNANCE_REQUIRED: {
    title: "Sumber eksternal memerlukan persetujuan governance",
    message: "Sumber eksternal yang diminta memerlukan persetujuan governance sebelum dapat diakses.",
    nextAction: "Ajukan approval melalui alur governance yang berlaku.",
  },
  EXTERNAL_RESEARCH_RISK_EXCEEDED: {
    title: "Risiko riset eksternal melebihi batas",
    message: "Tingkat risiko riset eksternal ini melebihi batas yang diizinkan untuk permintaan Anda.",
    nextAction: "Persempit permintaan atau ajukan pengecualian risiko kepada IT Lead.",
  },
  EXTERNAL_RESEARCH_COST_EXCEEDED: {
    title: "Biaya riset eksternal melebihi batas",
    message: "Estimasi biaya riset eksternal ini melebihi batas anggaran yang diizinkan.",
    nextAction: "Persempit cakupan riset atau ajukan tambahan anggaran kepada Owner.",
  },
};

export function araContextErrorPresentation(code: ContextErrorCode) {
  return ERROR_PRESENTATION[code];
}

export function sourceKindLabel(kind: SourceKind): string {
  return kind === "INTERNAL" ? "Internal" : "External";
}

export function contextTrustLabel(trust: ContextTrust): string {
  switch (trust) {
    case "AUTHORITATIVE":
      return "Authoritative";
    case "INTERNAL_APPROVED":
      return "Internal (disetujui)";
    case "EXTERNAL_UNTRUSTED":
      return "External (untrusted)";
  }
}
