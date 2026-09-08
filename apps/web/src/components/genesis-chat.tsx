"use client";

import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useMemo, useState } from "react";

import { apiMessage, apiRequest, withQuery } from "@/lib/api-client";
import { type SessionActor, type Workspace } from "@/lib/governance";

type ContextMode = "AUTO" | "INTERNAL" | "EXTERNAL" | "INTERNAL_AND_EXTERNAL";

type Conversation = {
  conversation_id: string;
  workspace_id: string | null;
  title: string | null;
  context_mode: ContextMode;
  status: string;
  created_at: string;
  updated_at: string | null;
};

type Message = {
  message_id: string;
  actor_kind: "HUMAN" | "SYSTEM";
  content: string;
  status: string;
  structured_content: Record<string, unknown>;
  citations: Array<Record<string, unknown>>;
  tool_activity: Array<Record<string, unknown>>;
  created_at: string;
};

type GenesisResponse = {
  answer?: string;
  intent?: string;
  reliability?: string;
  findings?: string[];
  recommendations?: string[];
  limitations?: string[];
  actions?: Array<Record<string, unknown>>;
};

type ConversationContext = {
  conversation_context_id: string;
  entity_type: "DOCUMENT" | "PROJECT" | "TASK" | "EVIDENCE" | "FINDING" | "REPORT";
  entity_id: string;
  source_version: string | null;
};

type AgentCandidate = {
  agent_key: string;
  name: string;
  semantic_version: string;
  purpose: string;
  risk_level: string;
  capability_keys: string[];
};

type TurnResult = {
  human_message: Message;
  assistant_message: Message;
  candidate_capabilities: string[];
  candidate_agents: AgentCandidate[];
  external_research: { status: string; items: Array<Record<string, unknown>> };
  correlation_id: string;
};

type DesignerResult = {
  proposed_design: { agent_key: string; name: string; objective: string };
  normalized_risk_level: string;
  bound_tool_keys: string[];
  missing_dependencies: string[];
  activation_readiness: { ready: boolean; blockers: string[] };
  draft: { agent: { agent_key: string; name: string }; version: { semantic_version: string } };
  release_request: { change_request_id: string; status: string };
  generated_tests: Array<{ test_key: string; category: string }>;
};

