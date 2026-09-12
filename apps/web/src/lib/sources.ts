import { apiRequest } from "@/lib/api-client";

export type SourceType = "TEXT" | "PDF" | "CSV" | "MARKDOWN" | "DOCX";
export type SourceClassification = "INTERNAL" | "RESTRICTED" | "CONFIDENTIAL" | "PUBLIC";

export type SourceRegistrationRequest = {
  workspace_id: string;
  source_key: string;
  name: string;
  source_type: SourceType;
  classification: SourceClassification;
  version_label: string;
  locator?: string | null;
  content: string;
  source_vault_policy_id?: string | null;
  vault_attestation?: boolean;
};

export type SourceVerificationRequest = {
  workspace_id: string;
  reason: string;
};

export type SourceVersionRecord = {
  source_id: string;
  source_version_id: string;
  workspace_id: string;
  source_key: string;
  name: string;
  source_type: SourceType;
  classification: SourceClassification;
  status: string;
  version_label: string;
  sha256: string;
  locator: string | null;
  citation_count: number;
  source_vault_policy_id?: string | null;
  created_at?: string;
};

export type SourceVaultPolicyRecord = {
  source_vault_policy_id: string;
  workspace_id: string;
  policy_name: string;
  storage_backend: string;
  lifecycle_status: string;
  isolation_level: string;
  created_at?: string;
};

export type EvidenceCitation = {
  citation_key: string;
  source_key: string;
  version_label: string;
  snippet: string;
  relevance_score?: number;
};

export async function listWorkspaceSources(workspaceId: string): Promise<SourceVersionRecord[]> {
  return await apiRequest<SourceVersionRecord[]>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources`);
}

export async function registerSource(payload: SourceRegistrationRequest): Promise<SourceVersionRecord> {
  const sourceKey = payload.source_key.trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9_]{2,79}$/.test(sourceKey)) {
    throw new Error("Source key harus berupa huruf kapital, angka, atau underscore (3-80 karakter).");
  }
  if (!payload.name.trim()) {
    throw new Error("Nama sumber pengetahuan wajib diisi.");
  }
  if (!payload.content.trim()) {
    throw new Error("Konten teks sumber pengetahuan wajib diisi.");
  }
  return await apiRequest<SourceVersionRecord>("/api/v1/sources", {
    method: "POST",
    body: JSON.stringify({
      ...payload,
      source_key: sourceKey,
      name: payload.name.trim(),
      content: payload.content.trim(),
    }),
  });
}

export async function verifySource(sourceKey: string, payload: SourceVerificationRequest): Promise<SourceVersionRecord> {
  const reason = payload.reason.trim();
  if (!reason) {
    throw new Error("Alasan verifikasi sumber wajib diisi.");
  }
  return await apiRequest<SourceVersionRecord>(`/api/v1/sources/${encodeURIComponent(sourceKey)}/verify`, {
    method: "POST",
    body: JSON.stringify({
      workspace_id: payload.workspace_id,
      reason,
    }),
  });
}

export async function getSourceVault(workspaceId: string): Promise<SourceVaultPolicyRecord | null> {
  try {
    return await apiRequest<SourceVaultPolicyRecord>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/source-vault`);
  } catch {
    return null;
  }
}

export async function searchSourceEvidence(workspaceId: string, query: string = "", limit: number = 12): Promise<EvidenceCitation[]> {
  const params = new URLSearchParams();
  if (query.trim()) params.set("query", query.trim());
  params.set("limit", String(limit));
  return await apiRequest<EvidenceCitation[]>(`/api/v1/workspaces/${encodeURIComponent(workspaceId)}/sources/evidence?${params.toString()}`);
}

export function canVerifySource(roles: string[]): boolean {
  return roles.some((role) => ["DIRECTOR", "DIVISION_OWNER", "IT_LEAD"].includes(role));
}

export function canRegisterSource(roles: string[]): boolean {
  return roles.some((role) => ["ADMIN", "IT_LEAD", "SECURITY_ADMIN", "QA_SECURITY"].includes(role));
}
