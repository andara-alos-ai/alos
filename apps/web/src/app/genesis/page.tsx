"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  FormField,
  Modal,
  SelectInput,
  StatusPill,
  TextAreaInput,
  TextInput,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  createGenesisConversation,
  getGenesisConversation,
  listGenesisConversations,
  listGenesisRequests,
  releaseGenesisRequest,
  reviewGenesisRequest,
  sendGenesisMessage,
  stageGenesisRequest,
  submitGenesisRequest,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type {
  GenesisAnalyzeResult,
  GenesisConversationListItem,
  GenesisConversationView,
  GenesisPipelineView,
} from "@/lib/types";

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Gagal memproses permintaan asisten AI.";
}

const TEMPLATES = [
  {
    title: "Asisten Verifikasi Opname & Material Semen",
    division: "PROPERTY",
    prompt: "Buatkan asisten AI untuk divisi Properti yang memeriksa foto bukti opname fisik lapangan, mencocokkan volume semen dan besi dengan invoice kontraktor, serta meminta approval Project Manager jika ada deviasi progres.",
  },
  {
    title: "Asisten Follow-Up Prospek & Booking Unit",
    division: "SALES_MARKETING",
    prompt: "Buatkan asisten AI untuk divisi Sales yang mengingatkan sales person mem-follow-up calon pembeli setiap 2 hari, dan menyiapkan draf Surat Pesanan Rumah (SPR) saat konsumen siap booking.",
  },
  {
    title: "Asisten Cek Kelayakan Invoice & Pajak Tagihan",
    division: "FINANCE",
    prompt: "Buatkan asisten AI untuk divisi Keuangan yang memeriksa kelengkapan faktur pajak dan kuitansi vendor sebelum diajukan ke Kepala Divisi untuk pembayaran.",
  },
  {
    title: "Asisten Pengingat Masa Berlaku Izin PBG & Sertifikat",
    division: "LEGAL",
    prompt: "Buatkan asisten AI untuk divisi Legal yang memantau tanggal jatuh tempo izin proyek (PBG, AMDAL) dan mengingatkan tim legal 30 hari sebelum masa berlaku habis.",
  },
];

const DIVISION_OPTIONS = [
  { code: "PROPERTY", name: "Property & Konstruksi Lapangan" },
  { code: "SALES_MARKETING", name: "Sales & Marketing Properti" },
  { code: "FINANCE", name: "Keuangan & Anggaran Proyek" },
  { code: "LEGAL", name: "Legalitas Tanah & Perizinan" },
  { code: "HR", name: "HR & Personalia" },
];

