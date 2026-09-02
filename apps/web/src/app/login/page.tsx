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
  getPilotProfiles,
  loginPilotProfile,
  oidcLoginUrl,
} from "@/lib/api";
import { divisionLabels, type DivisionCode } from "@/lib/identity";
import { roleLabels } from "@/lib/navigation";
import { claimOidcCallback } from "@/lib/oidc-callback";
import type { PilotProfile } from "@/lib/types";

const pilotLoginEnabled =
  process.env.NODE_ENV !== "production" ||
  process.env.NEXT_PUBLIC_ALOS_PILOT_LOGIN_ENABLED === "true";

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
  const [pilotProfiles, setPilotProfiles] = useState<PilotProfile[]>([]);
  const [profilesLoading, setProfilesLoading] = useState(pilotLoginEnabled);
  const [profileError, setProfileError] = useState<string | null>(null);
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
    if (!pilotLoginEnabled) return;
    let active = true;
    getPilotProfiles()
      .then((profiles) => {
        if (!active) return;
        setPilotProfiles(profiles);
        setProfileError(
          profiles.length ? null : "Akun pilot belum diprovisikan pada proyek sintetis aktif.",
        );
      })
      .catch((profilesError: unknown) => {
        if (active) setProfileError(errorMessage(profilesError));
      })
      .finally(() => {
        if (active) setProfilesLoading(false);
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
        await authenticate(token.access_token, true);
        router.replace("/");
      })
      .catch((loginError: unknown) => {
        setError(errorMessage(loginError));
      });
  }, [authenticate, router]);

  async function completeAuthentication(token: string, useCookieSession: boolean) {
    await authenticate(token, useCookieSession);
    router.replace("/");
  }

  async function submitPilot(userId: string) {
    setError(null);
    setSubmitting(true);
    try {
      const token = await loginPilotProfile(userId);
      await completeAuthentication(token.access_token, true);
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
      await completeAuthentication(accessToken.trim(), false);
    } catch (loginError) {
      setError(errorMessage(loginError));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="loginPage">
      <section className="loginIntro">
        <div className="loginBrand"><span className="brandMark">A</span><strong>ALOS</strong></div>
        <div>
          <p className="eyebrow light">Andara Leverage Operating System</p>
          <h1>Satu pusat kerja untuk operasi internal yang dapat diaudit.</h1>
          <p>Kelola Genesis, evidence, persetujuan, audit, dan logical agent dalam satu platform perusahaan.</p>
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
            <div className="pilotProfileSection">
              <div className="pilotProfileHeader">
                <strong>Pilih akun pengujian</strong>
                <span>Role dan akses diambil langsung dari database.</span>
              </div>
              {profilesLoading ? <p className="muted">Memuat akun pilot…</p> : null}
              {profileError ? <div className="formError" role="alert">{profileError}</div> : null}
              <div className="pilotProfileList">
                {pilotProfiles.map((profile) => {
                  const roleLabel = profile.roles.map((item) => roleLabels[item]).join(" · ");
                  const divisionLabel = profile.division_codes.length
                    ? profile.division_codes
                        .map((item) => divisionLabels[item as DivisionCode] || item)
                        .join(" · ")
                    : "Lintas divisi";
                  const accessLabel = roleLabel === divisionLabel
                    ? roleLabel
                    : `${roleLabel} · ${divisionLabel}`;
                  return (
                    <button
                      className="pilotProfileButton"
                      disabled={submitting}
                      key={profile.user_id}
                      onClick={() => void submitPilot(profile.user_id)}
                      type="button"
                    >
                      <span className="profileInitial">{profile.display_name.charAt(0)}</span>
                      <span className="profileIdentity">
                        <strong>{profile.display_name}</strong>
                        <small>{accessLabel}</small>
                        <em>{profile.email}</em>
                      </span>
                      <Icon name="chevron" />
                    </button>
                  );
                })}
              </div>
              {error ? <div className="formError" role="alert">{error}</div> : null}
            </div>
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
