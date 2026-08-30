"use client";

import { useRouter } from "next/navigation";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { Icon } from "@/components/icons";
import { useSession } from "@/components/session-provider";
import {
  ApiError,
  apiBaseUrl,
  exchangeOidcCode,
  getOidcStatus,
  issuePilotToken,
  oidcLoginUrl,
} from "@/lib/api";
import { roleLabels } from "@/lib/navigation";
import { claimOidcCallback } from "@/lib/oidc-callback";
import { roles, type Role } from "@/lib/types";

const uuidPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const pilotLoginEnabled =
  process.env.NODE_ENV !== "production" ||
  process.env.NEXT_PUBLIC_ALOS_PILOT_LOGIN_ENABLED === "true";

const defaultDivision: Partial<Record<Role, string>> = {
  DIVISION_HEAD: "SALES_MARKETING",
  SALES: "SALES_MARKETING",
  FINANCE: "FINANCE",
  PROPERTY: "PROPERTY",
  HR: "HR",
  LEGAL: "LEGAL",
  IT_ADMIN: "IT",
};

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return "Akses belum dapat diverifikasi. Silakan periksa data dan coba lagi.";
}

export default function LoginPage() {
  const router = useRouter();
  const session = useSession();
  const authenticate = session.authenticate;
  const oidcCallbackHandled = useRef(false);
  const [mode, setMode] = useState<"pilot" | "token">(pilotLoginEnabled ? "pilot" : "token");
  const [organizationId, setOrganizationId] = useState("00000000-0000-0000-0000-000000000002");
  const [userId, setUserId] = useState("00000000-0000-0000-0000-000000000001");
  const [role, setRole] = useState<Role>("IT_ADMIN");
  const [divisionCode, setDivisionCode] = useState("IT");
  const [projectIds, setProjectIds] = useState("");
  const [accessToken, setAccessToken] = useState("");
  const [oidcEnabled, setOidcEnabled] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getOidcStatus()
      .then((result) => {
        if (active) setOidcEnabled(result.enabled && result.provider === "google");
      })
      .catch(() => {
        if (active) setOidcEnabled(false);
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    const callback = claimOidcCallback(window.location.hash, oidcCallbackHandled);
    if (!callback) return;
    window.history.replaceState(null, "", window.location.pathname);
    if (callback.error) {
      window.queueMicrotask(() => {
        setError(
          callback.error === "access_denied"
            ? "Login Google dibatalkan."
            : "Login Google tidak dapat diverifikasi. Silakan coba lagi.",
        );
      });
      return;
    }
    if (!callback.code) return;
    exchangeOidcCode(callback.code)
      .then(async (token) => {
        await authenticate(token.access_token);
        router.replace("/");
      })
      .catch((loginError: unknown) => {
        setError(errorMessage(loginError));
      });
  }, [authenticate, router]);

  async function completeAuthentication(token: string) {
    await authenticate(token);
    router.replace("/");
  }

  async function submitPilot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const parsedProjects = projectIds
      .split(/[\s,]+/)
      .map((value) => value.trim())
      .filter(Boolean);
    if (!uuidPattern.test(userId) || !uuidPattern.test(organizationId)) {
      setError("User ID dan Organization ID wajib menggunakan format UUID yang valid.");
      return;
    }
    if (parsedProjects.some((projectId) => !uuidPattern.test(projectId))) {
      setError("Salah satu Project ID tidak menggunakan format UUID yang valid.");
      return;
    }
    setSubmitting(true);
    try {
      const token = await issuePilotToken({
        user_id: userId,
        organization_id: organizationId,
        roles: [role],
        division_codes: divisionCode ? [divisionCode] : [],
        project_ids: parsedProjects,
      });
      await completeAuthentication(token.access_token);
    } catch (loginError) {
      setError(errorMessage(loginError));
    } finally {
      setSubmitting(false);
    }
  }

  async function submitToken(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!accessToken.trim()) {
      setError("Masukkan token akses yang diterbitkan oleh sistem identitas ALOS.");
      return;
    }
    setSubmitting(true);
    try {
      await completeAuthentication(accessToken.trim());
    } catch (loginError) {
      setError(errorMessage(loginError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="loginPage">
      <section className="loginIntro">
        <div className="loginBrand"><span className="brandMark">A</span><strong>ALOS Internal v1</strong></div>
        <div>
          <p className="eyebrow light">Andara Leverage Operating System</p>
          <h1>Satu pusat kerja untuk operasi internal yang dapat diaudit.</h1>
          <p>Kelola pekerjaan, deadline, bukti, persetujuan, risiko, dan 18 Core Agent dalam satu platform perusahaan.</p>
        </div>
        <ul className="loginAssurances">
          <li><Icon name="check" /> Keputusan material tetap melalui manusia berwenang</li>
          <li><Icon name="check" /> Permission dan workflow divalidasi secara deterministik</li>
          <li><Icon name="check" /> Aktivitas penting tercatat pada audit trail</li>
        </ul>
      </section>

      <section className="loginPanel" aria-labelledby="login-title">
        <div className="loginCard">
          <p className="eyebrow">Akses terbatas</p>
          <h2 id="login-title">Masuk ke ALOS</h2>
          <p className="muted">Gunakan akun perusahaan yang telah diprovisikan untuk mengakses ALOS.</p>

          {oidcEnabled ? (
            <div className="oidcLogin">
              <button
                className="button primary full"
                disabled={submitting}
                onClick={() => window.location.assign(oidcLoginUrl)}
                type="button"
              >
                {submitting ? "Memverifikasi…" : "Masuk dengan Google"}
              </button>
              <span>atau gunakan akses pengembangan</span>
            </div>
          ) : null}

          <div className="segmentedControl" aria-label="Metode masuk">
            {pilotLoginEnabled ? (
              <button
                aria-pressed={mode === "pilot"}
                className={mode === "pilot" ? "active" : ""}
                onClick={() => { setMode("pilot"); setError(null); }}
                type="button"
              >
                Profil pilot
              </button>
            ) : null}
            <button
              aria-pressed={mode === "token"}
              className={mode === "token" ? "active" : ""}
              onClick={() => { setMode("token"); setError(null); }}
              type="button"
            >
              Token akses
            </button>
          </div>

          {mode === "pilot" && pilotLoginEnabled ? (
            <form className="formStack" onSubmit={submitPilot}>
              <div className="fieldGrid">
                <label>User ID<input autoComplete="off" onChange={(event) => setUserId(event.target.value)} required value={userId} /></label>
                <label>Organization ID<input autoComplete="off" onChange={(event) => setOrganizationId(event.target.value)} required value={organizationId} /></label>
              </div>
              <div className="fieldGrid">
                <label>
                  Peran
                  <select
                    onChange={(event) => {
                      const nextRole = event.target.value as Role;
                      setRole(nextRole);
                      setDivisionCode(defaultDivision[nextRole] || "");
                    }}
                    value={role}
                  >
                    {roles.map((item) => <option key={item} value={item}>{roleLabels[item]}</option>)}
                  </select>
                </label>
                <label>Kode divisi<input onChange={(event) => setDivisionCode(event.target.value.toUpperCase())} placeholder="Contoh: FINANCE" value={divisionCode} /></label>
              </div>
              <label>Project ID yang dapat diakses <span className="optional">opsional, pisahkan dengan koma</span><textarea onChange={(event) => setProjectIds(event.target.value)} rows={2} value={projectIds} /></label>
              {error ? <div className="formError" role="alert">{error}</div> : null}
              <button className="button primary full" disabled={submitting} type="submit">
                {submitting ? "Memverifikasi…" : "Masuk dengan profil pilot"}
              </button>
            </form>
          ) : (
            <form className="formStack" onSubmit={submitToken}>
              <label>Token akses<input autoComplete="off" onChange={(event) => setAccessToken(event.target.value)} type="password" value={accessToken} /></label>
              {error ? <div className="formError" role="alert">{error}</div> : null}
              <button className="button primary full" disabled={submitting} type="submit">
                {submitting ? "Memverifikasi…" : "Verifikasi dan masuk"}
              </button>
            </form>
          )}

          <div className="pilotNotice">
            <Icon name="risk" />
            <p><strong>Mode pilot internal</strong><span>Tidak menerima kata sandi. Token hanya disimpan selama tab browser aktif. API: {apiBaseUrl}</span></p>
          </div>
        </div>
      </section>
    </main>
  );
}
