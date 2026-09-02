"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  DataTable,
  FormField,
  Modal,
  SelectInput,
  StatsCard,
  StatusPill,
  TextAreaInput,
  TextInput,
  useToast,
} from "@/components/ui";
import {
  ApiError,
  assignSalesPic,
  createLead,
  getLeadInteractions,
  getLeads,
  recordSalesInteraction,
} from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { LeadRecord, SalesInteractionRecord } from "@/lib/types";

type InteractionOutcome = "qualified" | "reserved" | "follow_up" | "lost" | "exception";

function today(): string {
  const date = new Date();
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

function localDateTime(): string {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 16);
}

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Transaksi Sales belum dapat diproses.";
}

export default function SalesPage() {
  const { activeProjectId, principal, status, token } = useSession();
  const { error: toastError, success: toastSuccess } = useToast();

  const [leads, setLeads] = useState<LeadRecord[]>([]);
  const [interactions, setInteractions] = useState<SalesInteractionRecord[]>([]);
  const [interactionLeadId, setInteractionLeadId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"pipeline" | "interaction">("pipeline");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Modal
  const [showLeadModal, setShowLeadModal] = useState(false);

  // Forms
  const [leadForm, setLeadForm] = useState({
    fullName: "",
    phone: "",
    email: "",
    source: "WEBSITE",
    priority: "NORMAL" as "LOW" | "NORMAL" | "HIGH" | "CRITICAL",
    consent: true,
  });
  const [interactionForm, setInteractionForm] = useState({
    outcome: "follow_up" as InteractionOutcome,
    channel: "phone",
    notes: "",
    reservationReference: "",
    evidenceDocumentVersionId: "",
    qualificationResult: "WARM" as "HOT" | "WARM" | "COLD",
    lostReason: "",
    nextFollowUpAt: localDateTime(),
  });

  const selected = useMemo(
    () => leads.find((l) => l.lead_id === selectedId) || null,
    [leads, selectedId],
  );

  const visibleInteractions = useMemo(
    () => (interactionLeadId === selectedId ? interactions : []),
    [interactionLeadId, interactions, selectedId],
  );

  const canOperate = Boolean(
    principal &&
      principal.division_codes.includes("SALES_MARKETING") &&
      principal.roles.some((r) => r === "SALES" || r === "DIVISION_HEAD"),
  );

  const canInteractSelected = Boolean(
    canOperate &&
      selected &&
      principal &&
      (selected.assigned_user_id === principal.user_id || principal.roles.includes("DIVISION_HEAD")),
  );

  const loadData = useCallback(async () => {
    if (!token || !activeProjectId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const leadPage = await getLeads(token, activeProjectId);
      setLeads(leadPage.items);
      if (leadPage.items.length > 0 && !selectedId) {
        setSelectedId(leadPage.items[0].lead_id);
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, selectedId, token]);

  const loadInteractions = useCallback(
    async (leadId: string) => {
      if (!token) return;
      try {
        const history = await getLeadInteractions(token, leadId);
        setInteractions(history.items);
        setInteractionLeadId(leadId);
      } catch (err) {
        toastError(message(err));
      }
    },
    [toastError, token],
  );

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData, status]);

  useEffect(() => {
    if (!selectedId) return;
    const timer = window.setTimeout(() => void loadInteractions(selectedId), 0);
    return () => window.clearTimeout(timer);
  }, [loadInteractions, selectedId]);

  // Create New Lead
  const handleCreateLead = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !activeProjectId) return;
    setBusy(true);
    try {
      const created = await createLead(token, {
        project_id: activeProjectId,
        full_name: leadForm.fullName.trim(),
        phone: leadForm.phone.trim() || null,
        email: leadForm.email.trim() || null,
        source: leadForm.source,
        consent_recorded: leadForm.consent,
        priority: leadForm.priority,
      });
      setShowLeadModal(false);
      setLeadForm({
        fullName: "",
        phone: "",
        email: "",
        source: "WEBSITE",
        priority: "NORMAL",
        consent: true,
      });
      toastSuccess("Prospek baru berhasil ditambahkan ke pipeline.");
      await loadData();
      setSelectedId(created.lead_id);
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Assign PIC
  const handleAssignSelf = async () => {
    if (!token || !selected || !principal) return;
    setBusy(true);
    try {
      await assignSalesPic(token, selected.lead_id, principal.user_id);
      toastSuccess(`Prospek berhasil ditugaskan kepada ${principal.user_id}.`);
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Record Interaction
  const handleRecordInteraction = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !canInteractSelected) return;
    setBusy(true);
    try {
      await recordSalesInteraction(token, selected.lead_id, {
        outcome: interactionForm.outcome,
        channel: interactionForm.channel,
        notes: interactionForm.notes.trim(),
        evidence_reference:
          interactionForm.outcome === "reserved"
            ? interactionForm.reservationReference.trim()
            : null,
        evidence_document_version_id:
          interactionForm.outcome === "reserved"
            ? interactionForm.evidenceDocumentVersionId || null
            : null,
        reservation_reference:
          interactionForm.outcome === "reserved"
            ? interactionForm.reservationReference.trim()
            : null,
        reservation_date:
          interactionForm.outcome === "reserved"
            ? today()
            : null,
        qualification_result:
          interactionForm.outcome === "qualified"
            ? interactionForm.qualificationResult
            : null,
        lost_reason:
          interactionForm.outcome === "lost"
            ? interactionForm.lostReason.trim()
            : null,
        next_follow_up_at:
          interactionForm.outcome === "follow_up"
            ? new Date(interactionForm.nextFollowUpAt).toISOString()
            : null,
      });
      toastSuccess("Hasil interaksi follow-up berhasil dicatat.");
      setInteractionForm((prev) => ({ ...prev, notes: "" }));
      await loadData();
      if (selectedId) await loadInteractions(selectedId);
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Memuat modul Sales & Marketing..." />;
  }

  const qualifiedCount = leads.filter((l) => l.status === "QUALIFIED").length;
  const reservedCount = leads.filter((l) => l.status === "RESERVED").length;
  const newCount = leads.filter((l) => l.status === "NEW" || l.status === "CONTACTED").length;

  return (
    <div className="spaceY6">
      {/* Top Banner */}
      <header className="workspaceBanner">
        <div>
          <span className="workspaceBannerTag">
            Workspace Sales & Marketing · Core SRA
          </span>
          <h1 className="workspaceBannerTitle">
            Pipeline Prospek, Follow-Up & Reservasi Unit
          </h1>
          <p className="workspaceBannerSubtitle">
            Pemrosesan lead otomatis dan pencatatan booking reservasi unit properti.
          </p>
        </div>

        {canOperate && (
          <div className="workspaceActionGroup">
            <button
              className="button primary"
              onClick={() => setShowLeadModal(true)}
              type="button"
            >
              + Tambah Prospek (Lead Intake)
            </button>
          </div>
        )}
      </header>

      {error && <ErrorState message={error} retry={() => void loadData()} />}

      {/* Funnel Stats Cards */}
      <section className="gridCols4">
        <StatsCard
          badge={{ text: `${leads.length} Total`, variant: "info" }}
          subtitle="Semua prospek terdaftar pada proyek ini"
          title="Total Prospek"
          value={leads.length}
        />
        <StatsCard
          badge={{ text: `${newCount} Menunggu Respon`, variant: newCount > 0 ? "warning" : "success" }}
          subtitle="Prospek baru & sedang dalam kontak awal"
          title="Lead Baru & Kontak"
          value={newCount}
        />
        <StatsCard
          badge={{ text: `${qualifiedCount} Minat Tinggi`, variant: "info" }}
          subtitle="Prospek yang telah terkualifikasi minatnya"
          title="Terkualifikasi (Qualified)"
          value={qualifiedCount}
        />
        <StatsCard
          badge={{ text: `${reservedCount} Unit`, variant: "success" }}
          subtitle="Prospek yang telah booking tanda jadi / reservasi"
          title="Reservasi (Booking)"
          value={reservedCount}
        />
      </section>

      {/* Tabs Navigation */}
      <div className="tabBar">
        <button
          className={`tabButton ${activeTab === "pipeline" ? "active" : ""}`}
          onClick={() => setActiveTab("pipeline")}
          type="button"
        >
          🎯 Pipeline Prospek ({leads.length})
        </button>
        <button
          className={`tabButton ${activeTab === "interaction" ? "active" : ""}`}
          onClick={() => setActiveTab("interaction")}
          type="button"
        >
          📞 Interaksi & Follow-Up {selected ? `(${selected.full_name})` : ""}
        </button>
      </div>

      {/* Tab 1: Pipeline Leads */}
      {activeTab === "pipeline" && (
        <DataTable
          columns={[
            {
              header: "Nama Prospek",
              cell: (l: LeadRecord) => (
                <div>
                  <strong style={{ display: "block" }}>{l.full_name}</strong>
                  <span style={{ color: "var(--muted)", fontFamily: "monospace", fontSize: "11px" }}>{l.phone || "-"}</span>
                </div>
              ),
            },
            {
              header: "Sumber (Source)",
              cell: (l: LeadRecord) => (
                <span className="badge" style={{ background: "var(--paper)", border: "1px solid var(--line)", padding: "2px 8px", borderRadius: "6px" }}>
                  {l.source}
                </span>
              ),
            },
            {
              header: "Status Pipeline",
              cell: (l: LeadRecord) => <StatusPill status={l.status} />,
            },
            {
              header: "Waktu Daftar",
              cell: (l: LeadRecord) => (
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>{formatDateTime(l.created_at)}</span>
              ),
            },
          ]}
          data={leads}
          keyExtractor={(l) => l.lead_id}
          onRowClick={(l) => {
            setSelectedId(l.lead_id);
            setActiveTab("interaction");
          }}
          searchFilter={(l, q) =>
            l.full_name.toLowerCase().includes(q) ||
            (l.phone ? l.phone.toLowerCase().includes(q) : false) ||
            l.source.toLowerCase().includes(q) ||
            l.status.toLowerCase().includes(q)
          }
          searchPlaceholder="Cari nama prospek, nomor HP, sumber, status..."
        />
      )}

      {/* Tab 2: Detail & Interaksi Follow-Up */}
      {activeTab === "interaction" && (
        <div className="grid12">
          <div className="colSpan7">
            {!selected ? (
              <EmptyState
                description="Pilih salah satu prospek dari pipeline untuk mencatat interaksi follow-up."
                title="Pilih Prospek"
              />
            ) : (
              <div className="panel" style={{ padding: "22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: "14px", marginBottom: "16px" }}>
                  <div>
                    <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>
                      {selected.full_name}
                    </h2>
                    <span style={{ fontFamily: "monospace", color: "var(--muted)", fontSize: "11px" }}>
                      ID: {selected.lead_id}
                    </span>
                  </div>
                  <StatusPill status={selected.status} />
                </div>

                <div className="gridCols2" style={{ marginBottom: "16px" }}>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Nomor Telepon:</span>
                    <strong style={{ fontFamily: "monospace" }}>{selected.phone || "-"}</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Email:</span>
                    <span>{selected.email || "-"}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Sumber Prospek:</span>
                    <span>{selected.source}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>PIC Sales:</span>
                    <strong style={{ color: "var(--green-700)" }}>{selected.assigned_user_id || "Belum Ditugaskan"}</strong>
                  </div>
                </div>

                {!selected.assigned_user_id && canOperate && (
                  <div style={{ padding: "12px", background: "var(--paper)", borderRadius: "10px", display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px" }}>
                    <span style={{ fontSize: "12px", color: "var(--muted)" }}>Prospek ini belum memiliki penanggung jawab sales.</span>
                    <button className="button primary" disabled={busy} onClick={handleAssignSelf} type="button">
                      Tugaskan ke Saya
                    </button>
                  </div>
                )}

                {/* Interaction Timeline History */}
                <div style={{ borderTop: "1px solid var(--line)", paddingTop: "16px" }}>
                  <h3 style={{ margin: "0 0 12px", fontSize: "14px" }}>
                    Riwayat Follow-Up ({visibleInteractions.length})
                  </h3>

                  {visibleInteractions.length === 0 ? (
                    <p style={{ color: "var(--muted)", fontSize: "12px" }}>Belum ada interaksi yang tercatat untuk prospek ini.</p>
                  ) : (
                    <div className="spaceY3" style={{ maxHeight: "300px", overflowY: "auto" }}>
                      {visibleInteractions.map((item) => (
                        <div
                          key={item.interaction_id}
                          style={{ padding: "12px", background: "var(--paper)", borderRadius: "8px", border: "1px solid var(--line)", fontSize: "12px" }}
                        >
                          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                            <strong style={{ color: "var(--green-800)", textTransform: "capitalize" }}>
                              📱 {item.channel} — {item.outcome}
                            </strong>
                            <span style={{ color: "var(--muted)", fontSize: "10px" }}>
                              {formatDateTime(item.occurred_at)}
                            </span>
                          </div>
                          <p style={{ margin: "0 0 4px", color: "var(--ink)" }}>{item.notes}</p>
                          {item.evidence_reference && (
                            <span style={{ color: "var(--green-700)", fontFamily: "monospace", fontSize: "11px" }}>
                              Ref: {item.evidence_reference}
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="colSpan5 spaceY4">
            {selected && canInteractSelected && (
              <form
                className="panel"
                onSubmit={handleRecordInteraction}
                style={{ padding: "20px" }}
              >
                <h3 style={{ margin: "0 0 14px", fontSize: "15px", borderBottom: "1px solid var(--line)", paddingBottom: "8px" }}>
                  Catat Interaksi / Follow-Up
                </h3>

                <FormField label="Hasil Interaksi (Outcome):">
                  <SelectInput
                    onChange={(e) =>
                      setInteractionForm({
                        ...interactionForm,
                        outcome: e.target.value as InteractionOutcome,
                      })
                    }
                    value={interactionForm.outcome}
                  >
                    <option value="follow_up">Jadwalkan Follow-Up Ulang</option>
                    <option value="qualified">Kualifikasi Minat (Qualified)</option>
                    <option value="reserved">Reservasi Unit / Booking</option>
                    <option value="lost">Batal / Tidak Berminat (Lost)</option>
                  </SelectInput>
                </FormField>

                <FormField label="Kanal Komunikasi:">
                  <SelectInput
                    onChange={(e) =>
                      setInteractionForm({ ...interactionForm, channel: e.target.value })
                    }
                    value={interactionForm.channel}
                  >
                    <option value="phone">Panggilan Telepon</option>
                    <option value="whatsapp">Chat WhatsApp</option>
                    <option value="meeting">Pertemuan Langsung / Showroom</option>
                    <option value="email">Email</option>
                  </SelectInput>
                </FormField>

                {interactionForm.outcome === "reserved" && (
                  <FormField label="Nomor Referensi Booking / SPR:" required>
                    <TextInput
                      onChange={(e) =>
                        setInteractionForm({
                          ...interactionForm,
                          reservationReference: e.target.value,
                        })
                      }
                      placeholder="Contoh: RES-2026-UNIT-A10"
                      required
                      value={interactionForm.reservationReference}
                    />
                  </FormField>
                )}

                {interactionForm.outcome === "lost" && (
                  <FormField label="Alasan Pembatalan / Lost:" required>
                    <TextInput
                      onChange={(e) =>
                        setInteractionForm({ ...interactionForm, lostReason: e.target.value })
                      }
                      placeholder="Contoh: Lokasi kurang cocok"
                      required
                      value={interactionForm.lostReason}
                    />
                  </FormField>
                )}

                <FormField label="Catatan Follow-Up:" required>
                  <TextAreaInput
                    disabled={busy}
                    onChange={(e) =>
                      setInteractionForm({ ...interactionForm, notes: e.target.value })
                    }
                    placeholder="Tuliskan rangkuman percakapan dengan calon pembeli..."
                    required
                    value={interactionForm.notes}
                  />
                </FormField>

                <button
                  className="button primary"
                  disabled={busy || !interactionForm.notes.trim()}
                  style={{ width: "100%", marginTop: "8px" }}
                  type="submit"
                >
                  {busy ? "Menyimpan..." : "Simpan Catatan Interaksi"}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal: Tambah Prospek Baru */}
      <Modal
        onClose={() => setShowLeadModal(false)}
        open={showLeadModal}
        subtitle="Registrasi calon pembeli / lead baru ke sistem ALOS"
        title="Tambah Prospek (Lead Intake)"
      >
        <form className="spaceY4" onSubmit={handleCreateLead}>
          <FormField label="Nama Lengkap Prospek:" required>
            <TextInput
              onChange={(e) => setLeadForm({ ...leadForm, fullName: e.target.value })}
              placeholder="Contoh: Bpk. Hendra Gunawan"
              required
              value={leadForm.fullName}
            />
          </FormField>

          <div className="gridCols2">
            <FormField label="Nomor Telepon / WhatsApp:">
              <TextInput
                onChange={(e) => setLeadForm({ ...leadForm, phone: e.target.value })}
                placeholder="Contoh: 08123456789"
                value={leadForm.phone}
              />
            </FormField>

            <FormField label="Alamat Email:">
              <TextInput
                onChange={(e) => setLeadForm({ ...leadForm, email: e.target.value })}
                placeholder="Contoh: hendra@example.com"
                type="email"
                value={leadForm.email}
              />
            </FormField>
          </div>

          <div className="gridCols2">
            <FormField label="Sumber Prospek (Source):">
              <SelectInput
                onChange={(e) => setLeadForm({ ...leadForm, source: e.target.value })}
                value={leadForm.source}
              >
                <option value="WEBSITE">Website Resmi</option>
                <option value="EXHIBITION">Pameran Properti</option>
                <option value="REFERRAL">Rekomendasi (Referral)</option>
                <option value="SOCIAL_MEDIA">Instagram / Facebook Ads</option>
              </SelectInput>
            </FormField>

            <FormField label="Prioritas Minat:">
              <SelectInput
                onChange={(e) =>
                  setLeadForm({
                    ...leadForm,
                    priority: e.target.value as "LOW" | "NORMAL" | "HIGH" | "CRITICAL",
                  })
                }
                value={leadForm.priority}
              >
                <option value="NORMAL">Normal</option>
                <option value="HIGH">Tinggi (High Priority)</option>
                <option value="CRITICAL">Sangat Kritis (Hot Lead)</option>
                <option value="LOW">Rendah</option>
              </SelectInput>
            </FormField>
          </div>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowLeadModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !leadForm.fullName.trim()}
              type="submit"
            >
              {busy ? "Menyimpan..." : "Simpan Prospek"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
