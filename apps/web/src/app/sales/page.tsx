"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  assignSalesPic,
  createLead,
  getDocuments,
  getLeadInteractions,
  getLeads,
  recordSalesInteraction,
} from "@/lib/api";
import { formatDateTime, humanizeCode, shortId } from "@/lib/format";
import type { DocumentRecord, LeadRecord, SalesInteractionRecord } from "@/lib/types";

type InteractionOutcome = "qualified" | "reserved" | "follow_up" | "exception";

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Transaksi Sales belum dapat diproses.";
}

export default function SalesPage() {
  const { activeProjectId, principal, status, token } = useSession();
  const [leads, setLeads] = useState<LeadRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [interactions, setInteractions] = useState<SalesInteractionRecord[]>([]);
  const [interactionLeadId, setInteractionLeadId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [leadForm, setLeadForm] = useState({
    fullName: "",
    phone: "",
    email: "",
    source: "",
    priority: "NORMAL" as "LOW" | "NORMAL" | "HIGH" | "CRITICAL",
    consent: false,
  });
  const [interactionForm, setInteractionForm] = useState({
    outcome: "follow_up" as InteractionOutcome,
    channel: "phone",
    notes: "",
    reservationReference: "",
    evidenceDocumentVersionId: "",
  });

  const selected = useMemo(
    () => leads.find((lead) => lead.lead_id === selectedId) || null,
    [leads, selectedId],
  );
  const visibleInteractions = useMemo(
    () => (interactionLeadId === selectedId ? interactions : []),
    [interactionLeadId, interactions, selectedId],
  );
  const canOperate = Boolean(
    principal
    && principal.division_codes.includes("SALES_MARKETING")
    && principal.roles.some((role) => role === "SALES" || role === "DIVISION_HEAD"),
  );

  const loadData = useCallback(async () => {
    if (!token || !activeProjectId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [leadPage, documentPage] = await Promise.all([
        getLeads(token, activeProjectId),
        getDocuments(token, activeProjectId),
      ]);
      setLeads(leadPage.items);
      setDocuments(documentPage.items);
      setSelectedId((current) => (
        leadPage.items.some((lead) => lead.lead_id === current)
          ? current
          : leadPage.items[0]?.lead_id || null
      ));
    } catch (loadError) {
      setError(message(loadError));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const refresh = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(refresh);
  }, [loadData, status]);

  useEffect(() => {
    if (!token || !selectedId) {
      return;
    }
    let active = true;
    getLeadInteractions(token, selectedId)
      .then((page) => {
        if (active) {
          setInteractions(page.items);
          setInteractionLeadId(selectedId);
        }
      })
      .catch((interactionError) => {
        if (active) setFeedback(message(interactionError));
      });
    return () => {
      active = false;
    };
  }, [selectedId, token]);

  async function submitLead(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !activeProjectId || !canOperate) return;
    setFeedback(null);
    if (!leadForm.phone.trim() && !leadForm.email.trim()) {
      setFeedback("Isi minimal satu kontak: telepon atau email.");
      return;
    }
    if (!leadForm.consent) {
      setFeedback("Persetujuan pemrosesan data lead wajib dicatat.");
      return;
    }
    setBusy(true);
    try {
      const created = await createLead(token, {
        project_id: activeProjectId,
        full_name: leadForm.fullName.trim(),
        phone: leadForm.phone.trim() || null,
        email: leadForm.email.trim() || null,
        source: leadForm.source.trim(),
        consent_recorded: true,
        priority: leadForm.priority,
      });
      setLeadForm({
        fullName: "",
        phone: "",
        email: "",
        source: "",
        priority: "NORMAL",
        consent: false,
      });
      await loadData();
      setSelectedId(created.lead_id);
      setFeedback("Lead berhasil dicatat dan divalidasi oleh SLA.");
    } catch (submitError) {
      setFeedback(message(submitError));
    } finally {
      setBusy(false);
    }
  }

  async function assignToMe() {
    if (!token || !selected || !principal || !canOperate) return;
    setBusy(true);
    setFeedback(null);
    try {
      await assignSalesPic(token, selected.workflow_run_id, principal.user_id);
      await loadData();
      setFeedback("Lead berhasil ditugaskan kepada Anda dan follow-up telah dijadwalkan.");
    } catch (assignmentError) {
      setFeedback(message(assignmentError));
    } finally {
      setBusy(false);
    }
  }

  async function submitInteraction(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selected || !canOperate) return;
    setFeedback(null);
    if (
      interactionForm.outcome === "reserved"
      && (!interactionForm.reservationReference || !interactionForm.evidenceDocumentVersionId)
    ) {
      setFeedback("Reservasi wajib memiliki nomor referensi dan dokumen evidence.");
      return;
    }
    setBusy(true);
    try {
      await recordSalesInteraction(token, selected.workflow_run_id, {
        outcome: interactionForm.outcome,
        channel: interactionForm.channel.trim(),
        notes: interactionForm.notes.trim(),
        evidence_reference: null,
        evidence_document_version_id:
          interactionForm.evidenceDocumentVersionId || null,
        reservation_reference:
          interactionForm.outcome === "reserved"
            ? interactionForm.reservationReference.trim()
            : null,
      });
      setInteractionForm({
        outcome: "follow_up",
        channel: "phone",
        notes: "",
        reservationReference: "",
        evidenceDocumentVersionId: "",
      });
      await loadData();
      const page = await getLeadInteractions(token, selected.lead_id);
      setInteractions(page.items);
      setInteractionLeadId(selected.lead_id);
      setFeedback("Interaksi tersimpan dan status workflow telah diperbarui.");
    } catch (interactionError) {
      setFeedback(message(interactionError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Sales & Marketing · FLOW-001</p>
          <h1>Lead sampai Reservasi</h1>
          <p>Kelola intake, penugasan, follow-up, pipeline, dan reservasi dengan evidence serta audit trail.</p>
        </div>
        <button className="button secondary" disabled={loading} onClick={() => void loadData()} type="button">Perbarui data</button>
      </header>

      {!activeProjectId ? (
        <EmptyState title="Pilih proyek terlebih dahulu" description="Gunakan pemilih proyek di bagian atas untuk membuka transaksi Sales." />
      ) : null}
      {activeProjectId && loading ? <LoadingState label="Memuat pipeline Sales…" /> : null}
      {activeProjectId && !loading && error ? <ErrorState message={error} retry={() => void loadData()} /> : null}

      {activeProjectId && !loading && !error ? (
        <>
          {feedback ? <div className="transactionFeedback" role="status">{feedback}</div> : null}
          {canOperate ? (
            <section className="panel transactionCreatePanel">
              <div className="panelHeader"><div><p className="eyebrow">Intake terkendali</p><h2>Catat lead baru</h2></div></div>
              <form className="transactionForm" onSubmit={submitLead}>
                <label>Nama lengkap<input maxLength={160} minLength={2} onChange={(event) => setLeadForm({ ...leadForm, fullName: event.target.value })} required value={leadForm.fullName} /></label>
                <label>Telepon<input maxLength={32} onChange={(event) => setLeadForm({ ...leadForm, phone: event.target.value })} value={leadForm.phone} /></label>
                <label>Email<input maxLength={254} onChange={(event) => setLeadForm({ ...leadForm, email: event.target.value })} type="email" value={leadForm.email} /></label>
                <label>Sumber lead<input maxLength={80} minLength={2} onChange={(event) => setLeadForm({ ...leadForm, source: event.target.value })} required value={leadForm.source} /></label>
                <label>Prioritas<select onChange={(event) => setLeadForm({ ...leadForm, priority: event.target.value as typeof leadForm.priority })} value={leadForm.priority}><option>NORMAL</option><option>HIGH</option><option>CRITICAL</option><option>LOW</option></select></label>
                <label className="checkField"><input checked={leadForm.consent} onChange={(event) => setLeadForm({ ...leadForm, consent: event.target.checked })} type="checkbox" /><span>Consent pemrosesan data telah dicatat</span></label>
                <button className="button primary" disabled={busy} type="submit">{busy ? "Memproses…" : "Simpan lead"}</button>
              </form>
            </section>
          ) : null}

          <div className="transactionLayout">
            <section className="panel">
              <div className="panelHeader"><div><p className="eyebrow">Pipeline</p><h2>Daftar lead</h2></div><span className="resultCount">{leads.length} lead</span></div>
              {!leads.length ? <EmptyState title="Belum ada lead" description="Lead pada proyek ini akan tampil di sini." /> : (
                <div className="transactionRecordList">
                  {leads.map((lead) => (
                    <button className={lead.lead_id === selectedId ? "selected" : ""} key={lead.lead_id} onClick={() => setSelectedId(lead.lead_id)} type="button">
                      <span><strong>{lead.full_name}</strong><small>{lead.phone || lead.email || "Tanpa kontak"}</small></span>
                      <span><b className="statusBadge">{humanizeCode(lead.status)}</b><small>{shortId(lead.lead_id)}</small></span>
                    </button>
                  ))}
                </div>
              )}
            </section>

            <section className="panel transactionDetail">
              <div className="panelHeader"><div><p className="eyebrow">Workflow detail</p><h2>{selected?.full_name || "Pilih lead"}</h2></div>{selected ? <span className="statusBadge large">{humanizeCode(selected.workflow_status)}</span> : null}</div>
              {selected ? (
                <div className="transactionDetailBody">
                  <dl className="detailGrid">
                    <div><dt>Langkah</dt><dd>{humanizeCode(selected.current_step)}</dd></div>
                    <div><dt>Sales PIC</dt><dd>{selected.assigned_user_id ? shortId(selected.assigned_user_id) : "Belum ditugaskan"}</dd></div>
                    <div><dt>Sumber</dt><dd>{selected.source}</dd></div>
                    <div><dt>Dibuat</dt><dd>{formatDateTime(selected.created_at)}</dd></div>
                    <div><dt>Workflow Run</dt><dd title={selected.workflow_run_id}>{shortId(selected.workflow_run_id)}</dd></div>
                    <div><dt>Consent</dt><dd>{selected.consent_recorded ? "Tercatat" : "Belum"}</dd></div>
                  </dl>

                  {canOperate && selected.current_step === "sales-assignment" ? (
                    <button className="button primary" disabled={busy} onClick={() => void assignToMe()} type="button">Tugaskan kepada saya</button>
                  ) : null}

                  {canOperate && selected.current_step === "interaction-review" ? (
                    <form className="actionPanel" onSubmit={submitInteraction}>
                      <div><p className="eyebrow">Catatan human-in-the-loop</p><h3>Catat hasil interaksi</h3></div>
                      <div className="fieldGrid">
                        <label>Outcome<select onChange={(event) => setInteractionForm({ ...interactionForm, outcome: event.target.value as InteractionOutcome })} value={interactionForm.outcome}><option value="follow_up">Follow-up</option><option value="qualified">Qualified</option><option value="reserved">Reserved</option><option value="exception">Exception</option></select></label>
                        <label>Kanal<input maxLength={40} minLength={2} onChange={(event) => setInteractionForm({ ...interactionForm, channel: event.target.value })} required value={interactionForm.channel} /></label>
                      </div>
                      <label>Catatan<textarea maxLength={2000} minLength={3} onChange={(event) => setInteractionForm({ ...interactionForm, notes: event.target.value })} required rows={3} value={interactionForm.notes} /></label>
                      {interactionForm.outcome === "reserved" ? (
                        <div className="fieldGrid">
                          <label>Referensi reservasi<input maxLength={120} onChange={(event) => setInteractionForm({ ...interactionForm, reservationReference: event.target.value })} required value={interactionForm.reservationReference} /></label>
                          <label>Dokumen evidence<select onChange={(event) => setInteractionForm({ ...interactionForm, evidenceDocumentVersionId: event.target.value })} required value={interactionForm.evidenceDocumentVersionId}><option value="">Pilih dokumen</option>{documents.map((document) => <option key={document.document_version_id} value={document.document_version_id}>{document.logical_name} · v{document.version_number}</option>)}</select></label>
                        </div>
                      ) : null}
                      <button className="button primary" disabled={busy} type="submit">{busy ? "Memproses…" : "Simpan interaksi"}</button>
                    </form>
                  ) : null}

                  <section className="interactionHistory">
                    <h3>Riwayat interaksi</h3>
                    {!visibleInteractions.length ? <p className="muted">Belum ada interaksi tercatat.</p> : visibleInteractions.map((interaction) => (
                      <article key={interaction.interaction_id}><div><strong>{humanizeCode(interaction.outcome)}</strong><span>{interaction.channel} · {formatDateTime(interaction.occurred_at)}</span></div><p>{interaction.notes}</p></article>
                    ))}
                  </section>
                </div>
              ) : <EmptyState title="Pilih lead" description="Pilih lead dari daftar untuk melihat workflow dan tindakan yang tersedia." />}
            </section>
          </div>
        </>
      ) : null}
    </>
  );
}
