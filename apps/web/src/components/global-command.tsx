"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { apiMessage, apiRequest, withQuery } from "@/lib/api-client";
import { humanStatus, type Notification, type SearchResult } from "@/lib/operational";

export function GlobalCommand({ placeholder }: { placeholder: string }) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [notificationsOpen, setNotificationsOpen] = useState(false);

  useEffect(() => {
    function shortcut(event: globalThis.KeyboardEvent) {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault(); inputRef.current?.focus(); setSearchOpen(true);
      }
      if (event.key === "Escape") { setSearchOpen(false); setNotificationsOpen(false); }
    }
    window.addEventListener("keydown", shortcut);
    return () => window.removeEventListener("keydown", shortcut);
  }, []);

  useEffect(() => {
    const normalized = query.trim();
    if (normalized.length < 2) {
      const resetTimer = window.setTimeout(() => {
        setResults([]); setSearching(false); setSearchError("");
      }, 0);
      return () => window.clearTimeout(resetTimer);
    }
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setSearching(true); setSearchError("");
      try { setResults(await apiRequest<SearchResult[]>(withQuery("/api/v1/search", { q: normalized, limit: 12 }), { signal: controller.signal })); }
      catch (failure) { if (!controller.signal.aborted) setSearchError(apiMessage(failure)); }
      finally { if (!controller.signal.aborted) setSearching(false); }
    }, 250);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [query]);

  async function toggleNotifications() {
    const next = !notificationsOpen;
    setNotificationsOpen(next); setSearchOpen(false);
    if (!next) return;
    try { setNotifications(await apiRequest<Notification[]>(withQuery("/api/v1/notifications", { unread_only: false }))); }
    catch { setNotifications([]); }
  }

  async function markRead(item: Notification) {
    if (item.read_at) return;
    try {
      const updated = await apiRequest<Notification>(`/api/v1/notifications/${item.notification_id}/read`, { method: "POST" });
      setNotifications((current) => current.map((entry) => entry.notification_id === updated.notification_id ? updated : entry));
    } catch { /* The item remains unread and can be retried. */ }
  }

  const unread = notifications.filter((item) => !item.read_at).length;
  return <div className="alos-global-command">
    <label className="alos-search" aria-label="Pencarian ALOS"><span aria-hidden="true">⌕</span><input onChange={(event) => { setQuery(event.target.value); setSearchOpen(true); }} onFocus={() => setSearchOpen(true)} placeholder={placeholder} ref={inputRef} type="search" value={query} /><kbd>⌘ K</kbd></label>
    {searchOpen && query.trim() ? <div className="alos-command-results">{searching ? <p>Menelusuri data yang diizinkan…</p> : null}{searchError ? <p className="error">{searchError}</p> : null}{!searching && !searchError ? results.map((item) => <Link href={item.href} key={`${item.entity_type}-${item.entity_id}`} onClick={() => setSearchOpen(false)}><span><strong>{item.title}</strong><small>{humanStatus(item.entity_type)} · {item.subtitle}</small></span><b>→</b></Link>) : null}{!searching && !searchError && results.length === 0 ? <p>Tidak ada data internal yang cocok.</p> : null}<button onClick={() => { setSearchOpen(false); router.push(`/genesis?prompt=${encodeURIComponent(query.trim())}`); }} type="button">Tanyakan “{query.trim()}” kepada GENESIS</button></div> : null}
    <button aria-expanded={notificationsOpen} aria-label="Notifikasi" className="alos-notifications" onClick={() => void toggleNotifications()} type="button">♢{unread > 0 ? <i /> : null}</button>
    {notificationsOpen ? <div className="alos-notification-panel"><header><strong>Notifikasi</strong><small>{unread} belum dibaca</small></header>{notifications.map((item) => <button className={item.read_at ? "read" : ""} key={item.notification_id} onClick={() => void markRead(item)} type="button"><strong>{item.title}</strong><span>{item.body}</span><small>{new Intl.DateTimeFormat("id-ID", { dateStyle: "short", timeStyle: "short" }).format(new Date(item.created_at))}</small></button>)}{notifications.length === 0 ? <p>Belum ada notifikasi.</p> : null}</div> : null}
  </div>;
}
