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
  cancelPaymentRequest,
  createBudget,
  createPaymentRequest,
  decidePaymentRequest,
  getBudgets,
  getDocuments,
  getPaymentRequests,
  reconcilePayment,
  recordPayment,
} from "@/lib/api";
import { formatDateTime, shortId } from "@/lib/format";
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
  const { error: toastError, success: toastSuccess } = useToast();

  const [budgets, setBudgets] = useState<BudgetRecord[]>([]);
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [payments, setPayments] = useState<PaymentRequestRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"list" | "approval" | "payment" | "reconcile" | "budget">("list");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Modals
  const [showRequestModal, setShowRequestModal] = useState(false);
  const [showBudgetModal, setShowBudgetModal] = useState(false);

  // Forms
  const [budgetForm, setBudgetForm] = useState({ code: "", name: "", amount: "" });
  const [requestForm, setRequestForm] = useState({
    budgetId: "",
    documentVersionId: "",
    supportingDocumentVersionId: "",
    payeeName: "",
    vendorReference: "",
    categoryCode: "GENERAL",
    purpose: "",
    amount: "",
    requestedPaymentDate: today(),
  });
  const [decision, setDecision] = useState<PaymentDecision>("APPROVED");
  const [decisionReason, setDecisionReason] = useState("");
  const [cancellationReason, setCancellationReason] = useState("");
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
    () => payments.find((p) => p.payment_request_id === selectedId) || null,
    [payments, selectedId],
  );

  const canOperate = Boolean(
    principal &&
      principal.division_codes.includes("FINANCE") &&
      principal.roles.some((r) => r === "FINANCE" || r === "DIVISION_HEAD"),
  );

  const canDecideSelected = Boolean(
    principal &&
      selected &&
      ((selected.approval_route === "FINANCE_REVIEWER" &&
        principal.division_codes.includes("FINANCE") &&
        principal.roles.some((r) => r === "FINANCE" || r === "DIVISION_HEAD")) ||
        (selected.approval_route === "DIVISION_HEAD" &&
          principal.roles.includes("DIVISION_HEAD")) ||
        (selected.approval_route === "DIRECTOR" && principal.roles.includes("DIRECTOR"))),
  );

  const canCancelSelected = Boolean(
    principal &&
      selected &&
      ["DRAFT", "EXCEPTION_HOLD", "REVISION_REQUESTED"].includes(selected.status) &&
      canOperate,
  );

  const loadData = useCallback(async () => {
    if (!token || !activeProjectId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [budgetPage, docPage, paymentPage] = await Promise.all([
        getBudgets(token, activeProjectId),
        getDocuments(token, activeProjectId),
        getPaymentRequests(token, activeProjectId),
      ]);
      setBudgets(budgetPage.items);
      setDocuments(docPage.items);
      setPayments(paymentPage.items);
      if (budgetPage.items.length > 0 && !requestForm.budgetId) {
        setRequestForm((prev) => ({ ...prev, budgetId: budgetPage.items[0].budget_id }));
      }
      if (docPage.items.length > 0 && !requestForm.documentVersionId) {
        setRequestForm((prev) => ({ ...prev, documentVersionId: docPage.items[0].document_version_id }));
      }
      if (paymentPage.items.length > 0 && !selectedId) {
        setSelectedId(paymentPage.items[0].payment_request_id);
      }
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }, [activeProjectId, requestForm.budgetId, requestForm.documentVersionId, selectedId, token]);

  useEffect(() => {
    if (status !== "authenticated") return;
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, [loadData, status]);

  // Submit New Budget
  const handleCreateBudget = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !activeProjectId) return;
    setBusy(true);
    try {
      await createBudget(token, {
        project_id: activeProjectId,
        code: budgetForm.code.trim().toUpperCase(),
        name: budgetForm.name.trim(),
        allocated_amount: budgetForm.amount.trim(),
        currency: "IDR",
      });
      setBudgetForm({ code: "", name: "", amount: "" });
      setShowBudgetModal(false);
      toastSuccess("Alokasi anggaran baru berhasil dibuat.");
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Submit New Payment Request
  const handleCreatePaymentRequest = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !activeProjectId) return;
    const docId = requestForm.documentVersionId || documents[0]?.document_version_id;
    if (!docId) {
      toastError("Dokumen invoice/bukti tagihan wajib dilampirkan.");
      return;
    }
    setBusy(true);
    try {
      const created = await createPaymentRequest(token, {
        project_id: activeProjectId,
        budget_id: requestForm.budgetId,
        document_version_id: docId,
        supporting_document_version_ids: requestForm.supportingDocumentVersionId
          ? [requestForm.supportingDocumentVersionId]
          : undefined,
        payee_name: requestForm.payeeName.trim(),
        vendor_reference: requestForm.vendorReference.trim() || null,
        category_code: requestForm.categoryCode,
        purpose: requestForm.purpose.trim(),
        amount: requestForm.amount.trim(),
        currency: "IDR",
        requested_payment_date: requestForm.requestedPaymentDate,
      });
      setShowRequestModal(false);
      toastSuccess("Permohonan pembayaran berhasil diajukan ke antrean approval.");
      await loadData();
      setSelectedId(created.payment_request_id);
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Submit Approval Decision
  const handleDecide = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !canDecideSelected) return;
    setBusy(true);
    try {
      await decidePaymentRequest(token, selected.payment_request_id, decision, decisionReason.trim());
      setDecisionReason("");
      toastSuccess(`Keputusan ${decision} berhasil dicatat.`);
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Record Payment
  const handleRecordPayment = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !canOperate) return;
    const docId = paymentForm.evidenceDocumentVersionId || documents[0]?.document_version_id || selected.document_version_id;
    setBusy(true);
    try {
      await recordPayment(token, selected.payment_request_id, {
        payment_reference: paymentForm.reference.trim(),
        amount: paymentForm.amount.trim() || selected.amount,
        currency: selected.currency,
        paid_at: new Date().toISOString(),
        evidence_document_version_id: docId,
      });
      toastSuccess("Pembayaran berhasil dicatat. Transaksi siap untuk rekonsiliasi.");
      setPaymentForm({ reference: "", amount: "", paidAt: "", evidenceDocumentVersionId: "" });
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Reconcile Payment
  const handleReconcile = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !canOperate) return;
    setBusy(true);
    try {
      await reconcilePayment(token, selected.payment_request_id, {
        transaction_reference: reconciliationForm.reference.trim(),
        transaction_amount: reconciliationForm.amount.trim() || selected.amount,
        currency: selected.currency,
      });
      toastSuccess("Rekonsiliasi bank deterministik berhasil diselesaikan.");
      setReconciliationForm({ reference: "", amount: "" });
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  // Cancel Payment Request
  const handleCancel = async (e: FormEvent) => {
    e.preventDefault();
    if (!token || !selected || !canCancelSelected) return;
    setBusy(true);
    try {
      await cancelPaymentRequest(token, selected.payment_request_id, cancellationReason.trim());
      setCancellationReason("");
      toastSuccess("Payment request berhasil dibatalkan dan komitmen anggaran dilepas.");
      await loadData();
    } catch (err) {
      toastError(message(err));
    } finally {
      setBusy(false);
    }
  };

  if (loading) {
    return <LoadingState label="Memuat modul operasional keuangan..." />;
  }

  const pendingPayments = payments.filter((p) => p.status === "PENDING_APPROVAL");
  const approvedPayments = payments.filter((p) => p.status === "APPROVED");
  const reconciledPayments = payments.filter((p) => p.status === "RECONCILED");

  return (
    <div className="spaceY6">
      {/* Top Banner */}
      <header className="workspaceBanner">
        <div>
          <span className="workspaceBannerTag">
            Workspace Keuangan · Core FRA
          </span>
          <h1 className="workspaceBannerTitle">
            Manajemen Anggaran, Pembayaran & Rekonsiliasi
          </h1>
          <p className="workspaceBannerSubtitle">
            Pemeriksaan dokumen invoice/pajak, persetujuan bertingkat, dan rekonsiliasi deterministik.
          </p>
        </div>

        {canOperate && (
          <div className="workspaceActionGroup">
            <button
              className="button secondary"
              onClick={() => setShowBudgetModal(true)}
              type="button"
            >
              + Alokasi Anggaran
            </button>
            <button
              className="button primary"
              onClick={() => setShowRequestModal(true)}
              type="button"
            >
              + Ajukan Payment Request
            </button>
          </div>
        )}
      </header>

      {error && <ErrorState message={error} retry={() => void loadData()} />}

      {/* Stats Cards */}
      <section className="gridCols4">
        <StatsCard
          badge={{ text: `${budgets.length} Akun`, variant: "info" }}
          subtitle="Pos anggaran aktif pada proyek ini"
          title="Total Pos Anggaran"
          value={budgets.length}
        />
        <StatsCard
          badge={{ text: `${pendingPayments.length} Menunggu`, variant: pendingPayments.length > 0 ? "warning" : "success" }}
          subtitle="Permohonan pembayaran menunggu persetujuan"
          title="Menunggu Approval"
          value={pendingPayments.length}
        />
        <StatsCard
          badge={{ text: `${approvedPayments.length} Siap Bayar`, variant: "info" }}
          subtitle="Permohonan siap dibayarkan ke vendor"
          title="Disetujui (Approved)"
          value={approvedPayments.length}
        />
        <StatsCard
          badge={{ text: `${reconciledPayments.length} Cocok`, variant: "success" }}
          subtitle="Transaksi terverifikasi dengan mutasi bank"
          title="Rekonsiliasi Selesai"
          value={reconciledPayments.length}
        />
      </section>

      {/* Tabs Navigation */}
      <div className="tabBar">
        <button
          className={`tabButton ${activeTab === "list" ? "active" : ""}`}
          onClick={() => setActiveTab("list")}
          type="button"
        >
          📋 Daftar Permohonan Pembayaran ({payments.length})
        </button>
        <button
          className={`tabButton ${activeTab === "approval" ? "active" : ""}`}
          onClick={() => setActiveTab("approval")}
          type="button"
        >
          🛡️ Persetujuan & Keputusan
        </button>
        <button
          className={`tabButton ${activeTab === "payment" ? "active" : ""}`}
          onClick={() => setActiveTab("payment")}
          type="button"
        >
          💳 Catat Pembayaran
        </button>
        <button
          className={`tabButton ${activeTab === "reconcile" ? "active" : ""}`}
          onClick={() => setActiveTab("reconcile")}
          type="button"
        >
          🔄 Rekonsiliasi Bank Deterministik
        </button>
        <button
          className={`tabButton ${activeTab === "budget" ? "active" : ""}`}
          onClick={() => setActiveTab("budget")}
          type="button"
        >
          📊 Pos Anggaran ({budgets.length})
        </button>
      </div>

      {/* Tab 1: Payment Request List */}
      {activeTab === "list" && (
        <DataTable
          columns={[
            {
              header: "ID Permohonan",
              cell: (p: PaymentRequestRecord) => (
                <span style={{ fontFamily: "monospace", color: "var(--green-700)", fontWeight: 700 }}>
                  {shortId(p.payment_request_id)}
                </span>
              ),
            },
            {
              header: "Penerima (Payee)",
              cell: (p: PaymentRequestRecord) => (
                <div>
                  <strong style={{ display: "block" }}>{p.payee_name}</strong>
                  <span style={{ fontSize: "11px", color: "var(--muted)" }}>{p.purpose}</span>
                </div>
              ),
            },
            {
              header: "Nominal (IDR)",
              cell: (p: PaymentRequestRecord) => (
                <span style={{ fontFamily: "monospace", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  Rp {Number(p.amount).toLocaleString("id-ID")}
                </span>
              ),
            },
            {
              header: "Rute Approval",
              cell: (p: PaymentRequestRecord) => (
                <span style={{ color: "var(--muted)", fontFamily: "monospace", fontSize: "11px" }}>
                  {p.approval_route || "-"}
                </span>
              ),
            },
            {
              header: "Status",
              cell: (p: PaymentRequestRecord) => <StatusPill status={p.status} />,
            },
            {
              header: "Tanggal Pengajuan",
              cell: (p: PaymentRequestRecord) => (
                <span style={{ color: "var(--muted)", fontSize: "11px" }}>
                  {formatDateTime(p.created_at)}
                </span>
              ),
            },
          ]}
          data={payments}
          keyExtractor={(p) => p.payment_request_id}
          onRowClick={(p) => {
            setSelectedId(p.payment_request_id);
            setActiveTab("approval");
          }}
          searchFilter={(p, q) =>
            p.payee_name.toLowerCase().includes(q) ||
            p.purpose.toLowerCase().includes(q) ||
            p.status.toLowerCase().includes(q)
          }
          searchPlaceholder="Cari nama vendor, tujuan, atau status..."
        />
      )}

      {/* Tab 2: Persetujuan & Keputusan */}
      {activeTab === "approval" && (
        <div className="grid12">
          <div className="colSpan7">
            {!selected ? (
              <EmptyState
                description="Pilih salah satu permohonan pembayaran dari tabel untuk melihat rincian persetujuan."
                title="Pilih Payment Request"
              />
            ) : (
              <div className="panel" style={{ padding: "22px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", borderBottom: "1px solid var(--line)", paddingBottom: "14px", marginBottom: "16px" }}>
                  <div>
                    <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>
                      Rincian Payment Request
                    </h2>
                    <span style={{ fontFamily: "monospace", color: "var(--muted)", fontSize: "11px" }}>
                      ID: {selected.payment_request_id}
                    </span>
                  </div>
                  <StatusPill status={selected.status} />
                </div>

                <div className="gridCols2" style={{ marginBottom: "16px" }}>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Penerima (Payee):</span>
                    <strong style={{ fontSize: "14px" }}>{selected.payee_name}</strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Nominal:</span>
                    <strong style={{ color: "var(--green-800)", fontSize: "18px", fontFamily: "Georgia, serif" }}>
                      Rp {Number(selected.amount).toLocaleString("id-ID")}
                    </strong>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Kategori:</span>
                    <span>{selected.category_code}</span>
                  </div>
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Rute Kewenangan:</span>
                    <span style={{ fontFamily: "monospace", color: "var(--green-700)" }}>{selected.approval_route || "-"}</span>
                  </div>
                </div>

                <div style={{ marginBottom: "14px" }}>
                  <span style={{ color: "var(--muted)", fontSize: "11px", display: "block", marginBottom: "4px" }}>Tujuan Pembayaran:</span>
                  <p style={{ margin: 0, padding: "12px", background: "var(--paper)", borderRadius: "8px", border: "1px solid var(--line)", fontSize: "12px", lineHeight: "1.5" }}>
                    {selected.purpose}
                  </p>
                </div>

                {selected.vendor_reference && (
                  <div>
                    <span style={{ color: "var(--muted)", fontSize: "11px", display: "block" }}>Nomor Invoice/Faktur:</span>
                    <span style={{ fontFamily: "monospace" }}>{selected.vendor_reference}</span>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="colSpan5 spaceY4">
            {selected && canDecideSelected && (
              <form
                className="panel"
                onSubmit={handleDecide}
                style={{ padding: "20px" }}
              >
                <h3 style={{ margin: "0 0 14px", fontSize: "15px", borderBottom: "1px solid var(--line)", paddingBottom: "8px" }}>
                  Formulir Keputusan Approval
                </h3>

                <FormField label="Keputusan:">
                  <SelectInput
                    onChange={(e) => setDecision(e.target.value as PaymentDecision)}
                    value={decision}
                  >
                    <option value="APPROVED">Persetujuan (APPROVED)</option>
                    <option value="REVISION_REQUESTED">Minta Revisi (REVISION_REQUESTED)</option>
                    <option value="REJECTED">Tolak Permohonan (REJECTED)</option>
                  </SelectInput>
                </FormField>

                <FormField label="Alasan / Catatan Keputusan:">
                  <TextAreaInput
                    disabled={busy}
                    onChange={(e) => setDecisionReason(e.target.value)}
                    placeholder="Wajib diisi jika revisi/ditolak atau sebagai audit note..."
                    required={decision !== "APPROVED"}
                    value={decisionReason}
                  />
                </FormField>

                <button
                  className={`button ${decision === "APPROVED" ? "primary" : "secondary"}`}
                  disabled={busy}
                  style={{ width: "100%", marginTop: "8px" }}
                  type="submit"
                >
                  {busy ? "Menyimpan..." : `Konfirmasi Keputusan (${decision})`}
                </button>
              </form>
            )}

            {selected && canCancelSelected && (
              <form
                className="panel"
                onSubmit={handleCancel}
                style={{ padding: "18px", border: "1px solid #f6beba", background: "#fdf0ee" }}
              >
                <h3 style={{ margin: "0 0 4px", fontSize: "14px", color: "var(--red)" }}>Batalkan Permohonan</h3>
                <p style={{ margin: "0 0 10px", fontSize: "11px", color: "var(--muted)" }}>
                  Membatalkan payment request dan melepaskan komitmen anggaran yang tertahan.
                </p>
                <FormField label="Alasan Pembatalan:">
                  <TextAreaInput
                    disabled={busy}
                    onChange={(e) => setCancellationReason(e.target.value)}
                    placeholder="Masukkan alasan pembatalan transaksi..."
                    required
                    value={cancellationReason}
                  />
                </FormField>
                <button
                  className="button"
                  disabled={busy || !cancellationReason.trim()}
                  style={{ width: "100%", background: "var(--red)", color: "#fff" }}
                  type="submit"
                >
                  {busy ? "Membatalkan..." : "Batalkan Payment Request"}
                </button>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Tab 3: Catat Pembayaran */}
      {activeTab === "payment" && (
        <div className="panel" style={{ maxWidth: "600px", margin: "0 auto", padding: "24px" }}>
          <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>
            Pencatatan Pembayaran Nyata (Bank Transfer)
          </h2>
          <p style={{ color: "var(--muted)", fontSize: "12px", marginBottom: "18px" }}>
            Hanya permohonan yang berstatus <StatusPill status="APPROVED" /> yang dapat dicatatkan buktinya.
          </p>

          <form className="spaceY4" onSubmit={handleRecordPayment}>
            <FormField label="Pilih Payment Request Disetujui:">
              <SelectInput
                onChange={(e) => setSelectedId(e.target.value)}
                value={selectedId || ""}
              >
                <option value="">-- Pilih Transaksi --</option>
                {payments
                  .filter((p) => p.status === "APPROVED")
                  .map((p) => (
                    <option key={p.payment_request_id} value={p.payment_request_id}>
                      {p.payee_name} — Rp {Number(p.amount).toLocaleString("id-ID")} ({shortId(p.payment_request_id)})
                    </option>
                  ))}
              </SelectInput>
            </FormField>

            <FormField label="Nomor Referensi Bank / No. Bukti Transfer:">
              <TextInput
                disabled={busy}
                onChange={(e) => setPaymentForm({ ...paymentForm, reference: e.target.value })}
                placeholder="Contoh: TRF-BCA-88992109"
                required
                value={paymentForm.reference}
              />
            </FormField>

            <FormField label="Nominal Terbayar:">
              <TextInput
                disabled={busy}
                onChange={(e) => setPaymentForm({ ...paymentForm, amount: e.target.value })}
                placeholder={selected ? selected.amount : "Nominal IDR"}
                value={paymentForm.amount}
              />
            </FormField>

            <button
              className="button primary"
              disabled={busy || !selectedId || !paymentForm.reference.trim()}
              style={{ width: "100%", marginTop: "12px" }}
              type="submit"
            >
              {busy ? "Menyimpan..." : "Simpan Catatan Pembayaran"}
            </button>
          </form>
        </div>
      )}

      {/* Tab 4: Rekonsiliasi Bank */}
      {activeTab === "reconcile" && (
        <div className="panel" style={{ maxWidth: "600px", margin: "0 auto", padding: "24px" }}>
          <h2 style={{ margin: "0 0 4px", fontSize: "18px", fontFamily: "Georgia, serif" }}>
            Rekonsiliasi Bank Deterministik (Core FRA)
          </h2>
          <p style={{ color: "var(--muted)", fontSize: "12px", marginBottom: "18px" }}>
            Mencocokkan catatan transaksi sistem dengan mutasi rekening koran bank secara presisi.
          </p>

          <form className="spaceY4" onSubmit={handleReconcile}>
            <FormField label="Pilih Transaksi Terbayar:">
              <SelectInput
                onChange={(e) => setSelectedId(e.target.value)}
                value={selectedId || ""}
              >
                <option value="">-- Pilih Transaksi --</option>
                {payments
                  .filter((p) => p.status === "PAID")
                  .map((p) => (
                    <option key={p.payment_request_id} value={p.payment_request_id}>
                      {p.payee_name} — Rp {Number(p.amount).toLocaleString("id-ID")} ({shortId(p.payment_request_id)})
                    </option>
                  ))}
              </SelectInput>
            </FormField>

            <FormField label="Nomor Referensi Mutasi Bank:">
              <TextInput
                disabled={busy}
                onChange={(e) =>
                  setReconciliationForm({ ...reconciliationForm, reference: e.target.value })
                }
                placeholder="Contoh: MUT-BCA-992812"
                required
                value={reconciliationForm.reference}
              />
            </FormField>

            <button
              className="button primary"
              disabled={busy || !selectedId || !reconciliationForm.reference.trim()}
              style={{ width: "100%", marginTop: "12px" }}
              type="submit"
            >
              {busy ? "Mencocokkan..." : "Jalankan Rekonsiliasi Deterministik"}
            </button>
          </form>
        </div>
      )}

      {/* Tab 5: Pos Anggaran */}
      {activeTab === "budget" && (
        <DataTable
          columns={[
            {
              header: "Kode Anggaran",
              cell: (b: BudgetRecord) => (
                <span style={{ fontFamily: "monospace", color: "var(--green-700)", fontWeight: 700 }}>
                  {b.code}
                </span>
              ),
            },
            {
              header: "Nama Pos Anggaran",
              cell: (b: BudgetRecord) => <strong>{b.name}</strong>,
            },
            {
              header: "Total Alokasi (IDR)",
              cell: (b: BudgetRecord) => (
                <span style={{ fontFamily: "monospace", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  Rp {Number(b.allocated_amount).toLocaleString("id-ID")}
                </span>
              ),
            },
            {
              header: "Terkomitmen (Committed)",
              cell: (b: BudgetRecord) => (
                <span style={{ fontFamily: "monospace", color: "var(--amber)", fontVariantNumeric: "tabular-nums" }}>
                  Rp {Number(b.committed_amount).toLocaleString("id-ID")}
                </span>
              ),
            },
            {
              header: "Sisa Tersedia (Available)",
              cell: (b: BudgetRecord) => (
                <span style={{ fontFamily: "monospace", color: "var(--green-800)", fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
                  Rp {Number(b.available_amount).toLocaleString("id-ID")}
                </span>
              ),
            },
          ]}
          data={budgets}
          keyExtractor={(b) => b.budget_id}
          searchFilter={(b, q) =>
            b.code.toLowerCase().includes(q) || b.name.toLowerCase().includes(q)
          }
          searchPlaceholder="Cari kode atau nama pos anggaran..."
        />
      )}

      {/* Modal: Ajukan Payment Request Baru */}
      <Modal
        onClose={() => setShowRequestModal(false)}
        open={showRequestModal}
        subtitle="Permohonan pembayaran operasional dan pengadaan vendor"
        title="Ajukan Payment Request Baru"
      >
        <form className="spaceY4" onSubmit={handleCreatePaymentRequest}>
          <FormField label="Pos Anggaran (Budget):" required>
            <SelectInput
              onChange={(e) => setRequestForm({ ...requestForm, budgetId: e.target.value })}
              required
              value={requestForm.budgetId}
            >
              {budgets.map((b) => (
                <option key={b.budget_id} value={b.budget_id}>
                  {b.code} — {b.name} (Sisa: Rp {Number(b.available_amount).toLocaleString("id-ID")})
                </option>
              ))}
            </SelectInput>
          </FormField>

          <FormField label="Nama Penerima / Vendor (Payee):" required>
            <TextInput
              onChange={(e) => setRequestForm({ ...requestForm, payeeName: e.target.value })}
              placeholder="Contoh: PT Semen Perkasa Makmur"
              required
              value={requestForm.payeeName}
            />
          </FormField>

          <FormField label="Nomor Referensi Vendor / No. Invoice:">
            <TextInput
              onChange={(e) =>
                setRequestForm({ ...requestForm, vendorReference: e.target.value })
              }
              placeholder="Contoh: INV-SPM-2026-0041"
              value={requestForm.vendorReference}
            />
          </FormField>

          <FormField label="Nominal Pembayaran (IDR):" required>
            <TextInput
              onChange={(e) => setRequestForm({ ...requestForm, amount: e.target.value })}
              placeholder="Contoh: 15000000"
              required
              type="number"
              value={requestForm.amount}
            />
          </FormField>

          <FormField label="Tujuan Pembayaran (Justifikasi):" required>
            <TextAreaInput
              onChange={(e) => setRequestForm({ ...requestForm, purpose: e.target.value })}
              placeholder="Jelaskan kebutuhan pengadaan atau pembayaran..."
              required
              value={requestForm.purpose}
            />
          </FormField>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowRequestModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !requestForm.amount || !requestForm.payeeName.trim()}
              type="submit"
            >
              {busy ? "Memproses..." : "Ajukan Permohonan"}
            </button>
          </div>
        </form>
      </Modal>

      {/* Modal: Buat Alokasi Anggaran Baru */}
      <Modal
        onClose={() => setShowBudgetModal(false)}
        open={showBudgetModal}
        subtitle="Alokasi pagu anggaran baru untuk divisi / proyek"
        title="Buat Alokasi Anggaran Baru"
      >
        <form className="spaceY4" onSubmit={handleCreateBudget}>
          <FormField label="Kode Anggaran:" required>
            <TextInput
              onChange={(e) => setBudgetForm({ ...budgetForm, code: e.target.value })}
              placeholder="Contoh: BDG-PROJ-01-OP"
              required
              value={budgetForm.code}
            />
          </FormField>

          <FormField label="Nama Pos Anggaran:" required>
            <TextInput
              onChange={(e) => setBudgetForm({ ...budgetForm, name: e.target.value })}
              placeholder="Contoh: Operasional Lapangan & Logistik"
              required
              value={budgetForm.name}
            />
          </FormField>

          <FormField label="Total Pagu Anggaran (IDR):" required>
            <TextInput
              onChange={(e) => setBudgetForm({ ...budgetForm, amount: e.target.value })}
              placeholder="Contoh: 100000000"
              required
              type="number"
              value={budgetForm.amount}
            />
          </FormField>

          <div style={{ display: "flex", justifyContent: "flex-end", gap: "10px", marginTop: "18px", borderTop: "1px solid var(--line)", paddingTop: "14px" }}>
            <button
              className="button secondary"
              onClick={() => setShowBudgetModal(false)}
              type="button"
            >
              Batal
            </button>
            <button
              className="button primary"
              disabled={busy || !budgetForm.code.trim() || !budgetForm.amount}
              type="submit"
            >
              {busy ? "Menyimpan..." : "Simpan Anggaran"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
