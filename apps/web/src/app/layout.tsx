import type { Metadata } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "AI Customer Support Platform",
  description: "A production-oriented foundation for multi-tenant AI customer support.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
