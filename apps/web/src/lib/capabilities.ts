export type CapabilityRiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type CapabilityAccessMode =
  | "READ"
  | "CREATE_DRAFT"
  | "UPDATE_SCOPED"
  | "REQUEST_APPROVAL"
  | "EXECUTE_APPROVED_ACTION";

export type CapabilityAvailability = "AVAILABLE" | "UNAVAILABLE" | "DEGRADED";

export type CapabilityConfigurationStatus =
  | "CONFIGURED"
  | "NEEDS_CONFIGURATION"
  | "NOT_APPLICABLE";

export type CapabilityRecord = {
  capability_key: string;
  domain: string;
  name: string;
  description: string;
  supported_scopes: string[];
  allowed_data_classification: string[];
  risk_level: CapabilityRiskLevel;
  access_mode: CapabilityAccessMode;
  availability: CapabilityAvailability;
  configuration_status: CapabilityConfigurationStatus;
  version: number;
  metadata: Record<string, unknown>;
  backing_tools: string[];
  created_at: string;
  updated_at: string;
};

export type CapabilityResolution = {
  resolved: CapabilityRecord[];
  missing_dependencies: string[];
  unavailable: string[];
  activation_readiness: "READY" | "NEEDS_CONFIGURATION";
};

export type TypedToolRecord = {
  tool_key: string;
  capability_key: string;
  description: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  risk_level: CapabilityRiskLevel;
  allowed_scopes: string[];
  required_permission: string;
  access_mode: string;
  timeout_seconds: number;
  idempotency_policy: "NONE" | "OPTIONAL" | "REQUIRED";
  audit_policy: "ALWAYS" | "ON_WRITE";
  runtime_handler: string;
  lifecycle_status: string;
  version: number;
};

/**
 * Human-readable readiness derived from availability + configuration_status,
 * matching backend semantics: a capability can only be operationally used
 * when it is AVAILABLE and CONFIGURED. Everything else is a safe blocker,
 * never a silent fallback.
 */
export function capabilityReadiness(
  capability: Pick<CapabilityRecord, "availability" | "configuration_status">,
): "READY" | "NEEDS_CONFIGURATION" | "UNAVAILABLE" {
  if (capability.availability === "UNAVAILABLE") return "UNAVAILABLE";
  if (capability.configuration_status !== "CONFIGURED") return "NEEDS_CONFIGURATION";
  return "READY";
}

export function capabilityReadinessTone(
  readiness: ReturnType<typeof capabilityReadiness>,
): "success" | "warning" | "danger" {
  if (readiness === "READY") return "success";
  if (readiness === "NEEDS_CONFIGURATION") return "warning";
  return "danger";
}

export function capabilityRiskTone(risk: CapabilityRiskLevel): "info" | "warning" | "danger" {
  if (risk === "LOW" || risk === "MEDIUM") return "info";
  if (risk === "HIGH") return "warning";
  return "danger";
}

export function formatCapabilityScopes(capability: CapabilityRecord): string {
  return capability.supported_scopes.join(", ") || "Tidak ada scope";
}

export function formatCapabilityDomainLabel(domain: string): string {
  return domain
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function groupCapabilitiesByDomain(
  capabilities: readonly CapabilityRecord[],
): Array<{ domain: string; items: CapabilityRecord[] }> {
  const groups = new Map<string, CapabilityRecord[]>();
  for (const capability of capabilities) {
    const bucket = groups.get(capability.domain) ?? [];
    bucket.push(capability);
    groups.set(capability.domain, bucket);
  }
  return [...groups.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([domain, items]) => ({
      domain,
      items: [...items].sort((a, b) => a.name.localeCompare(b.name)),
    }));
}