export function GenesisChat({ actor, initialQuery = "" }: { actor: SessionActor; initialQuery?: string }) {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState(actor.workspace_ids[0] ?? "");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [contexts, setContexts] = useState<ConversationContext[]>([]);
  const [attachment, setAttachment] = useState({ entity_type: "DOCUMENT" as ConversationContext["entity_type"], entity_id: "", source_version: "" });
  const [mode, setMode] = useState<ContextMode>("AUTO");
  const [prompt, setPrompt] = useState(() => initialQuery || (typeof window === "undefined" ? "" : new URLSearchParams(window.location.search).get("prompt") ?? ""));
  const [agents, setAgents] = useState<AgentCandidate[]>([]);
  const [capabilities, setCapabilities] = useState<string[]>([]);
  const [externalStatus, setExternalStatus] = useState("NOT_REQUESTED");
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [showAgentRequest, setShowAgentRequest] = useState(false);
  const [agentResult, setAgentResult] = useState<DesignerResult | null>(null);

  const loadConversations = useCallback(async (nextWorkspaceId: string, selectNewest = false) => {
    const items = await apiRequest<Conversation[]>(withQuery("/api/v1/genesis/conversations", { workspace_id: nextWorkspaceId }));
    setConversations(items);
    if (selectNewest && items[0]) setConversationId(items[0].conversation_id);
    if (items.length === 0) {
      setConversationId("");
      setMessages([]);
    }
  }, []);

  useEffect(() => {
    async function loadFoundation() {
      setLoading(true);
      try {
        const nextWorkspaces = await apiRequest<Workspace[]>("/api/v1/workspaces");
        const allowed = nextWorkspaces.filter((workspace) => actor.workspace_ids.includes(workspace.workspace_id));
        setWorkspaces(allowed);
        const first = workspaceId || allowed[0]?.workspace_id || "";
        setWorkspaceId(first);
        if (first) await loadConversations(first, true);
      } catch (failure) {
        setError(apiMessage(failure));
      } finally {
        setLoading(false);
      }
    }
    void loadFoundation();
  }, [actor.workspace_ids, loadConversations, workspaceId]);

  useEffect(() => {
    if (!conversationId) return;
    async function loadMessages() {
      try {
        const [items, attached] = await Promise.all([
          apiRequest<Message[]>(`/api/v1/genesis/conversations/${conversationId}/messages`),
          apiRequest<ConversationContext[]>(`/api/v1/genesis/conversations/${conversationId}/context`),
        ]);
        setMessages(items);
        setContexts(attached);
        const active = conversations.find((item) => item.conversation_id === conversationId);
        if (active) setMode(active.context_mode);
      } catch (failure) {
        setError(apiMessage(failure));
      }
    }
    void loadMessages();
  }, [conversationId, conversations]);

  async function newConversation() {
    setError(""); setNotice(""); setMessages([]); setContexts([]); setConversationId(""); setAgents([]); setCapabilities([]);
  }

  async function changeWorkspace(next: string) {
    setWorkspaceId(next); setConversationId(""); setMessages([]); setContexts([]); setError("");
    try { await loadConversations(next, true); } catch (failure) { setError(apiMessage(failure)); }
  }

  async function attachContext(event: FormEvent) {
    event.preventDefault();
    if (!conversationId || !attachment.entity_id.trim()) return;
    setError("");
    try {
      const attached = await apiRequest<ConversationContext>(`/api/v1/genesis/conversations/${conversationId}/context`, {
        method: "POST",
        body: JSON.stringify({ ...attachment, entity_id: attachment.entity_id.trim(), source_version: attachment.source_version.trim() || null }),
      });
      setContexts((current) => current.some((item) => item.conversation_context_id === attached.conversation_context_id) ? current : [...current, attached]);
      setAttachment({ entity_type: "DOCUMENT", entity_id: "", source_version: "" });
      setNotice("Konteks resmi telah dilampirkan dan dicatat pada audit percakapan.");
    } catch (failure) { setError(apiMessage(failure)); }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const content = prompt.trim();
    if (!content || !workspaceId || sending) return;
    setSending(true); setError(""); setNotice("");
    try {
      let target = conversationId;
      if (!target) {
        const created = await apiRequest<Conversation>("/api/v1/genesis/conversations", {
          method: "POST",
          body: JSON.stringify({ workspace_id: workspaceId, title: content.slice(0, 80), context_mode: mode }),
        });
        target = created.conversation_id;
        setConversationId(target);
      }
      const result = await apiRequest<TurnResult>(`/api/v1/genesis/conversations/${target}/turns`, {
        method: "POST",
        body: JSON.stringify({ content, context_mode: mode, attachments: [] }),
      });
      setMessages((current) => [...current, result.human_message, result.assistant_message]);
      setAgents(result.candidate_agents);
      setCapabilities(result.candidate_capabilities);
      setExternalStatus(result.external_research.status);
      setPrompt("");
      await loadConversations(workspaceId);
    } catch (failure) {
      setError(apiMessage(failure));
    } finally {
      setSending(false);
    }
  }

  function submitOnEnter(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }

  const activeTitle = conversations.find((item) => item.conversation_id === conversationId)?.title ?? "Percakapan baru";
  return <section className="alos-content alos-genesis-chat-shell" aria-label="GENESIS Chat">
    <div className="alos-genesis-chat-heading"><div><p className="alos-kicker">ALOS / GENESIS</p><h2>GENESIS Company Assistant</h2><p>Jawaban berbasis data sesuai role dan scope. Aksi material selalu menjadi DRAFT untuk review manusia.</p></div><div><select aria-label="Workspace GENESIS" onChange={(event) => void changeWorkspace(event.target.value)} value={workspaceId}>{workspaces.map((workspace) => <option key={workspace.workspace_id} value={workspace.workspace_id}>{workspace.name}</option>)}</select><button className="alos-outline-button" onClick={() => void newConversation()} type="button">+ Percakapan baru</button></div></div>
    {error ? <div className="alos-operation-banner error" role="alert">{error}</div> : null}
    {notice ? <div className="alos-operation-banner success" role="status">{notice}</div> : null}
    <div className="alos-genesis-chat-grid">
      <aside className="alos-genesis-history"><strong>Riwayat</strong>{loading ? <p>Memuat…</p> : null}<div>{conversations.map((item) => <button className={conversationId === item.conversation_id ? "selected" : ""} key={item.conversation_id} onClick={() => setConversationId(item.conversation_id)} type="button"><span>{item.title ?? "Percakapan tanpa judul"}</span><small>{formatTime(item.updated_at ?? item.created_at)}</small></button>)}{!loading && conversations.length === 0 ? <p>Belum ada percakapan.</p> : null}</div></aside>
      <article className="alos-genesis-conversation">
        <header><div><span className="alos-genesis-orb">G</span><div><strong>{activeTitle}</strong><small>{conversationId ? "Riwayat tersimpan dan dapat diaudit" : "Mulai dari kebutuhan bisnis Anda"}</small></div></div><select aria-label="Mode sumber GENESIS" onChange={(event) => setMode(event.target.value as ContextMode)} value={mode}><option value="AUTO">Auto</option><option value="INTERNAL">Internal only</option><option value="EXTERNAL">External only</option><option value="INTERNAL_AND_EXTERNAL">Internal + external</option></select></header>
        <div className="alos-genesis-messages" aria-live="polite">{messages.length === 0 ? <GenesisWelcome actor={actor} onPrompt={setPrompt} /> : messages.map((message) => <GenesisMessage key={message.message_id} message={message} />)}{sending ? <div className="alos-genesis-thinking"><span /><span /><span /> GENESIS sedang menelusuri sumber yang diizinkan…</div> : null}</div>
        <form className="alos-genesis-chat-composer" onSubmit={(event) => void submit(event)}><textarea maxLength={10000} onChange={(event) => setPrompt(event.target.value)} onKeyDown={submitOnEnter} placeholder="Tanyakan kondisi bisnis, minta analisis, atau jelaskan agent yang dibutuhkan…" value={prompt} /><div><small>Enter untuk kirim · Shift+Enter untuk baris baru</small><button disabled={!prompt.trim() || !workspaceId || sending} type="submit">{sending ? "…" : "Kirim"}</button></div></form>
      </article>
      <aside className="alos-genesis-context"><section><strong>Konteks turn terakhir</strong><dl><div><dt>Mode</dt><dd>{modeLabel(mode)}</dd></div><div><dt>External</dt><dd>{humanExternalStatus(externalStatus)}</dd></div></dl></section>{conversationId ? <section><strong>Lampirkan konteks ALOS</strong><form className="alos-agent-request-form" onSubmit={(event) => void attachContext(event)}><select aria-label="Jenis konteks" onChange={(event) => setAttachment({ ...attachment, entity_type: event.target.value as ConversationContext["entity_type"] })} value={attachment.entity_type}><option>DOCUMENT</option><option>PROJECT</option><option>TASK</option><option>EVIDENCE</option><option>FINDING</option><option>REPORT</option></select><input aria-label="ID entitas" onChange={(event) => setAttachment({ ...attachment, entity_id: event.target.value })} placeholder="UUID entitas" required value={attachment.entity_id} /><input aria-label="Versi sumber" onChange={(event) => setAttachment({ ...attachment, source_version: event.target.value })} placeholder="Versi (opsional)" value={attachment.source_version} /><button type="submit">Lampirkan</button></form>{contexts.length ? <ul className="alos-context-list">{contexts.map((item) => <li key={item.conversation_context_id}>{item.entity_type} · {item.entity_id.slice(0, 8)}{item.source_version ? ` · ${item.source_version}` : ""}</li>)}</ul> : <p>Belum ada konteks eksplisit.</p>}</section> : null}<section><strong>Capability kandidat</strong>{capabilities.length ? <div className="alos-chip-list">{capabilities.map((item) => <span key={item}>{item}</span>)}</div> : <p>Akan dipilih setelah Anda mengirim kebutuhan.</p>}</section><section><strong>Agent ACTIVE kandidat</strong>{agents.length ? agents.map((item) => <div className="alos-agent-candidate" key={item.agent_key}><b>{item.name}</b><small>{item.agent_key} · v{item.semantic_version}</small></div>) : <p>Belum ada agent relevan yang aktif.</p>}<button className="alos-outline-button" onClick={() => setShowAgentRequest((value) => !value)} type="button">{showAgentRequest ? "Tutup permintaan" : "Minta agent baru"}</button></section>{showAgentRequest ? <AgentRequestForm actor={actor} defaultRequirement={prompt} onResult={(result) => { setAgentResult(result); setNotice(`Agent ${result.proposed_design.name} dibuat sebagai DRAFT dan dikirim ke governance.`); }} workspaceId={workspaceId} /> : null}{agentResult ? <section className="alos-agent-design-result"><strong>DRAFT terbaru</strong><p>{agentResult.proposed_design.name}</p><small>{agentResult.release_request.status} · {agentResult.generated_tests.length} test · {agentResult.bound_tool_keys.length} tool</small></section> : null}</aside>
    </div>
  </section>;
}

