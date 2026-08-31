import type { Role } from "./types";

export const workspaces = [
  {
    id: "finance",
    code: "FINANCE",
    name: "Keuangan",
    agents: ["FRA", "BCA", "TIA"],
    focus: "Pembayaran, anggaran, invoice, pajak, dan rekonsiliasi",
    operationalHref: "/finance",
    capabilities: ["Permintaan pembayaran", "Kontrol anggaran", "Rekonsiliasi", "Invoice & pajak"],
    sourceKeys: ["E", "F", "G", "J", "K", "M"],
  },
  {
    id: "sales-marketing",
    code: "SALES_MARKETING",
    name: "Sales & Marketing",
    agents: ["SLA", "MCA_MKT", "CFA"],
    focus: "Lead, pipeline, follow-up pelanggan, dan konten",
    operationalHref: "/sales",
    capabilities: ["Intake lead", "Penugasan sales", "Customer follow-up", "Pipeline & reservasi"],
    sourceKeys: ["C", "D", "E", "F", "G", "K"],
  },
  {
    id: "property",
    code: "PROPERTY",
    name: "Property",
    agents: ["TPA"],
    focus: "Bukti lapangan, progres, inspeksi, dan defect",
    operationalHref: "/property",
    capabilities: ["Bukti lapangan", "Validasi progres", "KPI teknis", "Exception & CAPA"],
    sourceKeys: ["C", "E", "F", "G", "K"],
  },
  {
    id: "hr",
    code: "HR",
    name: "HR",
    agents: ["HRA", "HPA"],
    focus: "Rekrutmen, kehadiran, kompetensi, dan berkas personalia",
    operationalHref: "/hr",
    capabilities: ["Permintaan rekrutmen", "Screening", "Keputusan HR", "Checklist personalia"],
    sourceKeys: ["C", "E", "G", "H", "K"],
  },
  {
    id: "legal",
    code: "LEGAL",
    name: "Legal",
    agents: ["LPA", "CLA"],
    focus: "Izin, kontrak, klausul, kewajiban, dan legal hold",
    operationalHref: "/legal",
    capabilities: ["Intake izin & kontrak", "Review legal", "Verifikasi sumber", "Evidence keputusan"],
    sourceKeys: ["C", "F", "G", "J", "K"],
  },
  {
    id: "it",
    code: "IT",
    name: "IT",
    agents: [],
    focus: "Platform, runtime, integrasi, keamanan, observabilitas, dan Genesis",
    operationalHref: "/system-health",
    capabilities: ["Shared Agent Runtime", "Integrasi & keamanan", "Observability", "Genesis design-time"],
    sourceKeys: ["A", "I", "K", "N"],
  },
] as const;

const roleWorkspace: Partial<Record<Role, string>> = {
  SALES: "sales-marketing",
  FINANCE: "finance",
  PROPERTY: "property",
  HR: "hr",
  LEGAL: "legal",
  IT_ADMIN: "it",
};

const divisionWorkspace: Record<string, string> = {
  FINANCE: "finance",
  SALES_MARKETING: "sales-marketing",
  PROPERTY: "property",
  HR: "hr",
  LEGAL: "legal",
  IT: "it",
};

export function accessibleWorkspacesFor(roles: Role[], divisionCodes: string[]) {
  if (roles.some((role) => ["DIRECTOR", "AI_EXECUTIVE", "AUDITOR"].includes(role))) {
    return [...workspaces];
  }
  const workspaceIds = new Set<string>();
  roles.forEach((role) => {
    const workspace = roleWorkspace[role];
    if (workspace) workspaceIds.add(workspace);
  });
  divisionCodes.forEach((division) => {
    const workspace = divisionWorkspace[division];
    if (workspace) workspaceIds.add(workspace);
  });
  return workspaces.filter((workspace) => workspaceIds.has(workspace.id));
}

export const sharedAgents = ["MCA", "DIA", "SEA", "CEA", "KDA", "ARA", "CRA"] as const;

export const workflows = [
  { id: "FLOW-001", name: "Lead ke Reservasi", owner: "Sales & Marketing" },
  { id: "FLOW-002", name: "Permintaan Pembayaran", owner: "Keuangan" },
  { id: "FLOW-003", name: "Bukti Lapangan", owner: "Property" },
  { id: "FLOW-004", name: "Izin dan Kontrak", owner: "Legal" },
  { id: "FLOW-005", name: "Rekrutmen", owner: "HR" },
  { id: "FLOW-006", name: "Ringkasan Eksekutif", owner: "Direktur Utama" },
] as const;
