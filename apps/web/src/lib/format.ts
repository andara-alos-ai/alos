const dateTimeFormatter = new Intl.DateTimeFormat("id-ID", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "Asia/Jakarta",
});

export function formatDateTime(value: string | null): string {
  if (!value) return "Belum ditetapkan";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Waktu tidak valid";
  return dateTimeFormatter.format(date);
}

export function relativeDeadline(value: string | null, now = new Date()): string {
  if (!value) return "Tanpa deadline";
  const target = new Date(value);
  if (Number.isNaN(target.getTime())) return "Deadline tidak valid";
  const minutes = Math.round((target.getTime() - now.getTime()) / 60_000);
  const absoluteMinutes = Math.abs(minutes);
  if (absoluteMinutes < 60) {
    return minutes < 0 ? `Terlambat ${absoluteMinutes} menit` : `${absoluteMinutes} menit lagi`;
  }
  const hours = Math.round(absoluteMinutes / 60);
  if (hours < 48) return minutes < 0 ? `Terlambat ${hours} jam` : `${hours} jam lagi`;
  const days = Math.round(hours / 24);
  return minutes < 0 ? `Terlambat ${days} hari` : `${days} hari lagi`;
}

export function humanizeCode(value: string): string {
  return value
    .toLowerCase()
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export function shortId(value: string | null): string {
  if (!value) return "—";
  return value.slice(0, 8).toUpperCase();
}