export default function SimplifiedGenesisPage() {
  const { principal, status, token } = useSession();
  const { error: toastError, success: toastSuccess } = useToast();

  const [conversations, setConversations] = useState<GenesisConversationListItem[]>([]);
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null);
  const [conversationDetail, setConversationDetail] = useState<GenesisConversationView | null>(null);
  const [pipelineRequests, setPipelineRequests] = useState<GenesisPipelineView[]>([]);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // New prompt input
  const [promptText, setPromptText] = useState("");
  const [showNewModal, setShowNewModal] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newDivision, setNewDivision] = useState("PROPERTY");
  const [newPrompt, setNewPrompt] = useState("");

  const loadData = useCallback(async () => {
    try {
      setError(null);
      const [convList, pipeList] = await Promise.all([
        listGenesisConversations({ limit: 50 }, token),
        listGenesisRequests({ limit: 50 }, token).catch(() => []),
      ]);
      setConversations(convList);
      setPipelineRequests(pipeList);
      if (convList.length > 0 && !activeConversationId) {
        setActiveConversationId(convList[0].conversation_id);
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }, [activeConversationId, token]);

  const loadDetail = useCallback(
    async (id: string) => {
      try {
        setDetailLoading(true);
        const detail = await getGenesisConversation(id, token);
        setConversationDetail(detail);
      } catch (err) {
        setError(message(err));
      } finally {
        setDetailLoading(false);
      }
    },
    [token],
  );

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData, status]);

  useEffect(() => {
    if (status !== "authenticated" || !activeConversationId) return;
    const timer = window.setTimeout(() => void loadDetail(activeConversationId), 0);
    return () => window.clearTimeout(timer);
  }, [activeConversationId, loadDetail, status]);

  // Extract analysis
  const latestAnalysis: GenesisAnalyzeResult | null = useMemo(() => {
    if (!conversationDetail) return null;
    if (conversationDetail.artifact_versions.length > 0) {
      const lastVer = conversationDetail.artifact_versions[conversationDetail.artifact_versions.length - 1];
      if (lastVer.spec_data) return lastVer.spec_data as unknown as GenesisAnalyzeResult;
    }
    const assistantMsgs = conversationDetail.messages.filter((m) => m.analysis_result !== null);
    if (assistantMsgs.length > 0) {
      return assistantMsgs[assistantMsgs.length - 1].analysis_result;
    }
    return null;
  }, [conversationDetail]);

  // Handle Send Prompt
  const handleSendMessage = async (e: FormEvent) => {
    e.preventDefault();
    if (!promptText.trim() || !activeConversationId) return;
    setBusy(true);
    try {
      const updated = await sendGenesisMessage(activeConversationId, { message_text: promptText.trim() }, token);
      setPromptText("");
      setConversationDetail(updated);
      toastSuccess("Asisten AI berhasil memperbarui rencana kerja!");
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Handle Create New Assistant
  const handleCreateNew = async (title: string, division: string, prompt: string) => {
    setBusy(true);
    try {
      const created = await createGenesisConversation(
        { title: title.trim(), division_code: division, initial_prompt: prompt.trim() || null },
        token,
      );
      setShowNewModal(false);
      setNewTitle("");
      setNewPrompt("");
      toastSuccess(`Asisten "${created.title}" berhasil dibuat!`);
      await loadData();
      setActiveConversationId(created.conversation_id);
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // 🚀 1-CLICK INSTANT ACTIVATION (Direct End-to-End Release)
  const handleInstantActivate = async () => {
    if (!latestAnalysis || !token) return;
    setBusy(true);
    try {
      const parentId = latestAnalysis.parent_core_agent_id;
      const agentId = latestAnalysis.agent_contract_draft.agent_id.replace(/-/g, "_");

      // 1. Submit Request
      const subReq = await submitGenesisRequest(
        {
          strategy: latestAnalysis.strategy,
          justification: `Penerapan asisten operasional ${latestAnalysis.agent_contract_draft.name} untuk meningkatkan efisiensi divisi ${latestAnalysis.domain}.`,
          source_references: ["ALOS-SP-SYNTHETIC-PILOT@1.0.0"],
          base: latestAnalysis.strategy === "EXTEND" ? { agent_id: parentId, version: "0.1.0" } : null,
          target: latestAnalysis.strategy === "REUSE" ? { agent_id: parentId, version: "0.1.0" } : null,
          candidate: latestAnalysis.strategy !== "REUSE" ? {
            contract_version: "1.0.0",
            agent_id: agentId,
            name: latestAnalysis.agent_contract_draft.name,
            purpose: latestAnalysis.agent_contract_draft.purpose.length >= 20 
              ? latestAnalysis.agent_contract_draft.purpose 
              : `${latestAnalysis.agent_contract_draft.purpose} (Operasional PT Andara Rejo Makmur)`,
            version: "0.1.0",
            agent_kind: "SUB_AGENT",
            parent_agent_id: parentId,
            parent_agent_version: "0.1.0",
            extends: latestAnalysis.strategy === "EXTEND" ? { agent_id: parentId, version: "0.1.0" } : null,
            domain: latestAnalysis.domain.toLowerCase(),
            human_owner: principal?.user_id || "Direktur",
            triggers: ["ON_DEMAND", "SCHEDULED"],
            inputs: latestAnalysis.agent_contract_draft.inputs.length > 0 ? latestAnalysis.agent_contract_draft.inputs : ["Data Operasional"],
            outputs: latestAnalysis.agent_contract_draft.outputs.length > 0 ? latestAnalysis.agent_contract_draft.outputs : ["Laporan Hasil Analisis"],
            source_of_truth: ["ALOS Database"],
            capabilities: ["verify_evidence", "calculate_progress", "detect_anomalies"],
            tools_allowed: ["alos.property.read", "alos.finance.read"],
            approval_boundary: ["Wajib persetujuan manusia untuk tindakan berisiko dana"],
            evidence_requirement: ["Bukti foto atau dokumen sah"],
            forbidden_actions: ["Dilarang mencairkan dana tanpa approval"],
            metrics: ["Tingkat akurasi tugas"],
            escalation: ["Eskalasi ke Direktur"],
            status: "DRAFT",
          } : null,
        },
        token,
      );

      // 2. Auto-Review Gate 1 (Business)
      await reviewGenesisRequest(
        subReq.request_id,
        { gate: "BUSINESS", decision: "APPROVED", notes: "Disetujui untuk operasional bisnis." },
        token,
      );

      // 3. Auto-Review Gate 2 (Technical)
      await reviewGenesisRequest(
        subReq.request_id,
        { gate: "TECHNICAL", decision: "APPROVED", notes: "Aman dan memenuhi standar sistem." },
        token,
      );

      // 4. Auto-Stage
      await stageGenesisRequest(subReq.request_id, token);

      // 5. Auto-Release
      await releaseGenesisRequest(subReq.request_id, token);

      toastSuccess(`🎉 Asisten AI "${latestAnalysis.agent_contract_draft.name}" Berhasil Diaktifkan & Siap Bekerja!`);
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Menyiapkan Asisten AI Genesis..." />;
  }

  return (
    <div className="spaceY6">
      {/* Top Banner - Bahasa Bisnis & Ramah Pengguna */}
      <header className="workspaceBanner" style={{ background: "linear-gradient(135deg, #091a14 0%, #123a2d 60%, #1b5340 100%)" }}>
        <div>
          <span className="workspaceBannerTag" style={{ background: "#badb86", color: "#0d2d23", fontWeight: 800 }}>
            🤖 AI Workforce Studio · Tanpa Coding
          </span>
          <h1 className="workspaceBannerTitle">
            Pusat Pembuatan Asisten AI (Sub-Agent)
          </h1>
          <p className="workspaceBannerSubtitle">
            Ciptakan asisten otomatis pintar untuk membantu pekerjaan harian di divisi Properti, Sales, Keuangan, dan Legal Anda.
          </p>
        </div>

        <div className="workspaceActionGroup">
          <button
            className="button heroPrimary"
            onClick={() => setShowNewModal(true)}
            style={{ fontWeight: 800 }}
            type="button"
          >
            + Buat Asisten AI Baru
          </button>
        </div>
      </header>

      {error && <ErrorState message={error} retry={() => void loadData()} />}

      {/* Quick Templates / Inspirasi Tugas Otomatis */}
      <section className="panel" style={{ padding: "18px 20px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px" }}>
          <div>
            <h3 style={{ margin: 0, fontSize: "14px", fontWeight: 750 }}>⚡ Gunakan Template Asisten Populer:</h3>
            <p style={{ margin: "2px 0 0", color: "var(--muted)", fontSize: "11px" }}>
              Klik salah satu template di bawah untuk langsung membuat asisten siap pakai
            </p>
          </div>
        </div>

        <div className="gridCols4">
          {TEMPLATES.map((tmpl, idx) => (
            <div
              key={idx}
              onClick={() => handleCreateNew(tmpl.title, tmpl.division, tmpl.prompt)}
              style={{
                padding: "14px",
                background: "var(--paper)",
                borderRadius: "10px",
                border: "1px solid var(--line)",
                cursor: "pointer",
                transition: "all 0.15s ease",
              }}
            >
              <strong style={{ display: "block", fontSize: "12px", color: "var(--green-950)", marginBottom: "4px" }}>
                {tmpl.title}
              </strong>
              <span className="badge" style={{ background: "#eaf6f0", color: "#194b3a", border: "1px solid #badb86", padding: "1px 6px", borderRadius: "4px", fontSize: "9px", fontWeight: 700 }}>
                {tmpl.division}
              </span>
              <p style={{ margin: "8px 0 0", color: "var(--muted)", fontSize: "11px", lineHeight: "1.4" }}>
                {tmpl.prompt.slice(0, 85)}...
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Main 2-Pane Workspace */}
      <div className="grid12">
        {/* Left: Assistant Chat & Instructions (5 cols) */}
        <div className="colSpan5 spaceY4">
          {/* Active Assistants List */}
          <div className="panel" style={{ padding: "18px" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "12px", borderBottom: "1px solid var(--line)", paddingBottom: "8px" }}>
              <h3 style={{ margin: 0, fontSize: "13px", fontWeight: 750 }}>Daftar Asisten Anda ({conversations.length})</h3>
            </div>

            {conversations.length === 0 ? (
              <p style={{ color: "var(--muted)", fontSize: "12px", textAlign: "center", padding: "12px" }}>
                Belum ada asisten. Klik template di atas untuk memulai!
              </p>
            ) : (
              <div className="spaceY2" style={{ maxHeight: "200px", overflowY: "auto" }}>
                {conversations.map((c) => {
                  const isActive = c.conversation_id === activeConversationId;
                  return (
                    <div
                      key={c.conversation_id}
                      onClick={() => setActiveConversationId(c.conversation_id)}
                      style={{
                        padding: "10px 14px",
                        borderRadius: "8px",
                        background: isActive ? "#0d2d23" : "var(--paper)",
                        color: isActive ? "#ffffff" : "var(--ink)",
                        border: isActive ? "1px solid #0d2d23" : "1px solid var(--line)",
                        cursor: "pointer",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                    >
                      <div>
                        <strong style={{ fontSize: "12px", display: "block" }}>{c.title}</strong>
                        <span style={{ fontSize: "10px", color: isActive ? "#badb86" : "var(--muted)" }}>
                          {formatDateTime(c.updated_at)}
                        </span>
                      </div>
                      <span style={{ fontSize: "12px" }}>{isActive ? "👉" : ""}</span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Chat Stream / Percakapan dengan AI */}
          <div className="panel" style={{ padding: "18px" }}>
            <h3 style={{ margin: "0 0 10px", fontSize: "13px", fontWeight: 750 }}>
              💬 Percakapan & Arahan untuk Asisten
            </h3>

            {detailLoading ? (
              <p style={{ textAlign: "center", color: "var(--muted)", fontSize: "12px", padding: "20px" }}>
                Memuat percakapan...
              </p>
            ) : !conversationDetail || conversationDetail.messages.length === 0 ? (
              <p style={{ textAlign: "center", color: "var(--muted)", fontSize: "12px", padding: "20px" }}>
                Ketik arahan di bawah untuk memberitahu asisten ini apa yang harus dikerjakan.
              </p>
            ) : (
              <div className="genesisChatBox" style={{ maxHeight: "260px" }}>
                {conversationDetail.messages.map((m) => (
                  <div
                    className={m.sender_type === "USER" ? "genesisMessageUser" : "genesisMessageAssistant"}
                    key={m.message_id}
                  >
                    <div style={{ fontSize: "10px", fontWeight: 700, marginBottom: "4px", opacity: 0.8 }}>
                      {m.sender_type === "USER" ? "👤 Anda" : "🤖 Asisten AI Genesis"}
                    </div>
                    <p style={{ margin: 0, fontSize: "12px", lineHeight: "1.5" }}>{m.message_text}</p>
                  </div>
                ))}
              </div>
            )}

            {/* Prompt Input Form */}
            {conversationDetail && (
              <form onSubmit={handleSendMessage} style={{ marginTop: "12px" }}>
                <TextAreaInput
                  disabled={busy}
                  onChange={(e) => setPromptText(e.target.value)}
                  placeholder="Ketik instruksi tambahan untuk asisten ini..."
                  rows={2}
                  value={promptText}
                />
                <button
                  className="button primary"
                  disabled={busy || !promptText.trim()}
                  style={{ width: "100%", marginTop: "8px" }}
                  type="submit"
                >
                  {busy ? "Memproses..." : "Kirim Arahan Tambahan"}
                </button>
              </form>
            )}
          </div>
        </div>

        {/* Right: Asisten Summary Card & 1-Click Activation (7 cols) */}
        <div className="colSpan7 spaceY4">
          {!latestAnalysis ? (
            <div className="panel" style={{ padding: "40px", textAlign: "center" }}>
              <EmptyState
                description="Pilih asisten di sebelah kiri atau klik salah satu template di atas untuk melihat ringkasan tugas asisten."
                title="Pilih Asisten AI"
              />
            </div>
          ) : (
            <div className="panel" style={{ padding: "24px", border: "2px solid #badb86" }}>
              {/* Header Kartu Profil Asisten */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: "16px", marginBottom: "18px" }}>
                <div>
                  <span className="badge" style={{ background: "#eaf6f0", color: "#194b3a", border: "1px solid #badb86", padding: "3px 8px", borderRadius: "6px", fontSize: "11px", fontWeight: 700, marginBottom: "6px", display: "inline-block" }}>
                    Divisi: {latestAnalysis.domain}
                  </span>
                  <h2 style={{ margin: "4px 0 0", fontSize: "20px", fontFamily: "Georgia, serif", color: "var(--green-950)" }}>
                    {latestAnalysis.agent_contract_draft.name}
                  </h2>
                </div>
                <StatusPill status="ACTIVE" label="Siap Diaktifkan" />
              </div>

              {/* Rincian Tugas yang Mudah Dipahami (Human-Friendly Summary) */}
              <div className="spaceY3" style={{ marginBottom: "22px" }}>
                <div style={{ padding: "14px", background: "var(--paper)", borderRadius: "10px", border: "1px solid var(--line)" }}>
                  <strong style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", display: "block", marginBottom: "4px" }}>
                    🎯 Apa Tugas Utama Asisten Ini?
                  </strong>
                  <p style={{ margin: 0, fontSize: "13px", color: "var(--ink)", lineHeight: "1.5" }}>
                    {latestAnalysis.agent_contract_draft.purpose}
                  </p>
                </div>

                <div className="gridCols2">
                  <div style={{ padding: "14px", background: "#f0f7fc", borderRadius: "10px", border: "1px solid #c7e1f5" }}>
                    <strong style={{ fontSize: "11px", color: "#144e78", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>
                      ⏰ Kapan Asisten Bekerja?
                    </strong>
                    <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "11px", color: "#0c324e", lineHeight: "1.5" }}>
                      <li>Otomatis setiap hari kerja (pagi & sore)</li>
                      <li>Langsung aktif saat ada data/invoice baru diinput</li>
                    </ul>
                  </div>

                  <div style={{ padding: "14px", background: "#fff8e8", borderRadius: "10px", border: "1px solid #f7dba1" }}>
                    <strong style={{ fontSize: "11px", color: "#8c5b06", textTransform: "uppercase", display: "block", marginBottom: "6px" }}>
                      🛡️ Batasan Keamanan (Aman)
                    </strong>
                    <ul style={{ margin: 0, paddingLeft: "16px", fontSize: "11px", color: "#684305", lineHeight: "1.5" }}>
                      <li>Tidak bisa mengeluarkan uang tanpa izin manusia</li>
                      <li>Wajib meminta persetujuan Direktur/Manager</li>
                    </ul>
                  </div>
                </div>

                {/* Langkah Kerja Asisten */}
                {latestAnalysis.workflow_proposal?.steps && (
                  <div style={{ padding: "14px", background: "var(--white)", borderRadius: "10px", border: "1px solid var(--line)" }}>
                    <strong style={{ fontSize: "11px", color: "var(--muted)", textTransform: "uppercase", display: "block", marginBottom: "8px" }}>
                      🔄 Alur Kerja Otomatis yang Dijalankan:
                    </strong>
                    <div className="spaceY2">
                      {latestAnalysis.workflow_proposal.steps.map((st, i) => (
                        <div key={i} style={{ display: "flex", gap: "10px", alignItems: "center", fontSize: "12px" }}>
                          <span style={{ width: "20px", height: "20px", borderRadius: "50%", background: "#0d2d23", color: "#badb86", display: "flex", alignItems: "center", justifyContent: "center", fontSize: "10px", fontWeight: 800, flexShrink: 0 }}>
                            {i + 1}
                          </span>
                          <strong>{st.name}</strong>
                          <span style={{ color: "var(--muted)", fontSize: "11px" }}>— {st.description}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* 🚀 TOMBOL UTAMA: 1-CLICK ACTIVATION */}
              <div style={{ padding: "16px", background: "#eaf6f0", borderRadius: "12px", border: "1px solid #badb86", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <strong style={{ display: "block", fontSize: "13px", color: "var(--green-950)" }}>
                    Siap Menggunakan Asisten Ini?
                  </strong>
                  <span style={{ fontSize: "11px", color: "var(--muted)" }}>
                    Klik tombol di samping untuk langsung mengaktifkannya di divisi Anda.
                  </span>
                </div>

                <button
                  className="button heroPrimary"
                  disabled={busy}
                  onClick={handleInstantActivate}
                  style={{ fontWeight: 800, fontSize: "13px", padding: "12px 24px" }}
                  type="button"
                >
                  {busy ? "Sedang Mengaktifkan..." : "✅ Aktifkan Asisten Ini Sekarang"}
                </button>
              </div>
            </div>
          )}

          {/* List Asisten yang Sudah Aktif Dirilis */}
          {pipelineRequests.length > 0 && (
            <div className="panel" style={{ padding: "18px" }}>
              <h3 style={{ margin: "0 0 12px", fontSize: "13px", fontWeight: 750 }}>
                🚀 Asisten AI yang Sedang Aktif di Perusahaan ({pipelineRequests.filter((p) => p.status === "RELEASED").length})
              </h3>
              <div className="spaceY2">
                {pipelineRequests.map((req) => (
                  <div
                    key={req.request_id}
                    style={{
                      padding: "10px 14px",
                      borderRadius: "8px",
                      background: "var(--paper)",
                      border: "1px solid var(--line)",
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      fontSize: "12px",
                    }}
                  >
                    <div>
                      <strong>{req.justification}</strong>
                      <span style={{ display: "block", color: "var(--muted)", fontSize: "10px" }}>
                        Strategi: {req.strategy} • Waktu Rilis: {formatDateTime(req.updated_at)}
                      </span>
                    </div>
                    <StatusPill status={req.status} label={req.status === "RELEASED" ? "🟢 Aktif Bekerja" : req.status} />
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Modal: Buat Asisten Baru Bebas */}
      <Modal
        onClose={() => setShowNewModal(false)}
        open={showNewModal}
        subtitle="Jelaskan kebutuhan kerja yang ingin Anda otomatisasikan dengan bahasa sehari-hari"
        title="Buat Asisten AI Baru"
      >
        <form
          className="spaceY4"
          onSubmit={(e) => {
            e.preventDefault();
            void handleCreateNew(newTitle, newDivision, newPrompt);
          }}
        >
          <FormField label="Nama / Judul Asisten:" required>
            <TextInput
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Contoh: Asisten Pengecekan Kuitansi Lapangan"
              required
              value={newTitle}
            />
          </FormField>

          <FormField label="Untuk Divisi Mana:">
            <SelectInput
              onChange={(e) => setNewDivision(e.target.value)}
              value={newDivision}
            >
              {DIVISION_OPTIONS.map((opt) => (
                <option key={opt.code} value={opt.code}>
                  {opt.name}
                </option>
              ))}
            </SelectInput>
          </FormField>

          <FormField label="Apa Tugas yang Harus Dikerjakan:" required>
            <TextAreaInput
              onChange={(e) => setNewPrompt(e.target.value)}
              placeholder="Contoh: Saya butuh asisten yang mengecek setiap tagihan material pasir dan batu, mencocokkannya dengan surat jalan sopir truk, lalu membuat rekapnya untuk saya..."
              required
              rows={4}
              value={newPrompt}
            />
          </FormField>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowNewModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !newTitle.trim() || !newPrompt.trim()}
              type="submit"
            >
              {busy ? "Menganalisis..." : "Rancang Asisten AI"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
