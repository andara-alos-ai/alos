import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import { SessionProvider } from "@/components/session-provider";
import { ToastProvider } from "@/components/ui/toast";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALOS — PT Andara Rejo Makmur",
  description: "Sistem Operasi Internal & Platform Digital Workforce PT Andara Rejo Makmur",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body>
        <SessionProvider>
          <ToastProvider>
            <AppShell>{children}</AppShell>
          </ToastProvider>
        </SessionProvider>
      </body>
    </html>
  );
}
