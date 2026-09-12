"use client";

import { useCallback, useEffect, useState } from "react";
import {
  type SourceVersionRecord,
  type SourceVaultPolicyRecord,
  type EvidenceCitation,
  type SourceType,
  type SourceClassification,
  listWorkspaceSources,
  registerSource,
  verifySource,
  getSourceVault,
  searchSourceEvidence,
  canRegisterSource,
  canVerifySource,
} from "@/lib/sources";
import { normalizeGovernanceError, type GovernanceUiError } from "@/lib/governance-errors";

type SourcesViewProps = {
  workspaceId: string;
  actorRoles: string[];
  onError: (err: GovernanceUiError | null) => void;
  onNotice: (msg: string) => void;
};

export function SourcesView({ workspaceId, actorRoles, onError, onNotice }: SourcesViewProps) {
  const [sources, setSources] = useState<SourceVersionRecord[]>([]);
  const [vaultPolicy, setVaultPolicy] = useState<SourceVaultPolicyRecord | null>(null);
  const [citations, setCitations] = useState<EvidenceCitation[]>([]);
  const [loading, setLoading] = useState(true);
  const [evidenceQuery, setEvidenceQuery] = useState("");
  const [searchingEvidence, setSearchingEvidence] = useState(false);

  // Modals
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [submittingRegister, setSubmittingRegister] = useState(false);
  const [newKey, setNewKey] = useState("");
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<SourceType>("TEXT");
  const [newClassification, setNewClassification] = useState<SourceClassification>("INTERNAL");
  const [newVersion, setNewVersion] = useState("v1.0");
  const [newContent, setNewContent] = useState("");

  const [verifyTarget, setVerifyTarget] = useState<SourceVersionRecord | null>(null);
  const [verifyReason, setVerifyReason] = useState("");
  const [submittingVerify, setSubmittingVerify] = useState(false);

  const loadData = useCallback(async () => {
    if (!workspaceId) {
      setLoading(false);
      return;
    }
    try {
      const [srcList, vault] = await Promise.all([
        listWorkspaceSources(workspaceId),
        getSourceVault(workspaceId),
      ]);
      setSources(srcList);
      setVaultPolicy(vault);
    } catch (err) {
      onError(normalizeGovernanceError(err));
    } finally {
      setLoading(false);
    }
  }, [workspaceId, onError]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void loadData();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [loadData]);

  async function handleSearchEvidence() {
    if (!workspaceId) return;
    setSearchingEvidence(true);
    onError(null);
    try {
      const res = await searchSourceEvidence(workspaceId, evidenceQuery, 12);
      setCitations(res);
      if (res.length === 0) {
        onNotice("Pencarian selesai: Tidak ada sitasi evidence yang cocok.");
      }
    } catch (err) {
      onError(normalizeGovernanceError(err));
    } finally {
      setSearchingEvidence(false);
    }
  }

  async function handleRegisterSource() {
    if (!canRegisterSource(actorRoles)) return;
    setSubmittingRegister(true);
    onError(null);
    try {
      const created = await registerSource({
        workspace_id: workspaceId,
        source_key: newKey,
        name: newName,
        source_type: newType,
        classification: newClassification,
        version_label: newVersion,
        content: newContent,
      });
      onNotice(`Sumber pengetahuan '${created.source_key}' berhasil didaftarkan.`);
      setShowRegisterModal(false);
      setNewKey("");
      setNewName("");
      setNewContent("");
      await loadData();
    } catch (err) {
      onError(normalizeGovernanceError(err));
    } finally {
      setSubmittingRegister(false);
    }
  }

  async function handleConfirmVerify() {
    if (!verifyTarget || !canVerifySource(actorRoles)) return;
    setSubmittingVerify(true);
    onError(null);
    try {
      await verifySource(verifyTarget.source_key, {
        workspace_id: workspaceId,
        reason: verifyReason,
      });
      onNotice(`Sumber '${verifyTarget.source_key}' berhasil diverifikasi.`);
      setVerifyTarget(null);
      setVerifyReason("");
      await loadData();
    } catch (err) {
      onError(normalizeGovernanceError(err));
    } finally {
      setSubmittingVerify(false);
    }
  }

  return (
    <div className="gov-agent-header">
      {/* Page Header */}
      <div className="gov-page-header">
        <div className="gov-page-title">
          <div className="gov-breadcrumb">
            Controls / <span>Sources &amp; Evidence Vault</span>
          </div>
          <h2>Sumber Pengetahuan &amp; Evidence Vault</h2>
          <p>Daftar sumber dokumen otoritatif, kebijakan isolasi vault, dan verifikasi manusia independen.</p>
        </div>

        <div className="gov-page-controls">
          <button
            className="gov-ag-request-btn"
            disabled={!canRegisterSource(actorRoles)}
            onClick={() => setShowRegisterModal(true)}
            title={!canRegisterSource(actorRoles) ? "Hanya peran IT_LEAD atau Security yang dapat mendaftarkan sumber." : undefined}
            type="button"
          >
            <span>+ Registrasi Sumber</span>
          </button>
        </div>
      </div>

      {/* Source Vault Policy Banner */}
      <div style={{ background: "#ffffff", border: "1px solid #d8e2dc", borderRadius: "10px", padding: "16px 20px", marginBottom: "20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "10px" }}>
          <div>
            <strong style={{ fontSize: "0.9rem", color: "#111827" }}>
              Source Vault Boundary Policy: {vaultPolicy?.policy_name ?? "Workspace Default Vault"}
            </strong>
            <p style={{ margin: "4px 0 0 0", fontSize: "0.78rem", color: "#546e63" }}>
              Backend Storage: <code>{vaultPolicy?.storage_backend ?? "PostgreSQL / Encrypted Metadata"}</code> · Isolasi: <strong>{vaultPolicy?.isolation_level ?? "WORKSPACE_BOUNDED"}</strong> · Status: <span style={{ color: "#15803d", fontWeight: 600 }}>{vaultPolicy?.lifecycle_status ?? "ACTIVE"}</span>
            </p>
          </div>
          <button
            className="gov-agent-btn-outline"
            onClick={() => void loadData()}
            style={{ fontSize: "0.76rem" }}
            type="button"
          >
            ↻ Refresh State
          </button>
        </div>
      </div>

      {/* Source Registry Table */}
      <div className="gov-table-card" style={{ marginBottom: "24px" }}>
        <div style={{ padding: "14px 20px", borderBottom: "1px solid #eef2f0", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <strong style={{ fontSize: "0.88rem", color: "#111827" }}>Source Registry ({sources.length})</strong>
          <span style={{ fontSize: "0.76rem", color: "#6b7280" }}>
            Hanya sumber berstatus <strong>VERIFIED</strong> yang dapat diretrieve oleh Agent Runtime.
          </span>
        </div>
        <div className="gov-table-wrap">
          <table className="gov-ag-table">
            <thead>
              <tr>
                <th>Source Key</th>
                <th>Nama Sumber</th>
                <th>Tipe</th>
                <th>Klasifikasi</th>
                <th>Versi</th>
                <th>Status Verifikasi</th>
                <th>Sitasi</th>
                <th style={{ textAlign: "right", paddingRight: "20px" }}>Aksi</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((src) => (
                <tr key={src.source_version_id}>
                  <td><code>{src.source_key}</code></td>
                  <td><strong>{src.name}</strong></td>
                  <td><span className="gov-ag-scope">{src.source_type}</span></td>
                  <td><span className={`gov-ag-risk-pill ${src.classification.toLowerCase()}`}>{src.classification}</span></td>
                  <td><span className="gov-ag-version">{src.version_label}</span></td>
                  <td>
                    <span className={`gov-perm-status-badge ${src.status.toLowerCase()}`}>
                      {src.status}
                    </span>
                  </td>
                  <td>{src.citation_count}</td>
                  <td style={{ textAlign: "right", paddingRight: "20px" }}>
                    {src.status === "VERIFIED" ? (
                      <span style={{ color: "#15803d", fontWeight: 600, fontSize: "0.76rem" }}>✓ Verified</span>
                    ) : (
                      <button
                        className="gov-perm-action-btn"
                        disabled={!canVerifySource(actorRoles)}
                        onClick={() => {
                          setVerifyTarget(src);
                          setVerifyReason("");
                        }}
                        title={!canVerifySource(actorRoles) ? "Hanya DIRECTOR, DIVISION_OWNER, atau IT_LEAD yang berwenang memverifikasi sumber." : undefined}
                        type="button"
                      >
                        Verify
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {sources.length === 0 && !loading && (
                <tr>
                  <td colSpan={8} style={{ textAlign: "center", padding: "36px", color: "#6e847a" }}>
                    Belum ada sumber pengetahuan terdaftar pada workspace ini.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Evidence Citations Search & Retrieval */}
      <div className="gov-table-card">
        <div style={{ padding: "16px 20px", borderBottom: "1px solid #eef2f0" }}>
          <strong style={{ fontSize: "0.88rem", color: "#111827", display: "block" }}>
            Pencarian Sitasi &amp; Evidence Retrieval
          </strong>
          <p style={{ fontSize: "0.76rem", color: "#6b7280", margin: "4px 0 12px 0" }}>
            Uji query untuk melihat bukti sitasi faktual yang dapat diakses oleh tools runtime.
          </p>
          <div style={{ display: "flex", gap: "10px" }}>
            <input
              className="gov-ag-search-input"
              onChange={(e) => setEvidenceQuery(e.target.value)}
              placeholder="Masukkan kata kunci pencarian sitasi (mis: regulasi, SOP, kualifikasi)..."
              style={{ flex: 1, padding: "8px 14px", border: "1px solid #cfdad3", borderRadius: "6px" }}
              value={evidenceQuery}
            />
            <button
              className="gov-modal-btn-confirm success"
              disabled={searchingEvidence}
              onClick={() => void handleSearchEvidence()}
              type="button"
            >
              {searchingEvidence ? "Mencari..." : "Cari Evidence"}
            </button>
          </div>
        </div>

        {citations.length > 0 && (
          <div style={{ padding: "16px 20px", display: "flex", flexDirection: "column", gap: "12px" }}>
            {citations.map((c) => (
              <div key={c.citation_key} style={{ background: "#f8faf9", border: "1px solid #d8e2dc", borderRadius: "8px", padding: "12px 16px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "6px" }}>
                  <span>
                    <strong>{c.source_key}</strong> · <code>{c.version_label}</code>
                  </span>
                  {typeof c.relevance_score === "number" && (
                    <span style={{ fontSize: "0.76rem", color: "#546e63" }}>
                      Relevance: {(c.relevance_score * 100).toFixed(0)}%
                    </span>
                  )}
                </div>
                <p style={{ margin: 0, fontSize: "0.8rem", color: "#374151", fontStyle: "italic" }}>
                  &ldquo;{c.snippet}&rdquo;
                </p>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Modal: Register Source */}
      {showRegisterModal && (
        <div className="gov-modal-backdrop" role="presentation">
          <section aria-labelledby="modal-reg-source" aria-modal="true" className="gov-modal" role="dialog">
            <h3 id="modal-reg-source" style={{ margin: "0 0 16px 0", fontSize: "1.1rem" }}>Registrasi Sumber Pengetahuan Baru</h3>
            <div className="gov-modal-field">
              <label htmlFor="src-key-input">Source Key (Unique, CAPITAL):</label>
              <input
                id="src-key-input"
                onChange={(e) => setNewKey(e.target.value.toUpperCase())}
                placeholder="CONTOH: SOP_AUDIT_FINANSIAL"
                value={newKey}
              />
            </div>
            <div className="gov-modal-field">
              <label htmlFor="src-name-input">Nama Sumber:</label>
              <input
                id="src-name-input"
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Pedoman SOP Audit Finansial 2026"
                value={newName}
              />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "10px" }}>
              <div className="gov-modal-field">
                <label htmlFor="src-type-select">Tipe Sumber:</label>
                <select id="src-type-select" onChange={(e) => setNewType(e.target.value as SourceType)} value={newType}>
                  <option value="TEXT">TEXT</option>
                  <option value="PDF">PDF</option>
                  <option value="CSV">CSV</option>
                  <option value="MARKDOWN">MARKDOWN</option>
                  <option value="DOCX">DOCX</option>
                </select>
              </div>
              <div className="gov-modal-field">
                <label htmlFor="src-class-select">Klasifikasi:</label>
                <select id="src-class-select" onChange={(e) => setNewClassification(e.target.value as SourceClassification)} value={newClassification}>
                  <option value="INTERNAL">INTERNAL</option>
                  <option value="RESTRICTED">RESTRICTED</option>
                  <option value="CONFIDENTIAL">CONFIDENTIAL</option>
                  <option value="PUBLIC">PUBLIC</option>
                </select>
              </div>
              <div className="gov-modal-field">
                <label htmlFor="src-ver-input">Label Versi:</label>
                <input id="src-ver-input" onChange={(e) => setNewVersion(e.target.value)} value={newVersion} />
              </div>
            </div>
            <div className="gov-modal-field">
              <label htmlFor="src-content-input">Konten Teks Sumber:</label>
              <textarea
                id="src-content-input"
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="Masukkan teks lengkap materi pedoman / kebijakan..."
                rows={5}
                value={newContent}
              />
            </div>
            <div className="gov-modal-actions">
              <button className="gov-modal-btn-cancel" disabled={submittingRegister} onClick={() => setShowRegisterModal(false)} type="button">
                Batal
              </button>
              <button className="gov-modal-btn-confirm success" disabled={submittingRegister} onClick={() => void handleRegisterSource()} type="button">
                {submittingRegister ? "Mendaftarkan..." : "Simpan & Daftarkan"}
              </button>
            </div>
          </section>
        </div>
      )}

      {/* Modal: Verify Source */}
      {verifyTarget && (
        <div className="gov-modal-backdrop" role="presentation">
          <section aria-labelledby="modal-verify-source" aria-modal="true" className="gov-modal" role="dialog">
            <h3 id="modal-verify-source" style={{ margin: "0 0 10px 0", fontSize: "1.1rem" }}>
              Verifikasi Manusia: {verifyTarget.name}
            </h3>
            <p style={{ fontSize: "0.8rem", color: "#546e63", marginBottom: "16px" }}>
              Sebagai pejabat berwenang (Director / Division Owner / IT Lead), berikan alasan verifikasi kelayakan konten sumber ini untuk dijadikan rujukan operasional AI.
            </p>
            <div className="gov-modal-field">
              <label htmlFor="verify-reason-input">Alasan / Catatan Verifikasi:</label>
              <textarea
                id="verify-reason-input"
                onChange={(e) => setVerifyReason(e.target.value)}
                placeholder="Contoh: Dokumen telah direview dan sesuai dengan regulasi kepatuhan operasional internal..."
                rows={3}
                value={verifyReason}
              />
            </div>
            <div className="gov-modal-actions">
              <button className="gov-modal-btn-cancel" disabled={submittingVerify} onClick={() => setVerifyTarget(null)} type="button">
                Batal
              </button>
              <button className="gov-modal-btn-confirm success" disabled={submittingVerify || !verifyReason.trim()} onClick={() => void handleConfirmVerify()} type="button">
                {submittingVerify ? "Memverifikasi..." : "Konfirmasi Verifikasi"}
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
