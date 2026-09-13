"use client";

import { useCallback, useEffect, useState } from "react";

import { apiMessage, apiRequest } from "@/lib/api-client";
import { type DashboardModuleKey } from "@/lib/dashboard-modules";
import { type SessionActor } from "@/lib/governance";
import { TaskViews } from "@/components/tasks/task-views";
import { ApprovalViews } from "@/components/approvals/approval-views";
import { ReportViews } from "@/components/reports/report-views";
import { FindingViews } from "@/components/findings/finding-views";
import {
  type OperationalDashboard,
  type ProposedAction,
  type ReportDefinition,
} from "@/lib/operational";

type OperationalModule = Extract<DashboardModuleKey, "tasks" | "approvals" | "findings" | "reports">;

export function OperationalModuleDashboard({
  actor,
  module,
}: {
  actor: SessionActor;
  module: OperationalModule;
}) {
  const [dashboard, setDashboard] = useState<OperationalDashboard | null>(null);
  const [definitions, setDefinitions] = useState<ReportDefinition[]>([]);
  const [proposedActions, setProposedActions] = useState<ProposedAction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextDashboard, nextDefinitions, nextActions] = await Promise.all([
        apiRequest<OperationalDashboard>("/api/v1/dashboard/operational"),
        module === "reports"
          ? apiRequest<ReportDefinition[]>("/api/v1/report-definitions")
          : Promise.resolve([]),
        module === "approvals"
          ? apiRequest<ProposedAction[]>("/api/v1/proposed-actions")
          : Promise.resolve([]),
      ]);
      setDashboard(nextDashboard);
      setDefinitions(nextDefinitions);
      setProposedActions(nextActions);
    } catch (failure) {
      setError(apiMessage(failure));
    } finally {
      setLoading(false);
    }
  }, [module]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void load(); }, 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  const mutation = async (work: () => Promise<unknown>, success: string) => {
    setError("");
    setNotice("");
    try {
      await work();
      setNotice(success);
      await load();
    } catch (failure) {
      setError(apiMessage(failure));
    }
  };

  if (loading && !dashboard) {
    return <section className="alos-content"><div className="alos-operation-state">Memuat data operasional sesuai scope Anda…</div></section>;
  }

  if (module === "tasks") {
    return (
      <section className="alos-dash-content" aria-label="Tugas ALOS">
        {error ? <div className="alos-operation-banner error" role="alert">{error}</div> : null}
        {notice ? <div className="alos-operation-banner success" role="status">{notice}</div> : null}
        <TaskViews
          actor={actor}
          isLoading={loading}
          mutate={mutation}
          onRefresh={() => void load()}
          operational={dashboard}
          tasks={dashboard?.tasks ?? []}
        />
      </section>
    );
  }

  if (module === "approvals") {
    return (
      <section className="alos-dash-content" aria-label="Pusat Persetujuan ALOS">
        {error ? <div className="alos-operation-banner error" role="alert">{error}</div> : null}
        {notice ? <div className="alos-operation-banner success" role="status">{notice}</div> : null}
        <ApprovalViews
          actor={actor}
          approvals={dashboard?.approvals ?? []}
          isLoading={loading}
          mutate={mutation}
          onRefresh={() => void load()}
          operational={dashboard}
          proposedActions={proposedActions}
        />
      </section>
    );
  }

  if (module === "reports") {
    return (
      <section className="alos-dash-content" aria-label="Laporan ALOS">
        {error ? <div className="alos-operation-banner error" role="alert">{error}</div> : null}
        {notice ? <div className="alos-operation-banner success" role="status">{notice}</div> : null}
        <ReportViews
          actor={actor}
          definitions={definitions}
          isLoading={loading}
          onCreateDefinition={async ({ name, period, scope, templateKey }) => {
            await mutation(
              () =>
                apiRequest("/api/v1/report-definitions", {
                  method: "POST",
                  body: JSON.stringify({
                    workspace_id: actor.workspace_ids[0],
                    division_code: scope === "COMPANY" ? null : actor.division_codes[0] ?? null,
                    name,
                    template_key: templateKey,
                    scope,
                    period,
                    sections: ["summary", "tasks", "findings"],
                    data_sources: ["tasks", "findings", "approvals"],
                    review_required: true,
                    recipient_user_ids: [],
                  }),
                }),
              "Definisi laporan berhasil dibuat.",
            );
            await load();
          }}
          onDeleteReport={async (reportId) => {
            await mutation(
              () => apiRequest(`/api/v1/reports/${reportId}`, { method: "DELETE" }),
              "Laporan berhasil dihapus.",
            );
            await load();
          }}
          onGenerateReport={async (defId) => {
            await mutation(
              () =>
                apiRequest(`/api/v1/report-definitions/${defId}/generate`, {
                  method: "POST",
                  body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
                }),
              "Laporan DRAFT berhasil dihasilkan dengan provenance.",
            );
            await load();
          }}
          operational={dashboard}
        />
      </section>
    );
  }

  if (module === "findings") {
    return (
      <section className="alos-dash-content" aria-label="Temuan ALOS">
        {error ? <div className="alos-operation-banner error" role="alert">{error}</div> : null}
        {notice ? <div className="alos-operation-banner success" role="status">{notice}</div> : null}
        <FindingViews
          actor={actor}
          findings={dashboard?.findings ?? []}
          onCreateFinding={async (data) => {
            await mutation(
              () =>
                apiRequest("/api/v1/findings", {
                  method: "POST",
                  body: JSON.stringify({
                    workspace_id: actor.workspace_ids[0],
                    division_code: actor.division_codes[0] ?? null,
                    source_kind: "GENESIS",
                    title: data.title,
                    description: data.description,
                    severity: data.severity,
                    recommendation: data.description,
                    due_date: data.dueDate ? `${data.dueDate}T17:00:00Z` : null,
                  }),
                }),
              "Temuan berhasil dicatat.",
            );
          }}
          onDeleteFinding={async (findingId) => {
            await mutation(
              () => apiRequest(`/api/v1/findings/${findingId}`, { method: "DELETE" }),
              "Temuan berhasil dihapus.",
            );
          }}
          onUpdateStatus={async (findingId, status, note) => {
            await mutation(
              () =>
                apiRequest(`/api/v1/findings/${findingId}/status`, {
                  method: "PATCH",
                  body: JSON.stringify({
                    status,
                    resolution: note ?? "Status updated via ALOS Temuan workspace.",
                  }),
                }),
              "Status temuan berhasil diperbarui.",
            );
          }}
          operational={dashboard}
        />
      </section>
    );
  }

  return null;
}

