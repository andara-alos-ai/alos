import type { Role } from "./types";

export type NavigationItem = {
  label: string;
  href: string;
  icon: "home" | "approval" | "agent";
  roles?: Role[];
};

const genesisRoles: Role[] = ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "IT_ADMIN", "AUDITOR"];

export const primaryNavigation: NavigationItem[] = [
  { label: "Genesis MVP1", href: "/", icon: "home" },
  { label: "Genesis Studio", href: "/genesis", icon: "agent", roles: genesisRoles },
  { label: "Agent Registry", href: "/agents", icon: "agent", roles: genesisRoles },
];

export const governanceNavigation: NavigationItem[] = [
  {
    label: "Review & Approval",
    href: "/approvals",
    icon: "approval",
    roles: ["DIRECTOR", "AI_EXECUTIVE", "DIVISION_HEAD", "IT_ADMIN", "AUDITOR"],
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
