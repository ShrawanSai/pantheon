import "./globals.css";
import type { Metadata } from "next";
import { ReactNode } from "react";
import { AppProviders } from "@/components/providers/app-providers";

export const metadata: Metadata = {
  title: "Pantheon Web",
  description: "Pantheon MVP web shell"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[--bg-base] text-[--text-primary] antialiased">
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
