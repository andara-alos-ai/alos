import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "ALOS | Andara Leverage Operating System",
  description: "ALOS operating dashboard for PT Andara Rejo Makmur",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
