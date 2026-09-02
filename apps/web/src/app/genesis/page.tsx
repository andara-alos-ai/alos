"use client";

import { type FormEvent, useMemo, useState } from "react";

import { useSession } from "@/components/session-provider";
import { ApiError, createGenesisConversation, sendGenesisMessage } from "@/lib/api";
import type { GenesisAnalyzeResult, GenesisConversationView } from "@/lib/types";

const divisions = [
  ["FINANCE", "Keuangan"],
  ["SALES_MARKETING", "Sales & Marketing"],
  ["PROPERTY", "Property"],
  ["HR", "HR"],
  ["LEGAL", "Legal"],
  ["IT", "IT"],
] as const;

function messageFor(error: unknown): string {
  return error instanceof ApiError ? error.message : "Genesis belum dapat memproses requirement ini.";
}

function latestAnalysis(conversation: GenesisConversationView | null): GenesisAnalyzeResult | null {
  return conversation?.messages.map((message) => message.analysis_result).filter(Boolean).at(-1) ?? null;
}

export default function GenesisPage() {
  const { activeProjectId, token } = useSession();
  const [title, setTitle] = useState("");
  const [division, setDivision] = useState("FINANCE");
  const [requirement, setRequirement] = useState("");
  const [sourceReference, setSourceReference] = useState("ALOS-SP-SYNTHETIC-PILOT@1.0.0");
  const [conversation, setConversation] = useState<GenesisConversationView | null>(null);
  const [followUp, setFollowUp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const analysis = useMemo(() => latestAnalysis(conversation), [conversation]);
  const sourceReferences = sourceReference.split(",").map((value) => value.trim()).filter(Boolean);

  async function createDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !title.trim() || !requirement.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const result = await createGenesisConversation(
        {
          title: title.trim(),
          project_id: activeProjectId,
          initial_prompt: requirement.trim(),
          source_references: sourceReferences,
          division_code: division,
        },
        token,
      );
      setConversation(result);
      setFollowUp("");
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setBusy(false);
    }
  }

  async function refineDraft(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token || !conversation || !followUp.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setConversation(await sendGenesisMessage(
        conversation.conversation_id,
        { message_text: followUp.trim(), source_references: sourceReferences, division_code: division },
        token,
      ));
      setFollowUp("");
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="spaceY6">
      <header className="pageHeader">
        <div>
          <p className="eyebrow">Genesis · Design Time</p>
          <h1>Rancang Agent dari Requirement</h1>
          <p>Genesis menghasilkan Blueprint dan Agent Contract DRAFT. Ia tidak dapat approve, release, atau mengaktifkan agent ini sendiri.</p>
        </div>
      </header>

      <section className="panel">
        <form className="formStack" onSubmit={(event) => void createDraft(event)}>
          <label>Nama agent<input onChange={(event) => setTitle(event.target.value)} placeholder="Contoh: Daily Brief Agent" required value={title} /></label>
          <label>Context divisi<select onChange={(event) => setDivision(event.target.value)} value={division}>{divisions.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label>
          <label>Source reference<input onChange={(event) => setSourceReference(event.target.value)} required value={sourceReference} /></label>
          <label>Requirement natural language<textarea onChange={(event) => setRequirement(event.target.value)} placeholder="Jelaskan tujuan, input, output, bukti, batasan, dan tindakan yang dilarang." required rows={6} value={requirement} /></label>
          <button className="button primary" disabled={busy} type="submit">{busy ? "Genesis sedang menganalisis…" : "Buat draft Blueprint & Contract"}</button>
        </form>
        {error ? <p className="formError" role="alert">{error}</p> : null}
      </section>

      {analysis ? (
        <section className="spaceY4">
          <section className="panel">
            <p className="eyebrow">Draft only · {analysis.llm_result_status}</p>
            <h2>{analysis.agent_contract_draft.name}</h2>
            <p>{analysis.agent_contract_draft.purpose}</p>
            <dl>
              <dt>Strategi</dt><dd>{analysis.strategy} — {analysis.strategy_justification}</dd>
              <dt>Owner</dt><dd>{analysis.business_owner}</dd>
              <dt>Model/provider</dt><dd>{analysis.llm_metadata.provider} / {analysis.llm_metadata.model ?? "not executed"}</dd>
              <dt>Effect</dt><dd>{analysis.production_effect ? "blocked" : "no production effect"}</dd>
            </dl>
          </section>
          <section className="panel">
            <h2>Contract boundary</h2>
            <div className="gridCols2">
              <div><strong>Allowed tools</strong><ul>{analysis.agent_contract_draft.tools_allowed.map((tool) => <li key={tool}>{tool}</li>)}</ul></div>
              <div><strong>Forbidden actions</strong><ul>{analysis.agent_contract_draft.forbidden_actions.map((action) => <li key={action}>{action}</li>)}</ul></div>
            </div>
            <strong>Validation</strong>
            <ul>{analysis.validations.map((validation) => <li key={validation.code}>{validation.passed ? "PASS" : "BLOCKED"} — {validation.message}</li>)}</ul>
          </section>
          <section className="panel">
            <h2>Human checkpoint diperlukan</h2>
            <p>Draft belum dapat dijalankan. Reviewer bisnis dan teknis yang berbeda harus memeriksa contract, test evidence, permission, cost policy, dan release proposal melalui jalur governance.</p>
          </section>
          <section className="panel">
            <form className="formStack" onSubmit={(event) => void refineDraft(event)}>
              <label>Tambahkan klarifikasi<textarea onChange={(event) => setFollowUp(event.target.value)} placeholder="Contoh: tambahkan KPI, source evidence wajib, atau batas biaya." rows={3} value={followUp} /></label>
              <button className="button secondary" disabled={busy || !followUp.trim()} type="submit">Simpan klarifikasi dan revisi draft</button>
            </form>
          </section>
        </section>
      ) : null}
    </section>
  );
}
