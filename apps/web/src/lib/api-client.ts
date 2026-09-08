export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly detail: string,
    readonly correlationId: string | null,
    readonly payload: unknown = null,
  ) {
    super(detail);
    this.name = "ApiError";
  }
}

type QueryValue = string | number | boolean | null | undefined;

export function withQuery(path: string, query: Record<string, QueryValue>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `${path}?${encoded}` : path;
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const response = await fetch(path, {
    cache: "no-store",
    credentials: "same-origin",
    ...init,
    headers,
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as unknown;
    throw new ApiError(
      response.status,
      apiErrorDetail(payload) ?? `Permintaan ALOS gagal (${response.status}).`,
      response.headers.get("X-Correlation-ID"),
      payload,
    );
  }
  if (response.status === 204) return undefined as T;
  return await response.json() as T;
}

export function apiMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.correlationId
      ? `${error.detail} Referensi: ${error.correlationId}`
      : error.detail;
  }
  return error instanceof Error ? error.message : "Terjadi kegagalan yang tidak diketahui.";
}

export function apiErrorDetail(payload: unknown): string | undefined {
  if (!payload || typeof payload !== "object" || !("detail" in payload)) return undefined;
  const detail = payload.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (!item || typeof item !== "object") return null;
        if ("msg" in item && typeof item.msg === "string") return item.msg;
        return null;
      })
      .filter((item): item is string => Boolean(item))
      .join("; ");
  }
  return undefined;
}
