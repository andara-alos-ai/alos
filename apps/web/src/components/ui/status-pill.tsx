"use client";

import { humanizeCode } from "@/lib/format";

export type StatusVariant =
  | "success"
  | "warning"
  | "danger"
  | "info"
  | "neutral"
  | "purple";

export function resolveStatusVariant(status: string | null | undefined): StatusVariant {
  if (!status) return "neutral";
  const s = status.toUpperCase();

  if (
    [
      "APPROVED",
      "ACCEPTED",
      "ACTIVE",
      "VERIFIED",
      "PUBLISHED",
      "PASSED",
      "PASS",
      "HEALTHY",
      "RELEASED",
      "QUALIFIED",
      "RESERVED",
    ].includes(s)
  ) {
    return "success";
  }

  if (
    [
      "PENDING",
      "SUBMITTED",
      "AWAITING_HUMAN_REVIEW",
      "REVISION_REQUESTED",
      "CONDITIONAL",
      "WARNING",
      "DEGRADED",
      "FOLLOW_UP",
      "IN_PROGRESS",
    ].includes(s)
  ) {
    return "warning";
  }

  if (
    [
      "REJECTED",
      "NOT_APPROVED",
      "CANCELLED",
      "BLOCKED",
      "FAILED",
      "OVERDUE",
      "UNHEALTHY",
      "LOST",
      "DEAD_LETTER",
    ].includes(s)
  ) {
    return "danger";
  }

  if (["STAGED", "PROCESSING", "RETRY", "NEW", "CONTACTED"].includes(s)) {
    return "info";
  }

  if (["DIRECTOR", "AI_EXECUTIVE"].includes(s)) {
    return "purple";
  }

  return "neutral";
}

export interface StatusPillProps {
  status: string | null | undefined;
  variant?: StatusVariant;
  label?: string;
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function StatusPill({
  status,
  variant,
  label,
  size = "sm",
  className = "",
}: StatusPillProps) {
  const resolvedVariant = variant || resolveStatusVariant(status);
  const displayLabel = label || (status ? humanizeCode(status) : "-");

  const sizeClass = size === "sm" ? "statusPill-sm" : size === "lg" ? "statusPill-lg" : "statusPill-md";
  const variantClass = `statusPill-${resolvedVariant}`;

  return (
    <span className={`statusPill ${variantClass} ${sizeClass} ${className}`}>
      <span className="statusPill-dot" />
      <span>{displayLabel}</span>
    </span>
  );
}
