"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { GenesisFactoryConsole } from "@/components/genesis-factory-console";
import { ApiError, apiRequest } from "@/lib/api-client";
import { type SessionActor } from "@/lib/governance";

export default function FactoryPage() {
  const router = useRouter();
  const [actor, setActor] = useState<SessionActor | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    async function loadActor() {
      try {
        setActor(await apiRequest<SessionActor>("/api/v1/whoami"));
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
  if (!actor) {
    return <main className="alos-loading-shell">Memuat GENESIS Factory…</main>;
  }
  return <main className="alos-app-shell"><GenesisFactoryConsole actor={actor} /></main>;
}
