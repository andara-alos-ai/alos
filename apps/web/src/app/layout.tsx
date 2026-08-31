import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { SessionProvider } from "@/components/session-provider";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALOS",
  description: "Platform operasi perusahaan PT Andara Rejo Makmur",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body><SessionProvider><AppShell>{children}</AppShell></SessionProvider></body>
    </html>
  );
}
