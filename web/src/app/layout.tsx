import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "Dispute Assistant",
  description: "Demo assistant for card and account disputes, grounded in Regulations E and Z.",
  robots: { index: false, follow: false },
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="flex min-h-screen flex-col antialiased">
        <header>
          <div role="note" className="border-b border-[var(--line)] bg-[var(--panel)] px-4 py-2 text-center text-xs text-[var(--muted)]">
            Demonstration only. Not financial or legal advice. Do not enter real account details.
          </div>
          <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-4 pt-4">
            <span className="font-semibold">Dispute Assistant</span>
            <span className="text-xs text-[var(--muted)]">Grounded in 12 CFR 1005 and 1026</span>
          </div>
        </header>
        <main className="flex flex-1 flex-col">{children}</main>
      </body>
    </html>
  );
}