function GenesisWelcome({ actor, onPrompt }: { actor: SessionActor; onPrompt: (value: string) => void }) {
  const examples = actor.roles.includes("DIRECTOR")
    ? ["Apa isu perusahaan yang paling mendesak?", "Ringkas approval yang masih pending.", "Buat kebutuhan agent monitoring tugas overdue Property."]
    : ["Apa tugas saya yang perlu segera ditangani?", "Ringkas temuan terbuka di divisi saya.", "Tunjukkan dokumen relevan untuk pekerjaan saya."];
  return <div className="alos-genesis-welcome"><span className="alos-genesis-orb large">G</span><h3>Apa yang ingin Anda ketahui?</h3><p>GENESIS hanya membaca data yang diizinkan dan menyertakan jejak sumber bila tersedia.</p><div>{examples.map((item) => <button key={item} onClick={() => onPrompt(item)} type="button">{item}</button>)}</div></div>;
}

function GenesisMessage({ message }: { message: Message }) {
  const isHuman = message.actor_kind === "HUMAN";
  const response = responseFromMessage(message);
  return <div className={`alos-genesis-message ${isHuman ? "human" : "assistant"}`}><div className="alos-genesis-message-meta"><strong>{isHuman ? "Anda" : "GENESIS"}</strong><time>{formatTime(message.created_at)}</time></div><p>{response?.answer || message.content}</p>{!isHuman && response?.reliability ? <small className="alos-genesis-reliability">Reliabilitas: {response.reliability}</small> : null}{!isHuman ? <GenesisResponseSections response={response} /> : null}{!isHuman && message.citations.length ? <details><summary>{message.citations.length} sumber</summary><ul>{message.citations.map((citation, index) => <li key={`${String(citation.source_id ?? citation.url ?? "citation")}-${index}`}><span>{String(citation.title ?? citation.source_id ?? citation.url ?? "Sumber terverifikasi")}</span><small>{String(citation.source_kind ?? "SOURCE")}</small></li>)}</ul></details> : null}{!isHuman && message.tool_activity.length ? <small className="alos-tool-activity">{message.tool_activity.length} tool call tercatat</small> : null}</div>;
}

