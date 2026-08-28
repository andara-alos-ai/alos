export const workspaces = [
  { id: "finance", name: "Keuangan", agents: ["FRA", "BCA", "TIA"], focus: "Pembayaran, anggaran, invoice, pajak, dan rekonsiliasi" },
  { id: "sales-marketing", name: "Sales & Marketing", agents: ["SLA", "MCA_MKT", "CFA"], focus: "Lead, pipeline, follow-up pelanggan, dan konten" },
  { id: "property", name: "Property", agents: ["TPA"], focus: "Bukti lapangan, progres, inspeksi, dan defect" },
  { id: "hr", name: "HR", agents: ["HRA", "HPA"], focus: "Rekrutmen, kehadiran, dan berkas personalia" },
  { id: "legal", name: "Legal", agents: ["LPA", "CLA"], focus: "Izin, kontrak, klausul, dan kewajiban" },
  { id: "it", name: "IT", agents: [], focus: "Platform, runtime, integrasi, keamanan, observabilitas, dan Genesis" },
] as const;

export const sharedAgents = ["MCA", "DIA", "SEA", "CEA", "KDA", "ARA", "CRA"] as const;

export const workflows = [
  { id: "FLOW-001", name: "Lead ke Reservasi", owner: "Sales & Marketing" },
  { id: "FLOW-002", name: "Permintaan Pembayaran", owner: "Keuangan" },
  { id: "FLOW-003", name: "Bukti Lapangan", owner: "Property" },
  { id: "FLOW-004", name: "Izin dan Kontrak", owner: "Legal" },
  { id: "FLOW-005", name: "Rekrutmen", owner: "HR" },
  { id: "FLOW-006", name: "Ringkasan Eksekutif", owner: "Direktur Utama" },
] as const;
