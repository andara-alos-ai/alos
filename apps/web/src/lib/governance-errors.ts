import { ApiError } from "./api-client";

export type GovernanceUiError = {
  title: string;
  reason: string;
  nextAction: string;
  status: number | null;
  correlationId: string | null;
};

const detailMessages: Record<string, Omit<GovernanceUiError, "status" | "correlationId">> = {
  "maker cannot act as checker": {
    title: "Separation of Duties memblokir aksi",
    reason: "Maker pada release request ini tidak boleh menjadi Checker.",
    nextAction: "Masuk dengan akun Checker independen, lalu jalankan test kembali.",
  },
  "positive, negative, regression, security, and recovery tests must pass": {
    title: "Evidence test belum lengkap",
    reason: "Lima kategori test wajib memiliki hasil terbaru yang sesuai expected result.",
    nextAction: "Buka Test & Evidence, perbaiki test yang gagal, lalu jalankan ulang sebagai Checker.",
  },
  "a successful Agent Run is required before review": {
    title: "Agent Run belum memenuhi gate",
    reason: "Release belum memiliki Agent Run sukses yang dapat dijadikan evidence.",
    nextAction: "Jalankan seluruh test yang diwajibkan, lalu kirim kembali evidence untuk review.",
  },
  "business and technical review approvals are required": {
    title: "Review manusia belum lengkap",
    reason: "Approval Business dan Technical belum keduanya tercatat.",
    nextAction: "Minta reviewer independen menyelesaikan gate yang masih pending.",
  },
  "kill switch is active": {
    title: "Aktivasi diblokir Kill Switch",
    reason: "Kontrol penghentian darurat masih aktif pada Agent ini.",
    nextAction: "Verifikasi penyebabnya, lalu clear Kill Switch dengan alasan yang diaudit bila aman.",
  },
};

export function normalizeGovernanceError(error: unknown): GovernanceUiError {
  if (error instanceof ApiError) {
    const exact = detailMessages[error.detail];
    if (exact) return { ...exact, status: error.status, correlationId: error.correlationId };

    const byStatus: Record<number, Omit<GovernanceUiError, "status" | "correlationId">> = {
      400: { title: "Input belum valid", reason: error.detail, nextAction: "Periksa field yang ditandai lalu kirim kembali." },
      401: { title: "Sesi telah berakhir", reason: "ALOS tidak lagi mengenali sesi ini.", nextAction: "Masuk kembali untuk melanjutkan." },
      403: { title: "Aksi tidak diizinkan", reason: error.detail || "Role atau scope Anda tidak memiliki izin.", nextAction: "Gunakan akun dengan role yang tepat atau pilih workspace yang diizinkan." },
      404: { title: "Data tidak ditemukan", reason: error.detail, nextAction: "Muat ulang daftar dan pilih record yang masih tersedia." },
      409: { title: "Aksi bertentangan dengan governance", reason: error.detail, nextAction: "Periksa lifecycle, role, evidence, dan status terbaru sebelum mencoba kembali." },
      422: { title: "Form belum dapat diproses", reason: error.detail, nextAction: "Perbaiki format atau field wajib yang disebutkan." },
      429: { title: "Batas penggunaan tercapai", reason: error.detail, nextAction: "Tunggu periode budget berikutnya atau minta pemilik budget meninjau limit." },
      500: { title: "Layanan Governance mengalami gangguan", reason: "Server tidak dapat menyelesaikan permintaan ini.", nextAction: "Coba lagi. Jika berulang, berikan Reference ID kepada IT Lead." },
    };
    return {
      ...(byStatus[error.status] ?? { title: "Permintaan tidak berhasil", reason: error.detail, nextAction: "Muat ulang data lalu coba kembali." }),
      status: error.status,
      correlationId: error.correlationId,
    };
  }
  if (error instanceof Error) {
    return { title: "Input belum valid", reason: error.message, nextAction: "Perbaiki isian yang disebutkan lalu coba kembali.", status: null, correlationId: null };
  }
  return { title: "Permintaan tidak berhasil", reason: "Terjadi kegagalan yang tidak dikenali.", nextAction: "Muat ulang halaman lalu coba kembali.", status: null, correlationId: null };
}
