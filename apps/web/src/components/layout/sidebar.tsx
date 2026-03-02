"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, Users, CreditCard, LogOut, Store, Loader2, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { getMyWallet } from "@/lib/api/users";
import { listRooms, type RoomMode } from "@/lib/api/rooms";
import { getAdminSettings } from "@/lib/api/admin";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { useUIStore } from "@/lib/stores/ui-store";
import { ThemeToggle } from "@/components/ui/theme-toggle";

const MODE_LABELS: Record<RoomMode, string> = {
  manual: "Manual",
  roundtable: "Round Table",
  orchestrator: "Auto-Pilot",
};

const MODE_COLORS: Record<RoomMode, string> = {
  manual: "bg-mode-solo/20 text-mode-solo ring-mode-solo/50",
  roundtable: "bg-mode-team/20 text-mode-team ring-mode-team/50",
  orchestrator: "bg-mode-auto/20 text-mode-auto ring-mode-auto/50",
};

export function Sidebar() {
  const pathname = usePathname();
  const sidebarOpen = useUIStore(state => state.sidebarOpen);

  const walletQuery = useQuery({
    queryKey: ["wallet", "me"],
    queryFn: getMyWallet,
    staleTime: 15_000,
  });

  const roomsQuery = useQuery({
    queryKey: ["rooms"],
    queryFn: listRooms,
    staleTime: 30_000,
  });

  const adminQuery = useQuery({
    queryKey: ["admin", "settings"],
    queryFn: getAdminSettings,
    retry: false,
    staleTime: 60_000,
  });
  const isAdmin = adminQuery.isSuccess;

  const recentRooms = (roomsQuery.data ?? [])
    .slice()
    .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
    .slice(0, 5);

  async function handleSignOut() {
    const supabase = getSupabaseBrowserClient();
    await supabase.auth.signOut();
    window.location.href = "/auth/login";
  }

  const navLinkClass = (active: boolean) =>
    [
      "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-elevated",
      active ? "bg-accent/10 text-accent" : "text-secondary hover:text-foreground",
    ].join(" ");

  return (
    <aside
      className={[
        "flex flex-col h-screen w-[260px] flex-shrink-0 border-r border-border bg-sidebar transition-all overflow-hidden",
        sidebarOpen ? "block absolute z-50 shadow-2xl lg:relative lg:shadow-none" : "hidden lg:flex",
      ].join(" ")}
    >
      {/* Logo + new room button */}
      <div className="flex items-center justify-between p-4 pb-2">
        <Link href="/rooms" className="text-xl font-bold tracking-tight text-accent">Pantheon</Link>
        <Link href="/rooms">
          <Button size="sm" className="h-8 w-8 rounded-full p-0 bg-accent hover:bg-accent-hover text-white">
            <Plus className="h-4 w-4" />
          </Button>
        </Link>
      </div>

      {/* Recent rooms */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1">
        <div className="mb-2 px-1 text-xs font-semibold uppercase tracking-wider text-muted">Recent Rooms</div>

        {roomsQuery.isLoading && (
          <div className="flex items-center gap-2 px-3 py-2 text-xs text-muted">
            <Loader2 className="w-3 h-3 animate-spin" />
            Loading…
          </div>
        )}

        {recentRooms.map(room => {
          const isActive = pathname === `/rooms/${room.id}`;
          return (
            <Link
              key={room.id}
              href={`/rooms/${room.id}`}
              className={[
                "flex flex-col gap-1 rounded-lg p-3 transition-colors",
                isActive
                  ? "bg-elevated border-l-4 border-l-accent shadow-sm"
                  : "hover:bg-elevated border-l-4 border-l-transparent",
              ].join(" ")}
            >
              <div className="flex items-center justify-between">
                <span className="text-sm font-bold text-foreground truncate">{room.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ring-1 font-medium ${MODE_COLORS[room.current_mode]}`}>
                  {MODE_LABELS[room.current_mode]}
                </span>
              </div>
              {room.goal && (
                <span className="text-xs text-muted truncate max-w-[200px]">{room.goal}</span>
              )}
            </Link>
          );
        })}

        {!roomsQuery.isLoading && recentRooms.length === 0 && (
          <p className="px-3 py-2 text-xs text-muted italic">No rooms yet.</p>
        )}
      </div>

      {/* Bottom nav */}
      <div className="mt-auto border-t border-border p-3 space-y-1">
        <Link href="/agents" className={navLinkClass(pathname.startsWith("/agents"))}>
          <Users className="h-4 w-4" />
          My Agents
        </Link>

        <Link href="/marketplace" className={navLinkClass(pathname.startsWith("/marketplace"))}>
          <Store className="h-4 w-4" />
          Marketplace
        </Link>

        <Link href="/billing" className={navLinkClass(pathname.startsWith("/billing"))}>
          <CreditCard className="h-4 w-4" />
          <div className="flex flex-1 items-center justify-between">
            <span>Billing</span>
            <span className="text-xs text-muted font-mono">
              {walletQuery.isLoading ? "…" : `${Number(walletQuery.data?.balance ?? 0).toFixed(2)} cr`}
            </span>
          </div>
        </Link>

        {isAdmin && (
          <Link href="/admin" className={navLinkClass(pathname.startsWith("/admin"))}>
            <ShieldCheck className="h-4 w-4" />
            Admin
          </Link>
        )}

        <div className="pt-2 mt-2 border-t border-border">
          <div className="flex items-center justify-between px-3 py-2">
            <div className="flex flex-col min-w-0">
              <span className="text-[10px] font-medium text-muted truncate uppercase tracking-tight">Signed In</span>
            </div>
            <div className="flex items-center gap-1">
              <ThemeToggle />
              <button
                onClick={handleSignOut}
                className="w-10 h-10 flex items-center justify-center text-muted hover:text-error transition-colors rounded-xl hover:bg-elevated"
                title="Sign Out"
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}
