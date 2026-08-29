"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { ApiError, getPrincipal, getProjects } from "@/lib/api";
import { clearSessionToken, readSessionToken, storeSessionToken } from "@/lib/session";
import type { Principal, Project } from "@/lib/types";

type SessionState = {
  status: "loading" | "authenticated" | "anonymous";
  token: string | null;
  principal: Principal | null;
  projects: Project[];
  activeProjectId: string | null;
  error: string | null;
  authenticate: (token: string) => Promise<void>;
  logout: () => void;
  setActiveProjectId: (projectId: string | null) => void;
  refreshProjects: () => Promise<void>;
};

const SessionContext = createContext<SessionState | null>(null);
const activeProjectKey = "alos.active-project";

export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [status, setStatus] = useState<SessionState["status"]>("loading");
  const [token, setToken] = useState<string | null>(null);
  const [principal, setPrincipal] = useState<Principal | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeProjectId, setProjectId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = useCallback(async (sessionToken: string) => {
    const availableProjects = await getProjects(sessionToken);
    setProjects(availableProjects);
    const saved = window.sessionStorage.getItem(activeProjectKey);
    const selected = availableProjects.some((project) => project.project_id === saved)
      ? saved
      : availableProjects[0]?.project_id || null;
    setProjectId(selected);
    if (selected) window.sessionStorage.setItem(activeProjectKey, selected);
  }, []);

  const authenticate = useCallback(
    async (sessionToken: string) => {
      setError(null);
      const verifiedPrincipal = await getPrincipal(sessionToken);
      storeSessionToken(sessionToken);
      setToken(sessionToken);
      setPrincipal(verifiedPrincipal);
      setStatus("authenticated");
      try {
        await loadProjects(sessionToken);
      } catch (projectError) {
        setProjects([]);
        setError(
          projectError instanceof ApiError
            ? projectError.message
            : "Konteks proyek belum dapat dimuat.",
        );
      }
    },
    [loadProjects],
  );

  const logout = useCallback(() => {
    clearSessionToken();
    window.sessionStorage.removeItem(activeProjectKey);
    setToken(null);
    setPrincipal(null);
    setProjects([]);
    setProjectId(null);
    setError(null);
    setStatus("anonymous");
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    const initialization = window.setTimeout(() => {
      const savedToken = readSessionToken();
      if (!savedToken) {
        setStatus("anonymous");
        return;
      }
      authenticate(savedToken).catch(() => {
        clearSessionToken();
        setStatus("anonymous");
      });
    }, 0);
    return () => window.clearTimeout(initialization);
  }, [authenticate]);

  const setActiveProjectId = useCallback((projectId: string | null) => {
    setProjectId(projectId);
    if (projectId) window.sessionStorage.setItem(activeProjectKey, projectId);
    else window.sessionStorage.removeItem(activeProjectKey);
  }, []);

  const refreshProjects = useCallback(async () => {
    if (token) await loadProjects(token);
  }, [loadProjects, token]);

  const value = useMemo<SessionState>(
    () => ({
      status,
      token,
      principal,
      projects,
      activeProjectId,
      error,
      authenticate,
      logout,
      setActiveProjectId,
      refreshProjects,
    }),
    [
      status,
      token,
      principal,
      projects,
      activeProjectId,
      error,
      authenticate,
      logout,
      setActiveProjectId,
      refreshProjects,
    ],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionState {
  const context = useContext(SessionContext);
  if (!context) throw new Error("useSession harus digunakan di dalam SessionProvider");
  return context;
}
