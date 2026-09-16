"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { GenesisFactoryConsole } from "@/components/genesis-factory-console";
import { AppShell } from "@/components/layout/app-shell";
import { getDashboardProfile } from "@/lib/dashboard-access";
import { ApiError, apiRequest } from "@/lib/api-client";
import { canReadFactoryRequests } from "@/lib/genesis-factory";
import { type SessionActor } from "@/lib/governance";

export default function FactoryPage() {
  const router = useRouter();
  const [actor, setActor] = useState<SessionActor | null>(null);
  const [failed, setFailed] = useState(false);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    async function loadActor() {
      try {
        const currentActor = await apiRequest<SessionActor>("/api/v1/whoami");
        if (!canReadFactoryRequests(currentActor.roles)) {
          setForbidden(true);
          return;
        }
        setActor(currentActor);
      } catch (failure) {
        if (failure instanceof ApiError && failure.status === 401) {
          router.replace("/login");
          return;
        }
        setFailed(true);
      }
    }
    void loadActor();
  }, [router]);

  if (failed) {
    return <main className="alos-loading-shell">Sesi ALOS tidak dapat dimuat. Silakan muat ulang halaman.</main>;
  }

  if (forbidden) {
    return (
      <main className="access-denied-shell">
        <p className="eyebrow">ALOS / GENESIS FACTORY</p>
        <h1>Akses GENESIS Factory tidak tersedia</h1>
        <p>
          Requirement dan capability decision hanya dapat dibaca oleh Director, Lead/Anggota
          Divisi, IT Lead, atau reviewer Governance yang berwenang.
        </p>
        <Link className="secondary-button button-link" href="/governance">Kembali ke Governance Dashboard</Link>
      </main>
    );
  }

  if (!actor) {
    return <main className="alos-loading-shell">Memuat GENESIS Factory…</main>;
  }

  const profile = getDashboardProfile(actor.roles, actor.division_codes);

  return (
    <AppShell actor={actor} activeNavHref="/governance" profile={profile}>
      <GenesisFactoryConsole actor={actor} />
    </AppShell>
  );
}
