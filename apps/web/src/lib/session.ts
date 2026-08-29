import type { Principal } from "./types";

const tokenStorageKey = "alos.pilot.access-token";

export function readSessionToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(tokenStorageKey);
}

export function storeSessionToken(token: string): void {
  window.sessionStorage.setItem(tokenStorageKey, token);
}

export function clearSessionToken(): void {
  window.sessionStorage.removeItem(tokenStorageKey);
}

export function sessionInitials(principal: Principal): string {
  const role = principal.roles[0] || "ALOS";
  return role
    .split("_")
    .map((part) => part[0])
    .join("")
    .slice(0, 2);
}
