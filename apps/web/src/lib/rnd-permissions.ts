// M2-H02-FE-05 (R&D Permission UX): presentation layer for R&D domain and
// Production Backlog access decisions. No live backend endpoint returns
// these permissions yet (mirrors the M2-H02-FE-01 situation for ARA
// context), so every consumer MUST default an unspecified domain/backlog
// to NOT_CONNECTED — a UI-only, honest "not yet verified" state — and must
// never render it as ALLOWED. When the backend contract lands, it is
// expected to send exactly one of ALLOWED / DENIED / NEEDS_APPROVAL per
// domain (and for backlog access); this module only maps that decision to
// a plain-language label and tone. It never invents its own allow/deny
// logic client-side.

export type RndPermissionStatus = "ALLOWED" | "DENIED" | "NEEDS_APPROVAL" | "NOT_CONNECTED";

export type RndDomainKeyLike = string;

export type RndDomainPermission = {
  domain: RndDomainKeyLike;
  status: RndPermissionStatus;
  reason?: string;
};

export type RndBacklogPermission = {
  status: RndPermissionStatus;
  reason?: string;
};

export function permissionForDomain(
  permissions: RndDomainPermission[] | undefined,
  domain: RndDomainKeyLike,
): RndPermissionStatus {
  return permissions?.find((item) => item.domain === domain)?.status ?? "NOT_CONNECTED";
}

export function rndPermissionLabel(status: RndPermissionStatus): string {
  switch (status) {
    case "ALLOWED":
      return "Diizinkan";
    case "DENIED":
      return "Ditolak";
    case "NEEDS_APPROVAL":
      return "Perlu Persetujuan";
    case "NOT_CONNECTED":
      return "Izin belum diverifikasi";
  }
}

export function rndPermissionTone(status: RndPermissionStatus): "allowed" | "denied" | "needs-approval" | "unverified" {
  switch (status) {
    case "ALLOWED":
      return "allowed";
    case "DENIED":
      return "denied";
    case "NEEDS_APPROVAL":
      return "needs-approval";
    case "NOT_CONNECTED":
      return "unverified";
  }
}

// Human, non-technical explanation of what the user can do next for a
// given status. ALLOWED/NOT_CONNECTED do not block any action, so they
// carry no "next step" instruction beyond the label itself.
export function rndPermissionNextAction(status: RndPermissionStatus): string | null {
  switch (status) {
    case "DENIED":
      return "Domain ini tidak diizinkan untuk Anda saat ini. Hubungi Domain Owner bila Anda merasa seharusnya berwenang.";
    case "NEEDS_APPROVAL":
      return "Tindakan ini memerlukan persetujuan Business/Domain Owner sebelum dapat digunakan.";
    case "NOT_CONNECTED":
      return "Izin akses domain ini belum dapat diverifikasi oleh backend; tindakan tetap tunduk pada pemeriksaan otorisasi saat dikirim.";
    case "ALLOWED":
      return null;
  }
}

// Whether an action (e.g. a research entry-point link) tied to this
// permission should be rendered as a usable action at all. NOT_CONNECTED
// keeps existing actions usable (real enforcement happens downstream, e.g.
// when GENESIS/ARA processes the request) — only an explicit backend
// DENIED or NEEDS_APPROVAL must suppress the action here, satisfying the
// AC "UI hanya menampilkan action yang dikirim backend".
export function isActionUsable(status: RndPermissionStatus): boolean {
  return status === "ALLOWED" || status === "NOT_CONNECTED";
}
