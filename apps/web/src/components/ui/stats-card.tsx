"use client";

import type { ReactNode } from "react";

export interface StatsCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  icon?: ReactNode;
  badge?: {
    text: string;
    variant?: "success" | "warning" | "danger" | "info" | "neutral";
  };
  onClick?: () => void;
  className?: string;
}

export function StatsCard({
  title,
  value,
  subtitle,
  icon,
  badge,
  onClick,
  className = "",
}: StatsCardProps) {
  const isClickable = Boolean(onClick);

  return (
    <article
      className={`statsCard ${isClickable ? "clickable" : ""} ${className}`}
      onClick={onClick}
    >
      <div className="statsCardTop">
        <span className="statsCardTitle">{title}</span>
        {icon && <div className="statsCardIcon">{icon}</div>}
      </div>

      <div className="statsCardValueRow">
        <strong className="statsCardValue">{value}</strong>
        {badge && (
          <span className={`statsCardBadge ${badge.variant || "neutral"}`}>
            {badge.text}
          </span>
        )}
      </div>

      {subtitle && <p className="statsCardSubtitle">{subtitle}</p>}
    </article>
  );
}
