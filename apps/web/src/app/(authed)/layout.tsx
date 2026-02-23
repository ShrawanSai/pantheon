"use client";

import { useQuery } from "@tanstack/react-query";
import { Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { getMyWallet } from "@/lib/api/users";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { useUIStore } from "@/lib/stores/ui-store";

export default function AuthedLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const sidebarOpen = useUIStore((state) => state.sidebarOpen);
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);
  const walletQuery = useQuery({
    queryKey: ["wallet", "me"],
    queryFn: getMyWallet,
    staleTime: 15_000
  });

  async function handleSignOut() {
    const supabase = getSupabaseBrowserClient();
    await supabase.auth.signOut();
    window.location.href = "/auth/login";
  }

  const navItems = [
    { href: "/rooms", label: "Rooms" },
    { href: "/agents", label: "Agents" },
    { href: "/billing", label: "Billing" }
  ];

  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[240px_1fr]">
      <aside
        className={[
          "border-[--border] bg-[--bg-surface] p-4 lg:border-r",
          sidebarOpen ? "block" : "hidden lg:block"
        ].join(" ")}
      >
        <div className="text-lg font-bold">Pantheon</div>
        <nav className="mt-4 grid gap-1 text-sm">
          {navItems.map((item) => {
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={isActive ? "page" : undefined}
                className={[
                  "rounded-md px-3 py-2 text-zinc-200 hover:bg-[--bg-elevated]",
                  isActive ? "bg-[--accent]/20 text-[--text-primary] ring-1 ring-[--accent]/50" : ""
                ].join(" ")}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="mt-4 rounded-md border border-dashed border-[--border] px-3 py-2 text-xs text-[--text-muted]">
          Credits: {walletQuery.isLoading ? "..." : walletQuery.data?.balance ?? "-"}
        </div>
        <Button type="button" variant="ghost" className="mt-3 w-full" onClick={handleSignOut}>
          Sign out
        </Button>
      </aside>
      <div className="grid grid-rows-[auto_1fr]">
        <header className="border-b border-[--border] bg-[--bg-surface] px-4 py-3">
          <Button type="button" variant="ghost" size="sm" onClick={toggleSidebar} aria-label="Toggle navigation">
            <Menu className="h-4 w-4" />
          </Button>
        </header>
        <main className="p-4">{children}</main>
      </div>
    </div>
  );
}
