import Link from "next/link";
import type { ReactNode } from "react";

import type { GovernanceUiError } from "@/lib/governance-errors";

export type GovernanceArea = "overview" | "agents" | "releases";

export function GovernanceNavigation({ active }: { active: GovernanceArea }) {
  return (
    <nav className="governance-navigation" aria-label="Governance dan Agent Control">
      <div><span>Governance</span><Link aria-current={active === "overview" ? "page" : undefined} className={active === "overview" ? "active" : ""} href="/governance">Overview &amp; Controls</Link></div>
      <div><span>Agent Control</span><Link aria-current={active === "agents" ? "page" : undefined} className={active === "agents" ? "active" : ""} href="/agents">Agents &amp; Permissions</Link><Link aria-current={active === "releases" ? "page" : undefined} className={active === "releases" ? "active" : ""} href="/releases">Release, Test &amp; Review</Link></div>
    </nav>
  );
}

export function GovernanceFeedback({ error, notice, onDismiss }: { error: GovernanceUiError | null; notice: string; onDismiss?: () => void }) {
  return (
    <>
      {error ? (
        <section className="governance-feedback error" role="alert">
          <div><strong>{error.title}</strong><p>{error.reason}</p><small>Langkah berikutnya: {error.nextAction}</small>{error.correlationId ? <code>Reference ID: {error.correlationId}</code> : null}</div>
          {onDismiss ? <button aria-label="Tutup pesan error" className="feedback-close" onClick={onDismiss} type="button">×</button> : null}
        </section>
      ) : null}
      {notice ? <p className="governance-toast" role="status">✓ {notice}</p> : null}
    </>
  );
}

export type Confirmation = {
  title: string;
  impact: string;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm: () => void;
};

export function GovernanceConfirmationModal({ confirmation, busy, onCancel }: { confirmation: Confirmation | null; busy: boolean; onCancel: () => void }) {
  if (!confirmation) return null;
  return (
    <div className="governance-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) onCancel(); }}>
      <section aria-labelledby="governance-modal-title" aria-modal="true" className="governance-modal" role="dialog">
        <p className="eyebrow">KONFIRMASI GOVERNANCE</p>
        <h2 id="governance-modal-title">{confirmation.title}</h2>
        <p>{confirmation.impact}</p>
        <p className="safe-note">Aksi ini akan membuat audit record permanen. Riwayat sebelumnya tidak dihapus.</p>
        <div className="builder-actions">
          <button className="secondary-button" disabled={busy} onClick={onCancel} type="button">Batal</button>
          <button className={confirmation.destructive ? "danger-button" : ""} disabled={busy} onClick={confirmation.onConfirm} type="button">{busy ? "Memproses…" : confirmation.confirmLabel}</button>
        </div>
      </section>
    </div>
  );
}

export function EmptyControlState({ children }: { children: ReactNode }) {
  return <p className="empty-state governance-empty">{children}</p>;
}
