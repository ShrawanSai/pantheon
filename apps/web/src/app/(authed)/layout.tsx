"use client";

import { Menu } from "lucide-react";
import { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { useUIStore } from "@/lib/stores/ui-store";
import { Sidebar } from "@/components/layout/sidebar";

export default function AuthedLayout({ children }: { children: ReactNode }) {
  const toggleSidebar = useUIStore((state) => state.toggleSidebar);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden relative">
        {/* Mobile Header overlay toggle */}
        <div className="lg:hidden absolute top-4 left-4 z-40">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={toggleSidebar}
            aria-label="Toggle navigation"
            className="h-10 w-10 rounded-full bg-surface shadow-md border border-border flex items-center justify-center p-0"
          >
            <Menu className="h-5 w-5 text-foreground" />
          </Button>
        </div>
        <main className="flex-1 overflow-auto h-full relative">
          {children}
        </main>
      </div>
    </div>
  );
}
