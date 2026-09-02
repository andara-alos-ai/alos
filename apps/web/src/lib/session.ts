import type { Principal } from "./types";

/**
 * Marker kept in React state so existing pages can keep their loading guards.
 * It is deliberately not a credential. Browser requests using this marker
 * authenticate through the HttpOnly cookie instead of an Authorization header.
 */
export const COOKIE_SESSION_MARKER = "__alos_cookie_session__";

export function readCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(/(?:^|;\s*)alos_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export function sessionInitials(principal: Principal): string {
  const role = principal.roles[0] || "ALOS";
  return role
    .split("_")
    .map((part) => part[0])
    .join("")
    .slice(0, 2);
}