function responseFromMessage(message: Message): GenesisResponse | null {
  const value = message.structured_content.response;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as GenesisResponse;
}

function GenesisResponseSections({ response }: { response: GenesisResponse | null }) {
  if (!response) return null;
  const sections: Array<[string, string[] | undefined]> = [
    ["Temuan", response.findings],
    ["Rekomendasi", response.recommendations],
    ["Batasan", response.limitations],
  ];
  return <>{sections.filter(([, items]) => Boolean(items?.length)).map(([title, items]) => <section className="alos-genesis-response-section" key={title}><strong>{title}</strong><ul>{items?.map((item) => <li key={item}>{item}</li>)}</ul></section>)}</>;
}

function AgentRequestForm({ actor, defaultRequirement, onResult, workspaceId }: { actor: SessionActor; defaultRequirement: string; onResult: (result: DesignerResult) => void; workspaceId: string }) {
  const [requirement, setRequirement] = useState(defaultRequirement);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const divisions = useMemo(() => actor.division_codes.slice(0, 6), [actor.division_codes]);
  async function submit(event: FormEvent) { event.preventDefault(); setSaving(true); setError(""); try { const result = await apiRequest<DesignerResult>("/api/v1/genesis/agent-requests", { method: "POST", body: JSON.stringify({ workspace_id: workspaceId, requirement, division_scope: divisions, deterministic: false }) }); onResult(result); } catch (failure) { setError(apiMessage(failure)); } finally { setSaving(false); } }
  return <form className="alos-agent-request-form" onSubmit={(event) => void submit(event)}><label>Kebutuhan agent<textarea minLength={20} onChange={(event) => setRequirement(event.target.value)} placeholder="Jelaskan tujuan, output, frekuensi, dan batasannya…" required value={requirement} /></label>{error ? <small className="error">{error}</small> : null}<button disabled={requirement.trim().length < 20 || saving} type="submit">{saving ? "Menyusun…" : "Buat Agent Contract DRAFT"}</button><small>Tidak ada aktivasi otomatis. Tool, permission, test, dan release tetap melalui governance.</small></form>;
}

function formatTime(value: string): string { return new Intl.DateTimeFormat("id-ID", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)); }
function modeLabel(mode: ContextMode): string { return { AUTO: "Auto", INTERNAL: "Internal", EXTERNAL: "External", INTERNAL_AND_EXTERNAL: "Internal + external" }[mode]; }
function humanExternalStatus(status: string): string { return status === "NOT_REQUESTED" ? "Tidak diminta" : status === "SUCCEEDED" ? "Tersedia" : status === "EXTERNAL_RESEARCH_NOT_CONFIGURED" ? "Belum dikonfigurasi" : status === "UNAVAILABLE" ? "Tidak tersedia" : status; }
