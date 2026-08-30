import type { Role } from "./types";

export const divisions = [
  "FINANCE",
  "SALES_MARKETING",
  "PROPERTY",
  "HR",
  "LEGAL",
  "IT",
] as const;

export type DivisionCode = (typeof divisions)[number];

export const divisionLabels: Record<DivisionCode, string> = {
  FINANCE: "Keuangan",
  SALES_MARKETING: "Sales & Marketing",
  PROPERTY: "Property",
  HR: "Human Resources",
  LEGAL: "Legal",
  IT: "Information Technology",
};

const fixedRoleDivisions: Partial<Record<Role, DivisionCode>> = {
  SALES: "SALES_MARKETING",
  FINANCE: "FINANCE",
  PROPERTY: "PROPERTY",
  HR: "HR",
  LEGAL: "LEGAL",
  IT_ADMIN: "IT",
};

const organizationRoles: Role[] = ["DIRECTOR", "AI_EXECUTIVE", "AUDITOR"];

export function divisionForRole(role: Role, selected: DivisionCode): DivisionCode | null {
  if (organizationRoles.includes(role)) return null;
  return fixedRoleDivisions[role] || selected;
}

export function roleHasFixedDivision(role: Role): boolean {
  return Boolean(fixedRoleDivisions[role]) || organizationRoles.includes(role);
}

export function canReadUserDirectory(roles: Role[]): boolean {
  return roles.some((role) => ["DIRECTOR", "IT_ADMIN", "AUDITOR"].includes(role));
}

export function canManageIdentity(roles: Role[]): boolean {
  return roles.includes("IT_ADMIN");
}

export function validateAuditReason(reason: string): string | null {
  return reason.trim().length >= 8 ? null : "Alasan wajib diisi minimal 8 karakter.";
}

export function optionalDateTimeToIso(value: string): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}
