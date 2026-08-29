import type { Role } from "./types";

export type NavigationItem = {
  label: string;
  href: string;
  icon: "home" | "work" | "approval" | "document" | "risk" | "agent" | "workflow" | "health";
  roles?: Role[];
};

const businessRoles: Role[] = [
  "DIRECTOR",
  "AI_EXECUTIVE",
  "DIVISION_HEAD",
  "SALES",
  "FINANCE",
  "PROPERTY",
  "HR",
  "LEGAL",
  "IT_ADMIN",
  "AUDITOR",
];

export const primaryNavigation: NavigationItem[] = [
  { label: "Ringkasan", href: "/", icon: "home", roles: businessRoles },
  { label: "Antrean Kerja", href: "/work-queue", icon: "work", roles: businessRoles },
  {
    label: "Persetujuan",
    href: "/approvals",
    icon: "approval",
    roles: ["DIRECTOR", "DIVISION_HEAD", "FINANCE", "LEGAL", "AUDITOR"],
  },
  { label: "Dokumen & Bukti", href: "/documents", icon: "document", roles: businessRoles },
  { label: "Exception & CAPA", href: "/risks", icon: "risk", roles: businessRoles },
];

export const systemNavigation: NavigationItem[] = [
  {
    label: "Agent Registry",
    href: "/agents",
    icon: "agent",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "IT_ADMIN", "AUDITOR"],
  },
  {
    label: "Workflow",
    href: "/workflows",
    icon: "workflow",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "IT_ADMIN", "AUDITOR"],
  },
  {
    label: "Kesehatan Sistem",
    href: "/system-health",
    icon: "health",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "IT_ADMIN", "AUDITOR"],
  },
];

export function visibleNavigation(items: NavigationItem[], roles: Role[]): NavigationItem[] {
  return items.filter((item) => !item.roles || item.roles.some((role) => roles.includes(role)));
}

export const roleLabels: Record<Role, string> = {
  DIRECTOR: "Direktur Utama",
  AI_EXECUTIVE: "AI Executive",
  DIVISION_HEAD: "Kepala Divisi",
  SALES: "Sales & Marketing",
  FINANCE: "Keuangan",
  PROPERTY: "Property",
  HR: "Human Resources",
  LEGAL: "Legal",
  IT_ADMIN: "Administrator IT",
  AUDITOR: "Auditor",
};
