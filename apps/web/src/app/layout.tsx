import type { Metadata } from "next";

import { AppShell } from "@/components/app-shell";
import "./globals.css";

export const metadata: Metadata = {
  title: "ALOS Internal v1",
  description: "Platform operasi internal PT Andara Rejo Makmur",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body><AppShell>{children}</AppShell></body>
    </html>
  );
}
