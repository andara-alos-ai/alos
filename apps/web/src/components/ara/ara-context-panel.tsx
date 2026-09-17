"use client";

import {
  araContextErrorPresentation,
  contextTrustLabel,
  type AraContextViewState,
} from "@/lib/ara-context";

export type AraContextPanelProps = {
  state: AraContextViewState;
};

// Renders the ARA context state exactly as the backend Context Builder
// would report it (READY / NEEDS_INFORMATION / BLOCKED), plus UI-only
// states that are never sent by the backend: LOADING (a request is in
// flight), NOT_CONNECTED (no backend endpoint exists yet for this
// checklist item — M2-H02-BE-01/BE-02 are still BELUM MULAI), and ERROR (a
// technical/transport failure, distinct from a policy BLOCKED). This
// component never invents a READY/authorized state locally (M2-H02-FE-01,
// M2-H02-FE-04 acceptance criteria).
export function AraContextPanel({ state }: AraContextPanelProps) {
  if (state.status === "LOADING") {
    return (
      <div aria-busy="true" aria-live="polite" className="alos-ara-ctx-panel loading" role="status">
        <span className="alos-ara-ctx-spinner" aria-hidden="true" />
        <div>
          <strong>Memuat konteks…</strong>
          <small>Memeriksa scope, evidence, dan sumber yang berwenang untuk permintaan ini.</small>
        </div>
      </div>
    );
  }

  if (state.status === "NOT_CONNECTED") {
    return (
      <div className="alos-ara-ctx-panel not-connected" role="note">
        <span className="alos-ara-ctx-icon" aria-hidden="true">
          ⏳
        </span>
        <div>
          <strong>Belum terhubung ke Context Builder</strong>
          <small>
            Endpoint yang menyediakan status context (loading, denied, evidence) belum tersedia.
            Menunggu M2-H02-BE-01 (Authorization Integration) dan M2-H02-BE-02 (Evidence Contract).
            Tidak ada status yang dibuat-buat sebelum backend terhubung.
          </small>
        </div>
      </div>
    );
  }

  // ERROR is a UI-only, transport/technical failure (network error, 5xx,
  // malformed payload) — never a backend policy decision. It must render
  // distinctly from BLOCKED (a real, authoritative permission denial) and
  // must never show the raw technical failure message to the user
  // (M2-H02-FE-04 AC: no ACTIVE/authorized state fabricated locally; the
  // same "no raw technical error" principle from FE-03 also applies here).
  if (state.status === "ERROR") {
    return (
      <div aria-live="assertive" className="alos-ara-ctx-panel error" role="alert">
        <span className="alos-ara-ctx-icon" aria-hidden="true">
          ⚠️
        </span>
        <div>
          <strong>Konteks tidak dapat dimuat saat ini</strong>
          <p>
            Terjadi gangguan teknis saat memuat status context. Ini bukan penolakan izin — coba
            muat ulang beberapa saat lagi.
          </p>
          <small>Langkah berikutnya: Muat ulang halaman; jika berulang, hubungi IT Lead.</small>
        </div>
      </div>
    );
  }

  if (state.status === "BLOCKED" || state.status === "NEEDS_INFORMATION") {
    if (!state.errorCode) {
      return null;
    }
    const presentation = araContextErrorPresentation(state.errorCode);
    const toneClass = state.status === "BLOCKED" ? "denied" : "needs-info";
    return (
      <div
        aria-live="assertive"
        className={`alos-ara-ctx-panel ${toneClass}`}
        role="alert"
      >
        <span className="alos-ara-ctx-icon" aria-hidden="true">
          {state.status === "BLOCKED" ? "🚫" : "❓"}
        </span>
        <div>
          <strong>{presentation.title}</strong>
          <p>{presentation.message}</p>
          <small>Langkah berikutnya: {presentation.nextAction}</small>
          {state.reason ? <small className="alos-ara-ctx-reason">Alasan backend: {state.reason}</small> : null}
        </div>
      </div>
    );
  }

  // READY
  const items = state.bundleItems ?? [];
  return (
    <div className="alos-ara-ctx-panel ready" role="status">
      <div className="alos-ara-ctx-ready-head">
        <strong>Konteks siap digunakan</strong>
        {typeof state.usedTokens === "number" && typeof state.tokenLimit === "number" ? (
          <span className="alos-ara-ctx-token-meter">
            {state.usedTokens.toLocaleString("id-ID")} / {state.tokenLimit.toLocaleString("id-ID")} token
          </span>
        ) : null}
      </div>
      {items.length ? (
        <ul className="alos-ara-ctx-item-list">
          {items.map((item) => (
            <li key={item.key}>
              <span className={`alos-ara-ctx-trust-badge trust-${item.trust.toLowerCase().replace(/_/g, "-")}`}>
                {contextTrustLabel(item.trust)}
              </span>
              <span>{item.purpose}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="alos-empty-copy">Belum ada item konteks yang dipilih.</p>
      )}
      {state.omittedItemKeys && state.omittedItemKeys.length > 0 ? (
        <p className="alos-ara-ctx-omitted">
          {state.omittedItemKeys.length} item konteks tidak disertakan karena keterbatasan kapasitas.
        </p>
      ) : null}
      {state.limitations && state.limitations.length > 0 ? (
        <ul className="alos-ara-ctx-limitations">
          {state.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
