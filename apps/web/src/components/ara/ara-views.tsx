"use client";

import { useState, useMemo, type KeyboardEvent } from "react";
import type { SessionActor } from "@/lib/governance";

export type AraConversation = {
  id: string;
  title: string;
  snippet: string;
  timestamp: string;
  group: "Hari Ini" | "Kemarin" | "7 Hari Terakhir";
};

export type AraMessage = {
  id: string;
  sender: "ara" | "user";
  text: string;
  timestamp: string;
  status?: string;
  isLoading?: boolean;
  suggestions?: string[];
};

export type AraAgent = {
  id: string;
  name: string;
  description: string;
  category: "doc" | "project" | "data";
  status: "Aktif" | "Nonaktif";
};

const DEFAULT_CONVERSATIONS: AraConversation[] = [
  {
    id: "conv-1",
    title: "Analisis risiko proyek digitalisasi",
    snippet: "Bantu analisis risiko untuk proyek...",
    timestamp: "14.59",
    group: "Hari Ini",
  },
  {
    id: "conv-2",
    title: "Ringkasan progres divisi IT",
    snippet: "Buat ringkasan progres dan capaian...",
    timestamp: "10.24",
    group: "Hari Ini",
  },
  {
    id: "conv-3",
    title: "Draft laporan bulanan IT",
    snippet: "Tolong buat draft laporan bulanan...",
    timestamp: "16.20",
    group: "Kemarin",
  },
  {
    id: "conv-4",
    title: "Rekomendasi tools untuk tim",
    snippet: "Apa tools yang direkomendasikan...",
    timestamp: "13.15",
    group: "Kemarin",
  },
  {
    id: "conv-5",
    title: "Analisis efisiensi proses",
    snippet: "Bantu analisis proses dan berikan...",
    timestamp: "09.05",
    group: "Kemarin",
  },
  {
    id: "conv-6",
    title: "Perbandingan vendor cloud",
    snippet: "Buat perbandingan antara AWS, Azure...",
    timestamp: "12 Sep",
    group: "7 Hari Terakhir",
  },
  {
    id: "conv-7",
    title: "SOP pengelolaan aset IT",
    snippet: "Tolong buatkan draft SOP untuk...",
    timestamp: "11 Sep",
    group: "7 Hari Terakhir",
  },
  {
    id: "conv-8",
    title: "Insight dari data tiket",
    snippet: "Apa insight yang bisa diambil dari...",
    timestamp: "9 Sep",
    group: "7 Hari Terakhir",
  },
  {
    id: "conv-9",
    title: "Rencana pelatihan tim",
    snippet: "Buat rencana pelatihan untuk tim IT...",
    timestamp: "8 Sep",
    group: "7 Hari Terakhir",
  },
];

const DEFAULT_AGENTS: AraAgent[] = [
  {
    id: "ag-1",
    name: "Document Analyst",
    description: "Analisis dan ringkasan dokumen",
    category: "doc",
    status: "Aktif",
  },
  {
    id: "ag-2",
    name: "Project Analyst",
    description: "Analisis proyek dan progres",
    category: "project",
    status: "Aktif",
  },
  {
    id: "ag-3",
    name: "Data Insight",
    description: "Analisis data dan visualisasi",
    category: "data",
    status: "Aktif",
  },
];

const DEFAULT_SUGGESTIONS = [
  "Buat ringkasan progres divisi saya",
  "Analisis risiko proyek yang sedang berjalan",
  "Bandingkan vendor untuk infrastruktur cloud",
  "Buat draft laporan bulanan",
  "Rekomendasikan prioritas kerja minggu ini",
];

function createUniqueId(prefix: string): string {
  return `${prefix}-${Date.now()}`;
}

function getCurrentTimeString(): string {
  return new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });
}

export type AraViewsProps = {
  actor?: SessionActor;
  initialQuery?: string;
  onSendMessage?: (content: string) => Promise<void>;
};

