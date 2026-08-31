"use client";

import { type FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/page-state";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  createBudget,
  createPaymentRequest,
  decidePaymentRequest,
  getBudgets,
  getDocuments,
  getPaymentRequests,
  reconcilePayment,
  recordPayment,
} from "@/lib/api";
import { formatDateTime, humanizeCode, shortId } from "@/lib/format";
import type { BudgetRecord, DocumentRecord, PaymentRequestRecord } from "@/lib/types";

type PaymentDecision = "APPROVED" | "REJECTED" | "REVISION_REQUESTED";

function message(error: unknown): string {
  return error instanceof ApiError ? error.message : "Transaksi Keuangan belum dapat diproses.";
}

function today(): string {
  const date = new Date();
  const offset = date.getTimezoneOffset() * 60_000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
}

export default function FinancePage() {
  const { activeProjectId, principal, status, token } = useSession();
  const [budgets, setBudgets] = useState<BudgetRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [payments, setPayments] = useState<PaymentRequestRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [budgetForm, setBudgetForm] = useState({ code: "", name: "", amount: "" });
  const [requestForm, setRequestForm] = useState({
    budgetId: "",
    documentVersionId: "",
    payeeName: "",
    purpose: "",
    amount: "",
    requestedPaymentDate: today(),
  });
  const [decision, setDecision] = useState<PaymentDecision>("APPROVED");
  const [decisionReason, setDecisionReason] = useState("");
  const [paymentForm, setPaymentForm] = useState({
    reference: "",
    amount: "",
    paidAt: "",
    evidenceDocumentVersionId: "",
  });
  const [reconciliationForm, setReconciliationForm] = useState({
    reference: "",
    amount: "",
  });

  const selected = useMemo(
    () => payments.find((payment) => payment.payment_request_id === selectedId) || null,
    [payments, selectedId],
  );
  const canOperate = Boolean(
    principal
    && principal.division_codes.includes("FINANCE")
    && principal.roles.some((role) => role === "FINANCE" || role === "DIVISION_HEAD"),
  );
  const isOwnRequest = Boolean(
    principal && selected && principal.user_id === selected.requester_user_id,
  );

  const loadData = useCallback(async () => {
    if (!token || !activeProjectId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [budgetPage, paymentPage, documentPage] = await Promise.all([
        getBudgets(token, activeProjectId),
        getPaymentRequests(token, activeProjectId),
        getDocuments(token, activeProjectId),
      ]);
      setBudgets(budgetPage.items);
      setPayments(paymentPage.items);
      setDocuments(documentPage.items);
      setSelectedId((current) => (
        paymentPage.items.some((payment) => payment.payment_request_id === current)
          ? current
          : paymentPage.items[0]?.payment_request_id || null
      ));
      setRequestForm((current) => ({
        ...current,
        budgetId: budgetPage.items.some((budget) => budget.budget_id === current.budgetId)
          ? current.budgetId
          : budgetPage.items[0]?.budget_id || "",
        documentVersionId: documentPage.items.some(
          (document) => document.document_version_id === current.documentVersionId,
        ) ? current.documentVersionId : documentPage.items[0]?.document_version_id || "",
      }));
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

  async function submitBudget(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !activeProjectId || !canOperate) return;
    setBusy(true);
    setFeedback(null);
    try {
      await createBudget(token, {
        project_id: activeProjectId,
        code: budgetForm.code.trim().toUpperCase(),
        name: budgetForm.name.trim(),
        currency: "IDR",
        allocated_amount: budgetForm.amount,
      });
      setBudgetForm({ code: "", name: "", amount: "" });
      await loadData();
      setFeedback("Budget aktif berhasil dibuat dan dicatat pada audit trail.");
    } catch (submitError) {
      setFeedback(message(submitError));
    } finally {
      setBusy(false);
    }
  }

  async function submitPaymentRequest(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !activeProjectId || !canOperate) return;
    setBusy(true);
    setFeedback(null);
    try {
      const created = await createPaymentRequest(token, {
        project_id: activeProjectId,
        budget_id: requestForm.budgetId,
        document_version_id: requestForm.documentVersionId,
        payee_name: requestForm.payeeName.trim(),
        purpose: requestForm.purpose.trim(),
        amount: requestForm.amount,
        currency: "IDR",
        requested_payment_date: requestForm.requestedPaymentDate,
      });
      setRequestForm((current) => ({
        ...current,
        payeeName: "",
        purpose: "",
        amount: "",
        requestedPaymentDate: today(),
      }));
      await loadData();
      setSelectedId(created.payment_request_id);
      setFeedback("Payment request lolos pemeriksaan awal dan masuk ke approval.");
    } catch (submitError) {
      setFeedback(message(submitError));
    } finally {
      setBusy(false);
    }
  }

  async function submitDecision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selected || !canOperate) return;
    setBusy(true);
    setFeedback(null);
    try {
      await decidePaymentRequest(
        token,
        selected.payment_request_id,
        decision,
        decisionReason.trim(),
      );
      setDecisionReason("");
      await loadData();
      setFeedback("Keputusan approval tersimpan dengan separation of duties.");
    } catch (decisionError) {
      setFeedback(message(decisionError));
    } finally {
      setBusy(false);
    }
  }

  async function submitPayment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selected || !canOperate) return;
    const paidAt = new Date(paymentForm.paidAt);
    if (Number.isNaN(paidAt.getTime())) {
      setFeedback("Waktu pembayaran tidak valid.");
      return;
    }
    setBusy(true);
    setFeedback(null);
    try {
      await recordPayment(token, selected.payment_request_id, {
        payment_reference: paymentForm.reference.trim(),
        amount: paymentForm.amount,
        currency: selected.currency,
        paid_at: paidAt.toISOString(),
        evidence_document_version_id: paymentForm.evidenceDocumentVersionId,
      });
      setReconciliationForm({
        reference: paymentForm.reference.trim(),
        amount: paymentForm.amount,
      });
      setPaymentForm({ reference: "", amount: "", paidAt: "", evidenceDocumentVersionId: "" });
      await loadData();
      setFeedback("Pembayaran tercatat dan menunggu rekonsiliasi FRA.");
    } catch (paymentError) {
      setFeedback(message(paymentError));
    } finally {
      setBusy(false);
    }
  }

  async function submitReconciliation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !selected || !canOperate) return;
    setBusy(true);
    setFeedback(null);
    try {
      const result = await reconcilePayment(token, selected.payment_request_id, {
        transaction_reference: reconciliationForm.reference.trim(),
        transaction_amount: reconciliationForm.amount,
        currency: selected.currency,
      });
      await loadData();
      setFeedback(
        result.reconciliation_status === "MATCHED"
          ? "Rekonsiliasi cocok dan workflow telah selesai."
          : "Rekonsiliasi berbeda; exception dan CAPA perlu ditindaklanjuti.",
      );
    } catch (reconciliationError) {
      setFeedback(message(reconciliationError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Keuangan · FLOW-002</p>
          <h1>Payment sampai Rekonsiliasi</h1>
          <p>Kelola anggaran, evidence, approval, pembayaran, dan rekonsiliasi secara deterministik.</p>
        </div>
        <button className="button secondary" disabled={loading} onClick={() => void loadData()} type="button">Perbarui data</button>
      </header>

      {!activeProjectId ? <EmptyState title="Pilih proyek terlebih dahulu" description="Gunakan pemilih proyek di bagian atas untuk membuka transaksi Keuangan." /> : null}
      {activeProjectId && loading ? <LoadingState label="Memuat transaksi Keuangan…" /> : null}
      {activeProjectId && !loading && error ? <ErrorState message={error} retry={() => void loadData()} /> : null}

      {activeProjectId && !loading && !error ? (
        <>
          {feedback ? <div className="transactionFeedback" role="status">{feedback}</div> : null}
          {canOperate ? (
            <div className="transactionCreateGrid">
              <section className="panel">
                <div className="panelHeader"><div><p className="eyebrow">Budget control</p><h2>Buat budget</h2></div></div>
                <form className="formStack transactionPanelBody" onSubmit={submitBudget}>
                  <div className="fieldGrid"><label>Kode<input maxLength={32} minLength={2} onChange={(event) => setBudgetForm({ ...budgetForm, code: event.target.value })} required value={budgetForm.code} /></label><label>Alokasi IDR<input min="0.01" onChange={(event) => setBudgetForm({ ...budgetForm, amount: event.target.value })} required step="0.01" type="number" value={budgetForm.amount} /></label></div>
                  <label>Nama budget<input maxLength={160} minLength={3} onChange={(event) => setBudgetForm({ ...budgetForm, name: event.target.value })} required value={budgetForm.name} /></label>
                  <button className="button primary" disabled={busy} type="submit">Simpan budget</button>
                </form>
              </section>
              <section className="panel">
                <div className="panelHeader"><div><p className="eyebrow">Request intake</p><h2>Buat payment request</h2></div></div>
                <form className="formStack transactionPanelBody" onSubmit={submitPaymentRequest}>
                  <div className="fieldGrid"><label>Budget<select onChange={(event) => setRequestForm({ ...requestForm, budgetId: event.target.value })} required value={requestForm.budgetId}><option value="">Pilih budget</option>{budgets.map((budget) => <option key={budget.budget_id} value={budget.budget_id}>{budget.code} · tersedia {budget.available_amount}</option>)}</select></label><label>Dokumen pendukung<select onChange={(event) => setRequestForm({ ...requestForm, documentVersionId: event.target.value })} required value={requestForm.documentVersionId}><option value="">Pilih dokumen</option>{documents.map((document) => <option key={document.document_version_id} value={document.document_version_id}>{document.logical_name} · v{document.version_number}</option>)}</select></label></div>
                  <div className="fieldGrid"><label>Penerima<input maxLength={200} minLength={2} onChange={(event) => setRequestForm({ ...requestForm, payeeName: event.target.value })} required value={requestForm.payeeName} /></label><label>Jumlah IDR<input min="0.01" onChange={(event) => setRequestForm({ ...requestForm, amount: event.target.value })} required step="0.01" type="number" value={requestForm.amount} /></label></div>
                  <label>Tujuan pembayaran<textarea maxLength={1000} minLength={3} onChange={(event) => setRequestForm({ ...requestForm, purpose: event.target.value })} required rows={2} value={requestForm.purpose} /></label>
                  <label>Tanggal pembayaran diminta<input onChange={(event) => setRequestForm({ ...requestForm, requestedPaymentDate: event.target.value })} required type="date" value={requestForm.requestedPaymentDate} /></label>
                  <button className="button primary" disabled={busy || !budgets.length || !documents.length} type="submit">Ajukan pembayaran</button>
                </form>
              </section>
            </div>
          ) : null}

          <div className="transactionLayout">
            <section className="panel">
              <div className="panelHeader"><div><p className="eyebrow">Payment queue</p><h2>Daftar permintaan</h2></div><span className="resultCount">{payments.length} permintaan</span></div>
              {!payments.length ? <EmptyState title="Belum ada payment request" description="Permintaan pada proyek ini akan tampil di sini." /> : (
                <div className="transactionRecordList">
                  {payments.map((payment) => (
                    <button className={payment.payment_request_id === selectedId ? "selected" : ""} key={payment.payment_request_id} onClick={() => setSelectedId(payment.payment_request_id)} type="button"><span><strong>{payment.payee_name}</strong><small>IDR {payment.amount} · {payment.purpose}</small></span><span><b className="statusBadge">{humanizeCode(payment.status)}</b><small>{shortId(payment.payment_request_id)}</small></span></button>
                  ))}
                </div>
              )}
            </section>

            <section className="panel transactionDetail">
              <div className="panelHeader"><div><p className="eyebrow">Workflow detail</p><h2>{selected?.payee_name || "Pilih permintaan"}</h2></div>{selected ? <span className="statusBadge large">{humanizeCode(selected.status)}</span> : null}</div>
              {selected ? (
                <div className="transactionDetailBody">
                  <dl className="detailGrid">
                    <div><dt>Jumlah</dt><dd>{selected.currency} {selected.amount}</dd></div>
                    <div><dt>Langkah</dt><dd>{humanizeCode(selected.current_step)}</dd></div>
                    <div><dt>Budget</dt><dd>{shortId(selected.budget_id)}</dd></div>
                    <div><dt>Pemohon</dt><dd>{shortId(selected.requester_user_id)}</dd></div>
                    <div><dt>Budget tersedia</dt><dd>{selected.budget_available ? "Ya" : "Tidak"}</dd></div>
                    <div><dt>Dibuat</dt><dd>{formatDateTime(selected.created_at)}</dd></div>
                  </dl>

                  {canOperate && !isOwnRequest && selected.current_step === "finance-approval" ? (
                    <form className="actionPanel" onSubmit={submitDecision}><div><p className="eyebrow">Human approval</p><h3>Keputusan pembayaran</h3><p>Pemohon tidak dapat menyetujui permintaannya sendiri.</p></div><label>Keputusan<select onChange={(event) => setDecision(event.target.value as PaymentDecision)} value={decision}><option>APPROVED</option><option>REJECTED</option><option>REVISION_REQUESTED</option></select></label><label>Alasan<textarea maxLength={2000} minLength={3} onChange={(event) => setDecisionReason(event.target.value)} required rows={3} value={decisionReason} /></label><button className="button primary" disabled={busy} type="submit">Simpan keputusan</button></form>
                  ) : null}

                  {canOperate && isOwnRequest && selected.current_step === "finance-approval" ? (
                    <div className="readOnlyNotice"><p><strong>Menunggu approver lain</strong><span>Separation of duties melarang pemohon menyetujui permintaannya sendiri.</span></p></div>
                  ) : null}

                  {canOperate && selected.current_step === "payment-action" ? (
                    <form className="actionPanel" onSubmit={submitPayment}><div><p className="eyebrow">Payment evidence</p><h3>Catat pembayaran</h3></div><div className="fieldGrid"><label>Referensi transaksi<input maxLength={160} minLength={3} onChange={(event) => setPaymentForm({ ...paymentForm, reference: event.target.value })} required value={paymentForm.reference} /></label><label>Jumlah<input min="0.01" onChange={(event) => setPaymentForm({ ...paymentForm, amount: event.target.value })} required step="0.01" type="number" value={paymentForm.amount} /></label></div><div className="fieldGrid"><label>Waktu dibayar<input onChange={(event) => setPaymentForm({ ...paymentForm, paidAt: event.target.value })} required type="datetime-local" value={paymentForm.paidAt} /></label><label>Dokumen bukti<select onChange={(event) => setPaymentForm({ ...paymentForm, evidenceDocumentVersionId: event.target.value })} required value={paymentForm.evidenceDocumentVersionId}><option value="">Pilih dokumen</option>{documents.map((document) => <option key={document.document_version_id} value={document.document_version_id}>{document.logical_name} · v{document.version_number}</option>)}</select></label></div><button className="button primary" disabled={busy} type="submit">Catat pembayaran</button></form>
                  ) : null}

                  {canOperate && selected.current_step === "reconciliation" ? (
                    <form className="actionPanel" onSubmit={submitReconciliation}><div><p className="eyebrow">FRA deterministic check</p><h3>Rekonsiliasi transaksi</h3><p>Reference, amount, dan currency dibandingkan tanpa LLM.</p></div><div className="fieldGrid"><label>Referensi bank<input maxLength={160} minLength={3} onChange={(event) => setReconciliationForm({ ...reconciliationForm, reference: event.target.value })} required value={reconciliationForm.reference} /></label><label>Jumlah transaksi<input min="0.01" onChange={(event) => setReconciliationForm({ ...reconciliationForm, amount: event.target.value })} required step="0.01" type="number" value={reconciliationForm.amount} /></label></div><button className="button primary" disabled={busy} type="submit">Jalankan rekonsiliasi</button></form>
                  ) : null}

                  {!canOperate ? <div className="readOnlyNotice"><p><strong>Akses monitoring</strong><span>Anda dapat melihat transaksi tanpa menjalankan tindakan Keuangan.</span></p></div> : null}
                </div>
              ) : <EmptyState title="Pilih payment request" description="Pilih permintaan untuk melihat tahapan dan tindakan yang tersedia." />}
            </section>
          </div>
        </>
      ) : null}
    </>
  );
}
