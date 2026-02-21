import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";
import { ReactNode } from "react";

export const metadata: Metadata = {
  title: "Pantheon Web",
  description: "Pantheon MVP web shell"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <header className="topbar">
            <strong>Pantheon</strong>
            <nav>
              <Link href="/">Home</Link>
              <Link href="/auth/login">Login</Link>
              <Link href="/auth/callback">Auth Callback</Link>
            </nav>
          </header>
          <main className="main">{children}</main>
        </div>
      </body>
    </html>
  );
}

