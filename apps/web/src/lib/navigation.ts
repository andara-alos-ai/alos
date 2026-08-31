import type { Role } from "./types";

export type NavigationItem = {
  label: string;
  href: string;
  icon: "home" | "work" | "approval" | "document" | "risk" | "agent" | "workflow" | "health" | "users" | "governance";
  roles?: Role[];
  divisions?: string[];
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
    label: "Lead & Reservasi",
    href: "/sales",
    icon: "workflow",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "SALES", "AUDITOR"],
    divisions: ["SALES_MARKETING"],
  },
  {
    label: "Payment & Rekonsiliasi",
    href: "/finance",
    icon: "approval",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "FINANCE", "AUDITOR"],
    divisions: ["FINANCE"],
  },
  {
    label: "Progres Property",
    href: "/property",
    icon: "workflow",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "PROPERTY", "AUDITOR"],
    divisions: ["PROPERTY"],
  },
  {
    label: "Izin & Kontrak",
    href: "/legal",
    icon: "document",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "LEGAL", "AUDITOR"],
    divisions: ["LEGAL"],
  },
  {
    label: "Rekrutmen & Personalia",
    href: "/hr",
    icon: "users",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "HR", "AUDITOR"],
    divisions: ["HR"],
  },
];

export const governanceNavigation: NavigationItem[] = [
  {
    label: "AI Executive Brief",
    href: "/executive",
    icon: "home",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "AUDITOR"],
  },
  {
    label: "Persetujuan",
    href: "/approvals",
    icon: "approval",
    roles: ["DIRECTOR", "DIVISION_HEAD", "FINANCE", "LEGAL", "AUDITOR"],
  },
  { label: "Dokumen & Bukti", href: "/documents", icon: "document", roles: businessRoles },
  { label: "Exception & CAPA", href: "/risks", icon: "risk", roles: businessRoles },
  {
    label: "Blueprint & Keputusan",
    href: "/governance",
    icon: "governance",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "IT_ADMIN", "AUDITOR"],
  },
  {
    label: "UAT & Go-Live",
    href: "/uat",
    icon: "workflow",
    roles: businessRoles,
  },
];

export const systemNavigation: NavigationItem[] = [
  {
    label: "Proyek & Status",
    href: "/projects",
    icon: "workflow",
    roles: ["DIRECTOR", "IT_ADMIN", "AUDITOR"],
  },
  {
    label: "Pengguna & Akses",
    href: "/users",
    icon: "users",
    roles: ["DIRECTOR", "IT_ADMIN", "AUDITOR"],
  },
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

export function visibleNavigation(
  items: NavigationItem[],
  roles: Role[],
  divisionCodes: string[] = [],
): NavigationItem[] {
  const organizationWide = roles.some((role) => (
    role === "DIRECTOR" || role === "AI_EXECUTIVE" || role === "AUDITOR"
  ));
  return items.filter((item) => {
    const roleAllowed = !item.roles || item.roles.some((role) => roles.includes(role));
    const divisionAllowed = (
      !item.divisions
      || organizationWide
      || item.divisions.some((division) => divisionCodes.includes(division))
    );
    return roleAllowed && divisionAllowed;
  });
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
