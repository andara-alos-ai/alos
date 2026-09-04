export const dashboardModules = {
  divisions: {
    title: "Divisi",
    description: "Pantau kesehatan dan prioritas setiap divisi saat data operasional telah terhubung.",
  },
  projects: {
    title: "Proyek",
    description: "Kelola portofolio, milestone, risiko, dan owner proyek dari satu ruang kerja.",
  },
  tasks: {
    title: "Tugas",
    description: "Pantau pekerjaan, tenggat, dan proses review yang menjadi tanggung jawab tim.",
  },
  approvals: {
    title: "Approval",
    description: "Tinjau permintaan persetujuan berdasarkan peran, bukti, dan audit yang berlaku.",
  },
  documents: {
    title: "Dokumen",
    description: "Kelola dokumen terdaftar dengan klasifikasi, pemilik, versi, dan akses yang terkontrol.",
  },
  reports: {
    title: "Laporan",
    description: "Buat dan akses laporan dari sumber data yang telah diverifikasi.",
  },
  findings: {
    title: "Temuan",
    description: "Catat, tindak lanjuti, dan audit isu, risiko, serta perbaikan berkelanjutan.",
  },
  genesis: {
    title: "Genesis",
    description: "Ajukan kebutuhan atau pertanyaan untuk menghasilkan DRAFT yang tetap melalui governance manusia.",
  },
  settings: {
    title: "Pengaturan",
    description: "Kelola preferensi dan akses yang memang diizinkan untuk peran Anda.",
  },
} as const;

export type DashboardModuleKey = keyof typeof dashboardModules;

export function isDashboardModuleKey(value: string): value is DashboardModuleKey {
  return value in dashboardModules;
}
