"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        credentials: "same-origin",
        cache: "no-store",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (!response.ok) {
        setError("Email atau password tidak valid.");
        return;
      }
      router.replace("/");
      router.refresh();
    } catch {
      setError("Tidak dapat terhubung ke ALOS. Coba lagi.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="login-shell">
      <aside className="login-hero" aria-label="ALOS Integrated Business Platform">
        <header className="hero-header">
          <Brand lockup="light" />
          <p className="hero-promise"><span />Building better living<br />for a brighter tomorrow</p>
        </header>
        <div className="hero-copy">
          <h1>Satu platform untuk kemajuan bersama.</h1>
          <p>Transparan. Terintegrasi. Lebih baik. Didukung oleh AI untuk keputusan yang lebih tepat dan masa depan yang lebih baik.</p>
          <ul className="hero-features">
            <Feature icon="◫" title="Terintegrasi" text="Seluruh divisi dalam satu ekosistem." />
            <Feature icon="✦" title="Didukung AI" text="Insight cerdas untuk aksi yang lebih cepat." />
            <Feature icon="⌾" title="Aman & terpercaya" text="Data perusahaan terlindungi." />
            <Feature icon="⌘" title="Kolaboratif" text="Membangun bersama, mencapai lebih." />
          </ul>
        </div>
        <footer className="hero-footer">
          <p>“Teknologi hari ini,<br />untuk kehidupan yang lebih baik esok.”</p>
          <div className="hero-metrics" aria-label="ALOS snapshot">
            <span><strong>6</strong>Divisi</span>
            <span><strong>50+</strong>Tim members</span>
            <span><strong>100+</strong>Proyek berjalan</span>
          </div>
        </footer>
      </aside>

      <section className="login-pane" aria-labelledby="login-title">
        <div className="language-chip" aria-label="Bahasa antarmuka">◉&nbsp; Bahasa Indonesia</div>
        <div className="login-card">
          <Brand lockup="dark" />
          <div className="login-intro">
            <h1 id="login-title">Selamat datang</h1>
            <p>Masuk ke akun Anda untuk mengakses ALOS.</p>
          </div>
          <form className="login-form" onSubmit={submit}>
            <label htmlFor="email">Email</label>
            <div className="login-input-wrap">
              <span aria-hidden="true" className="input-icon">✉</span>
              <input
                autoComplete="username"
                id="email"
                name="email"
                onChange={(event) => setEmail(event.target.value)}
                placeholder="nama@perusahaan.com"
                required
                type="email"
                value={email}
              />
            </div>
            <label htmlFor="password">Password</label>
            <div className="login-input-wrap">
              <span aria-hidden="true" className="input-icon">▣</span>
              <input
                autoComplete="current-password"
                id="password"
                minLength={16}
                name="password"
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Masukkan password"
                required
                type={showPassword ? "text" : "password"}
                value={password}
              />
              <button
                aria-label={showPassword ? "Sembunyikan password" : "Tampilkan password"}
                className="password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                type="button"
              >
                {showPassword ? "Sembunyikan" : "Tampilkan"}
              </button>
            </div>
            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button className="login-submit" disabled={submitting} type="submit">
              {submitting ? "Memverifikasi…" : "Masuk"}<span aria-hidden="true">→</span>
            </button>
          </form>
          <div className="access-note"><span aria-hidden="true">i</span><p><strong>Belum memiliki akses?</strong>Hubungi administrator ALOS pada divisi IT perusahaan.</p></div>
        </div>
        <footer className="login-footer">Kebijakan Privasi <span /> Syarat & Ketentuan <span /> Bantuan<br /><small>© 2026 PT. Andara Rejo Makmur. All rights reserved.</small></footer>
      </section>
    </main>
  );
}

function Brand({ lockup }: { lockup: "dark" | "light" }) {
  return (
    <div className={`brand-lockup brand-${lockup}`}>
      <span aria-hidden="true" className="brand-mark">A</span>
      <span><strong>ALOS</strong><small>Integrated Business Platform<br />PT. Andara Rejo Makmur</small></span>
    </div>
  );
}

function Feature({ icon, text, title }: { icon: string; text: string; title: string }) {
  return <li><span aria-hidden="true" className="feature-icon">{icon}</span><p><strong>{title}</strong><small>{text}</small></p></li>;
}