export function AraViews({
  actor,
  initialQuery = "",
  onSendMessage,
}: AraViewsProps) {
  const [conversations, setConversations] = useState<AraConversation[]>(DEFAULT_CONVERSATIONS);
  const [activeConvId, setActiveConvId] = useState<string>("conv-1");
  const [searchQuery, setSearchQuery] = useState("");
  const [inputText, setInputText] = useState(initialQuery);
  const [isContextModalOpen, setIsContextModalOpen] = useState(false);
  const [isAgentDrawerOpen, setIsAgentDrawerOpen] = useState(false);
  const [attachedContexts, setAttachedContexts] = useState<string[]>([]);
  const [selectedModel, setSelectedModel] = useState("GENESIS Core");

  // Initial chat history matching REFERENCE B screenshot
  const [messages, setMessages] = useState<AraMessage[]>([
    {
      id: "msg-1",
      sender: "ara",
      timestamp: "14.58",
      text: "Halo! Saya ARA, asisten AI ALOS.\nSaya dapat membantu Anda mencari informasi, menganalisis data, merangkum dokumen, membuat draft, hingga memberikan rekomendasi untuk pekerjaan Anda.\n\nApa yang ingin Anda lakukan hari ini?",
      suggestions: [
        "Ringkas dokumen yang saya upload",
        "Analisis data proyek saya",
        "Buat draft laporan",
        "Berikan insight dari data",
        "Rekomendasikan langkah selanjutnya",
      ],
    },
    {
      id: "msg-2",
      sender: "user",
      timestamp: "14.59",
      text: "Tolong buatkan ringkasan progres proyek digitalisasi untuk divisi IT Operations bulan ini, dan highlight risiko yang perlu diperhatikan.",
    },
    {
      id: "msg-3",
      sender: "ara",
      timestamp: "15.00",
      status: "••• Memproses...",
      isLoading: true,
      text: "Baik, saya akan menganalisis data terbaru dari proyek di divisi IT Operations, mengambil informasi kunci, dan menyajikan ringkasan beserta risiko utama.\nMohon tunggu sebentar, saya sedang menyiapkan ringkasannya...",
    },
  ]);

  // Filtered conversations based on search
  const filteredConversations = useMemo(() => {
    if (!searchQuery.trim()) return conversations;
    const q = searchQuery.toLowerCase();
    return conversations.filter(
      (c) => c.title.toLowerCase().includes(q) || c.snippet.toLowerCase().includes(q),
    );
  }, [conversations, searchQuery]);

  // Handle New Conversation
  const handleNewConversation = () => {
    const newId = createUniqueId("conv");
    const newConv: AraConversation = {
      id: newId,
      title: "Percakapan Baru",
      snippet: "Mulai percakapan baru dengan ARA...",
      timestamp: "Baru saja",
      group: "Hari Ini",
    };
    setConversations([newConv, ...conversations]);
    setActiveConvId(newId);
    setMessages([
      {
        id: createUniqueId("msg"),
        sender: "ara",
        timestamp: "Baru saja",
        text: "Halo! Saya ARA, asisten AI ALOS. Apa yang dapat saya bantu untuk Anda hari ini?",
        suggestions: [
          "Ringkas dokumen yang saya upload",
          "Analisis data proyek saya",
          "Buat draft laporan",
        ],
      },
    ]);
  };

  // Handle Sending Message
  const handleSend = async (contentToSend?: string) => {
    const text = contentToSend ?? inputText;
    if (!text.trim()) return;

    const userMsg: AraMessage = {
      id: createUniqueId("msg-u"),
      sender: "user",
      timestamp: getCurrentTimeString(),
      text: text.trim(),
    };

    const processingMsg: AraMessage = {
      id: createUniqueId("msg-a"),
      sender: "ara",
      timestamp: getCurrentTimeString(),
      status: "••• Memproses...",
      isLoading: true,
      text: "Baik, saya sedang menganalisis permintaan Anda dan menghubungkan data yang relevan. Mohon tunggu sebentar...",
    };

    setMessages((prev) => [...prev, userMsg, processingMsg]);
    setInputText("");

    if (onSendMessage) {
      await onSendMessage(text);
    }

    // Simulate response resolution after 1.8s
    setTimeout(() => {
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === processingMsg.id
            ? {
                ...msg,
                isLoading: false,
                status: undefined,
                text: `Berikut analisis untuk: "${text}"\n\n1. Portofolio Proyek: Sebanyak 12 proyek aktif terpantau berjalan lancar (83% on-track), dengan rata-rata progres 78.5%.\n2. Titik Perhatian: Migrasi Core System dan Lisensi Cloud memerlukan evaluasi mitigasi segera.\n3. Rekomendasi Tindak Lanjut: Lakukan koordinasi dengan tim Infrastructure dan tinjau checklist kepatuhan pada Dokumen Kebijakan Keamanan v2.0.`,
              }
            : msg,
        ),
      );
    }, 1800);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <div className="alos-ara-container">
      {/* 3-Column Workspace Grid */}
      <div className="alos-ara-workspace-grid">
        {/* ===================================================================
            COLUMN 1 (~24%): CONVERSATION HISTORY (Percakapan)
            =================================================================== */}
        <aside className="alos-ara-sidebar" aria-label="Daftar Percakapan ARA">
          {/* Header */}
          <div className="alos-ara-sidebar-head">
            <h2 className="alos-ara-sidebar-title">Percakapan</h2>
            <button
              className="alos-ara-btn-new-chat"
              id="btn-percakapan-baru"
              onClick={handleNewConversation}
              type="button"
            >
              + Percakapan Baru
            </button>
          </div>

          {/* Search Box */}
          <div className="alos-ara-search-wrap">
            <svg
              className="alos-ara-search-icon"
              fill="none"
              height="15"
              stroke="currentColor"
              viewBox="0 0 24 24"
              width="15"
            >
              <circle cx="11" cy="11" r="8" strokeWidth="2" />
              <path d="M21 21l-4.35-4.35" strokeLinecap="round" strokeWidth="2" />
            </svg>
            <input
              className="alos-ara-search-input"
              id="search-percakapan"
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Cari percakapan..."
              type="search"
              value={searchQuery}
            />
          </div>

          {/* Grouped Conversation List */}
          <div className="alos-ara-conv-list">
            {(["Hari Ini", "Kemarin", "7 Hari Terakhir"] as const).map((group) => {
              const groupItems = filteredConversations.filter((c) => c.group === group);
              if (groupItems.length === 0) return null;
              return (
                <div className="alos-ara-conv-group" key={group}>
                  <div className="alos-ara-group-label">{group}</div>
                  <div className="alos-ara-group-items">
                    {groupItems.map((conv) => {
                      const isActive = conv.id === activeConvId;
                      return (
                        <div
                          className={`alos-ara-conv-card ${isActive ? "active" : ""}`}
                          key={conv.id}
                          onClick={() => setActiveConvId(conv.id)}
                          role="button"
                          tabIndex={0}
                        >
                          <div className="alos-ara-conv-left">
                            <span className="alos-ara-chat-bubble-icon">
                              <svg fill="none" height="15" stroke="currentColor" viewBox="0 0 24 24" width="15">
                                <path
                                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  strokeWidth="2"
                                />
                              </svg>
                            </span>
                            <div className="alos-ara-conv-text">
                              <div className="alos-ara-conv-title">{conv.title}</div>
                              <div className="alos-ara-conv-snippet">{conv.snippet}</div>
                            </div>
                          </div>
                          <span className="alos-ara-conv-time">{conv.timestamp}</span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </aside>

        {/* ===================================================================
            COLUMN 2 (~50%): MAIN ARA CHAT STREAM & COMPOSER
            =================================================================== */}
        <section className="alos-ara-main-stream" aria-label="Ruang Percakapan ARA">
          {/* Header Card */}
          <div className="alos-ara-header-card">
            <div className="alos-ara-header-left">
              <div className="alos-ara-avatar-badge">
                <span className="alos-ara-avatar-text">A</span>
              </div>
              <div>
                <h1 className="alos-ara-name">ARA</h1>
                <p className="alos-ara-tagline">
                  Asisten AI untuk kerja yang lebih cerdas, cepat, dan berdampak.
                </p>
              </div>
            </div>

            <div className="alos-ara-header-right">
              <select
                aria-label="Pilih Model Engine"
                className="alos-ara-model-select"
                onChange={(e) => setSelectedModel(e.target.value)}
                value={selectedModel}
              >
                <option value="GENESIS Core">⬡ GENESIS Core</option>
                <option value="GENESIS Pro (Analytic)">⬡ GENESIS Pro</option>
                <option value="GENESIS Ultra">⬡ GENESIS Ultra</option>
              </select>
            </div>
          </div>

          {/* Scrollable Message Feed */}
          <div className="alos-ara-messages-feed" id="ara-messages-feed">
            {messages.map((msg) => {
              if (msg.sender === "user") {
                return (
                  <div className="alos-ara-msg-row user" key={msg.id}>
                    <div className="alos-ara-msg-content-wrap user">
                      <div className="alos-ara-msg-meta user">
                        <span className="alos-ara-sender-name">Anda</span>
                        <span className="alos-ara-msg-time">{msg.timestamp}</span>
                      </div>
                      <div className="alos-ara-bubble user">{msg.text}</div>
                    </div>
                    <div className="alos-ara-user-avatar">
                      {actor?.division_codes?.[0] ? actor.division_codes[0].slice(0, 2).toUpperCase() : "IT"}
                    </div>
                  </div>
                );
              }

              // Assistant (ARA) message
              return (
                <div className="alos-ara-msg-row ara" key={msg.id}>
                  <div className="alos-ara-bot-avatar">A</div>
                  <div className="alos-ara-msg-content-wrap ara">
                    <div className="alos-ara-msg-meta ara">
                      <span className="alos-ara-sender-name">ARA</span>
                      <span className="alos-ara-msg-time">{msg.timestamp}</span>
                      {msg.status && <span className="alos-ara-msg-status">{msg.status}</span>}
                    </div>

                    <div className="alos-ara-bubble ara">
                      <div className="alos-ara-bubble-text">{msg.text}</div>

                      {/* Quick Suggestion Pills */}
                      {msg.suggestions && msg.suggestions.length > 0 && (
                        <div className="alos-ara-suggestions-wrap">
                          {msg.suggestions.map((sug, idx) => (
                            <button
                              className="alos-ara-suggestion-chip"
                              key={idx}
                              onClick={() => void handleSend(sug)}
                              type="button"
                            >
                              {sug}
                            </button>
                          ))}
                        </div>
                      )}

                      {/* Thinking / Progress Box */}
                      {msg.isLoading && (
                        <div className="alos-ara-thinking-box">
                          <div className="alos-ara-spinner" />
                          <div className="alos-ara-thinking-text">
                            <div className="alos-ara-thinking-title">
                              ARA sedang menganalisis data proyek...
                            </div>
                            <div className="alos-ara-thinking-desc">
                              Mengambil data dari proyek, dokumen, dan laporan terkait.
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Composer Input Area */}
          <div className="alos-ara-composer-card">
            <textarea
              className="alos-ara-composer-textarea"
              id="ara-prompt-input"
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Tulis pertanyaan atau minta bantuan apa saja..."
              rows={2}
              value={inputText}
            />

            <div className="alos-ara-composer-toolbar">
              <div className="alos-ara-composer-tools-left">
                <button
                  className="alos-ara-tool-btn"
                  onClick={() => setIsContextModalOpen(true)}
                  type="button"
                >
                  <svg fill="none" height="14" stroke="currentColor" viewBox="0 0 24 24" width="14">
                    <path
                      d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                    />
                  </svg>
                  Lampirkan
                </button>

                <button
                  className="alos-ara-tool-btn"
                  onClick={() => setIsContextModalOpen(true)}
                  type="button"
                >
                  <svg fill="none" height="14" stroke="currentColor" viewBox="0 0 24 24" width="14">
                    <circle cx="12" cy="12" r="10" strokeWidth="2" />
                    <path d="M2 12h20M12 2a15.3 15.3 0 014 10 15.3 15.3 0 01-4 10 15.3 15.3 0 01-4-10 15.3 15.3 0 014-10z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                  </svg>
                  Gunakan Konteks ⌵
                </button>
              </div>

              <div className="alos-ara-composer-tools-right">
                <span className="alos-ara-shortcut-hint">Shift + Enter untuk baris baru</span>
                <button
                  className="alos-ara-btn-send"
                  disabled={!inputText.trim()}
                  id="btn-kirim-prompt"
                  onClick={() => void handleSend()}
                  type="button"
                >
                  <svg fill="none" height="14" stroke="currentColor" viewBox="0 0 24 24" width="14">
                    <path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                  </svg>
                  Kirim
                </button>
              </div>
            </div>
          </div>
        </section>

        {/* ===================================================================
            COLUMN 3 (~26%): CONTEXT, AGENTS & SUGGESTIONS PANEL
            =================================================================== */}
        <aside className="alos-ara-right-panel" aria-label="Kontrol Konteks dan Agen">
          {/* Card 1: Konteks Saat Ini */}
          <div className="alos-ara-card">
            <div className="alos-ara-card-header">
              <h3 className="alos-ara-card-title">Konteks Saat Ini</h3>
              <button
                className="alos-ara-card-action-btn"
                onClick={() => setIsContextModalOpen(true)}
                type="button"
              >
                + Tambah
              </button>
            </div>

            {attachedContexts.length === 0 ? (
              <div className="alos-ara-empty-context-box">
                <span className="alos-ara-empty-context-icon">
                  <svg fill="none" height="20" stroke="currentColor" viewBox="0 0 24 24" width="20">
                    <path
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                    />
                  </svg>
                </span>
                <div>
                  <div className="alos-ara-empty-context-title">Belum ada konteks</div>
                  <div className="alos-ara-empty-context-sub">
                    Tambahkan dokumen, proyek, atau data yang ingin digunakan dalam percakapan ini.
                  </div>
                </div>
              </div>
            ) : (
              <div className="alos-ara-context-chips">
                {attachedContexts.map((ctx, i) => (
                  <span className="alos-ara-context-chip" key={i}>
                    📄 {ctx}
                    <button
                      onClick={() => setAttachedContexts(attachedContexts.filter((_, idx) => idx !== i))}
                      type="button"
                    >
                      ✕
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Card 2: Agen Aktif */}
          <div className="alos-ara-card">
            <div className="alos-ara-card-header">
              <h3 className="alos-ara-card-title">Agen Aktif</h3>
              <button
                className="alos-ara-link-action"
                onClick={() => setIsAgentDrawerOpen(true)}
                type="button"
              >
                Kelola Agen →
              </button>
            </div>

            <div className="alos-ara-agent-list">
              {DEFAULT_AGENTS.map((agent) => (
                <div className="alos-ara-agent-item" key={agent.id}>
                  <div className="alos-ara-agent-left">
                    <span className={`alos-ara-agent-icon ${agent.category}`}>
                      {agent.category === "doc" && (
                        <svg fill="none" height="15" stroke="currentColor" viewBox="0 0 24 24" width="15">
                          <path d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                        </svg>
                      )}
                      {agent.category === "project" && (
                        <svg fill="none" height="15" stroke="currentColor" viewBox="0 0 24 24" width="15">
                          <path d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                        </svg>
                      )}
                      {agent.category === "data" && (
                        <svg fill="none" height="15" stroke="currentColor" viewBox="0 0 24 24" width="15">
                          <path d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                        </svg>
                      )}
                    </span>
                    <div>
                      <div className="alos-ara-agent-name">{agent.name}</div>
                      <div className="alos-ara-agent-sub">{agent.description}</div>
                    </div>
                  </div>
                  <span className="alos-ara-badge-active">
                    <span className="alos-ara-dot" /> {agent.status}
                  </span>
                </div>
              ))}
            </div>

            <button
              className="alos-ara-btn-request-agent"
              onClick={() => setIsAgentDrawerOpen(true)}
              type="button"
            >
              + Request Agen Baru
            </button>
          </div>

          {/* Card 3: Saran untuk Anda */}
          <div className="alos-ara-card">
            <div className="alos-ara-card-header">
              <h3 className="alos-ara-card-title">Saran untuk Anda</h3>
              <button
                className="alos-ara-btn-refresh"
                onClick={() => {
                  /* refresh suggestions */
                }}
                title="Segarkan Saran"
                type="button"
              >
                <svg fill="none" height="13" stroke="currentColor" viewBox="0 0 24 24" width="13">
                  <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
                </svg>
                Segarkan
              </button>
            </div>

            <div className="alos-ara-suggestions-list">
              {DEFAULT_SUGGESTIONS.map((sug, idx) => (
                <div
                  className="alos-ara-suggestion-row"
                  key={idx}
                  onClick={() => void handleSend(sug)}
                  role="button"
                  tabIndex={0}
                >
                  <span className="alos-ara-sug-text">› {sug}</span>
                  <span className="alos-ara-sug-arrow">›</span>
                </div>
              ))}
            </div>
          </div>

          {/* Card 4: Dari Data Menuju Dampak Watermark Banner */}
          <div className="alos-ara-impact-banner">
            <span className="alos-ara-sparkle-icon">✦</span>
            <div>
              <h4 className="alos-ara-impact-title">Dari Data Menuju Dampak</h4>
              <p className="alos-ara-impact-desc">
                ARA membantu Anda melihat lebih jauh, bekerja lebih cepat, dan mencapai hasil yang lebih besar.
              </p>
            </div>
          </div>
        </aside>
      </div>

      {/* Modal: Tambah / Gunakan Konteks */}
      {isContextModalOpen && (
        <div className="alos-ara-modal-backdrop" onClick={() => setIsContextModalOpen(false)}>
          <div className="alos-ara-modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="alos-ara-modal-head">
              <div>
                <p className="alos-ara-modal-kicker">SUMBER DATA PERCAKAPAN</p>
                <h3 className="alos-ara-modal-title">Tambahkan Konteks</h3>
              </div>
              <button
                className="alos-ara-modal-close"
                onClick={() => setIsContextModalOpen(false)}
                type="button"
              >
                ✕
              </button>
            </div>

            <div className="alos-ara-context-options-list">
              {[
                { name: "Kebijakan Keamanan Informasi v2.0.pdf", type: "Dokumen" },
                { name: "Portofolio Proyek Digitalisasi Q3", type: "Proyek" },
                { name: "Laporan Kinerja IT Operations - Agustus 2026", type: "Laporan" },
                { name: "Daftar Temuan Audit MFA & Akses", type: "Temuan" },
              ].map((item, idx) => (
                <div
                  className="alos-ara-context-option-item"
                  key={idx}
                  onClick={() => {
                    if (!attachedContexts.includes(item.name)) {
                      setAttachedContexts([...attachedContexts, item.name]);
                    }
                    setIsContextModalOpen(false);
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <div>
                    <div className="alos-ara-opt-name">{item.name}</div>
                    <div className="alos-ara-opt-type">{item.type}</div>
                  </div>
                  <button className="alos-ara-btn-attach-opt" type="button">
                    + Pakai
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Modal: Kelola Agen */}
      {isAgentDrawerOpen && (
        <div className="alos-ara-modal-backdrop" onClick={() => setIsAgentDrawerOpen(false)}>
          <div className="alos-ara-modal-box" onClick={(e) => e.stopPropagation()}>
            <div className="alos-ara-modal-head">
              <div>
                <p className="alos-ara-modal-kicker">GOVERNANCE &amp; AGENT CONTROL</p>
                <h3 className="alos-ara-modal-title">Kelola Agen AI</h3>
              </div>
              <button
                className="alos-ara-modal-close"
                onClick={() => setIsAgentDrawerOpen(false)}
                type="button"
              >
                ✕
              </button>
            </div>

            <p style={{ fontSize: "0.82rem", color: "#52665e", margin: "0 0 12px 0" }}>
              Seluruh agen AI beroperasi di bawah boundary kebijakan ALOS Governance Engine.
            </p>

            <div className="alos-ara-agent-manage-list">
              {DEFAULT_AGENTS.map((agent) => (
                <div className="alos-ara-agent-manage-item" key={agent.id}>
                  <div>
                    <div className="alos-ara-opt-name">{agent.name}</div>
                    <div className="alos-ara-opt-type">{agent.description}</div>
                  </div>
                  <span className="alos-ara-badge-active">
                    <span className="alos-ara-dot" /> {agent.status}
                  </span>
                </div>
              ))}
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "16px" }}>
              <button
                className="alos-ara-btn-new-chat"
                onClick={() => setIsAgentDrawerOpen(false)}
                type="button"
              >
                Tutup
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
