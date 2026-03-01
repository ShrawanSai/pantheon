"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, Users, CreditCard, LogOut, MessageSquare } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useMemo } from "react";

import { Button } from "@/components/ui/button";
import { getMyWallet } from "@/lib/api/users";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { useUIStore } from "@/lib/stores/ui-store";

import { ThemeToggle } from "@/components/ui/theme-toggle";

// Temporary mock data for rooms
const MOCK_ROOMS = [
    { id: "1", name: "Alpha Exploration", mode: "auto", goal: "Find out the best strategy for Q4" },
    { id: "2", name: "Dev Discussion", mode: "team", goal: "Tech stack review" }
];

export function Sidebar() {
    const pathname = usePathname();
    const sidebarOpen = useUIStore((state) => state.sidebarOpen);

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

    const getModeColor = (mode: string) => {
        switch (mode) {
            case 'solo': return 'bg-mode-solo/20 text-mode-solo ring-mode-solo/50';
            case 'team': return 'bg-mode-team/20 text-mode-team ring-mode-team/50';
            case 'auto': return 'bg-mode-auto/20 text-mode-auto ring-mode-auto/50';
            default: return 'bg-accent/20 text-accent ring-accent/50';
        }
    };

    const getModeLabel = (mode: string) => {
        switch (mode) {
            case 'solo': return 'Solo Chat';
            case 'team': return 'Team Discussion';
            case 'auto': return 'Auto Best Answer';
            default: return 'Chat';
        }
    };

    return (
        <aside
            className={[
                "flex flex-col h-screen w-[260px] flex-shrink-0 border-r border-border bg-sidebar transition-all overflow-hidden",
                sidebarOpen ? "block absolute z-50 shadow-2xl lg:relative lg:shadow-none" : "hidden lg:flex"
            ].join(" ")}
        >
            <div className="flex items-center justify-between p-4 pb-2">
                <div className="text-xl font-bold tracking-tight text-accent">Pantheon</div>
                <Button size="sm" className="h-8 w-8 rounded-full p-0 bg-accent hover:bg-accent-hover text-white">
                    <Plus className="h-4 w-4" />
                </Button>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-6">
                <div>
                    <div className="mb-2 px-1 text-xs font-semibold uppercase tracking-wider text-muted">Recent Rooms</div>
                    <div className="space-y-1">
                        {MOCK_ROOMS.map((room) => {
                            const isActive = pathname === `/rooms/${room.id}`;
                            return (
                                <Link
                                    key={room.id}
                                    href={`/rooms/${room.id}`}
                                    className={[
                                        "flex flex-col gap-1 rounded-lg p-3 transition-colors",
                                        isActive
                                            ? "bg-elevated border-l-4 border-l-accent shadow-sm"
                                            : "hover:bg-elevated border-l-4 border-l-transparent"
                                    ].join(" ")}
                                >
                                    <div className="flex items-center justify-between">
                                        <span className="text-sm font-bold text-foreground truncate">{room.name}</span>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ring-1 font-medium ${getModeColor(room.mode)}`}>
                                            {getModeLabel(room.mode)}
                                        </span>
                                    </div>
                                    <span className="text-xs text-muted truncate max-w-[200px]">{room.goal}</span>
                                </Link>
                            );
                        })}
                    </div>
                </div>
            </div>

            <div className="mt-auto border-t border-border p-3 space-y-1">
                <Link
                    href="/agents"
                    className={[
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-elevated",
                        pathname.startsWith("/agents") ? "bg-accent/10 text-accent" : "text-secondary hover:text-foreground"
                    ].join(" ")}
                >
                    <Users className="h-4 w-4" />
                    My Agents
                </Link>
                <Link
                    href="/billing"
                    className={[
                        "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-elevated",
                        pathname.startsWith("/billing") ? "bg-accent/10 text-accent" : "text-secondary hover:text-foreground"
                    ].join(" ")}
                >
                    <CreditCard className="h-4 w-4" />
                    <div className="flex flex-1 items-center justify-between">
                        <span>Billing</span>
                        <span className="text-xs text-muted font-mono">
                            ${walletQuery.isLoading ? "..." : (walletQuery.data?.balance ? Number(walletQuery.data.balance).toFixed(2) : "0.00")}
                        </span>
                    </div>
                </Link>

                <div className="pt-2 mt-2 border-t border-border">
                    <div className="flex items-center justify-between px-3 py-2">
                        <div className="flex flex-col min-w-0">
                            <span className="text-[10px] font-medium text-muted truncate uppercase tracking-tight">Active User</span>
                            <span className="text-xs font-medium text-foreground truncate">user@example.com</span>
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
