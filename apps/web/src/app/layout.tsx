import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "ALOS Genesis MVP1",
  description: "Genesis AI Executive Operating Layer",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="id">
      <body>{children}</body>
    </html>
  );
}
