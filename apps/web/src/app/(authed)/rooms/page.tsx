"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Search, Plus, Landmark, Bell, Settings2, Loader2, MessageSquare, PlusCircle } from "lucide-react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { CreateRoomModal } from "@/components/rooms/create-room-modal";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { createRoom, deleteRoom, listRooms, type RoomMode, type RoomRead } from "@/lib/api/rooms";

type RoomUiMode = "solo" | "team" | "auto";

type CreateRoomFormState = {
  name: string;
  uiMode: RoomUiMode;
};

const ROOM_MODE_LABELS: Record<RoomMode, string> = {
  manual: "Solo Chat",
  roundtable: "Team Discussion",
  orchestrator: "Auto Best Answer"
};

const ROOM_MODE_DESCRIPTIONS: Record<RoomUiMode, string> = {
  solo: "One primary agent replies each turn, like a normal chat.",
  team: "A team of agents replies in sequence so you get multiple perspectives.",
  auto: "A manager coordinates specialists and returns one consolidated answer."
};

function mapUiModeToApiMode(mode: RoomUiMode): RoomMode {
  if (mode === "solo") return "manual";
  if (mode === "team") return "roundtable";
  return "orchestrator";
}

function timeAgo(iso: string): string {
  const date = new Date(iso);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "Just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// Dummy abstract images for recent rooms to make it look premium
const ABSTRACT_COVERS = [
  "https://lh3.googleusercontent.com/aida-public/AB6AXuBcrmAwIk-TlgAH7ab6SgW_BCpY9zepMP3bzcj0dWigUUY2qdWxNFXAcVHt-8ZdyaSViuNj3iegU7Pw37qXE8su5eLjU7gRAhBE2UuiwlP-mIc0XJXSABiGCRSW91oiH72JDGZOdkVicYuEesXff_sQzQt5U1K1gCldyxFOTTAZ30ZTZp2BuAqG7Db-WV0lxmtoJU6r7KlY-Q7TGLuUamak6VihnVil-8IQX_PrE53c2cXO4tfjPYZbV_4cG6rpMRo-3Uhy-RrnWcs",
  "https://lh3.googleusercontent.com/aida-public/AB6AXuBxEjaeWW2RSwjuGL0QjeAufBBwDFScjwqTkE-kYk-tjkvKhcG_VxilUA2XLlhNQY0eXZ1xfNtE8RIxWjXIEu04IZb3TIjI63Bg9oMFl5i5rpmpZ4XK_83SYu4cMjRv6i3vUvAtHGojZa1qPXHbh6aPJNIAn9v3Rx6B3NUWcII1_u_6vCUF1S0l-7scYVGB6qgX-qQS2IYXzxyxJ0S62Uai9leB9zpeGtGxozji98InHOkqr9tIQr1YLaxdItFHt_FiQ2SeQaxJ8R4",
  "https://lh3.googleusercontent.com/aida-public/AB6AXuBj-BmnRa7hwbVSvlH7HsNQl4dk55rz7qjfFK82Nqaw83lTJ3l7eYrSNMWM0XcL9wvAZtHgZ4dBycRJoJ9v4ncib3XgE7buXsxBuGkQtOk1UJa079WEdizt-8OEqUMBt_y1qm3Plf9Y8WQnzkdaxujbOyNI3-u3ZOfoOkuwg_Exymga2zeg1SB_1nO9X4x1dabhGpFtN2BHpKqxl0nQ7vukcvnfeeSNziz_iE77BkrMQDqb83bBpZqLZBqQ5PbtgU0CdP54RFPalRk",
];

export default function RoomsPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RoomRead | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [form, setForm] = useState<CreateRoomFormState>({ name: "", uiMode: "solo" });
  const [formError, setFormError] = useState("");

  const roomsQuery = useQuery({ queryKey: ["rooms"], queryFn: listRooms });

  const sortedRooms = useMemo(() => {
    let list = [...(roomsQuery.data || [])].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(r => r.name.toLowerCase().includes(q) || ROOM_MODE_LABELS[r.current_mode].toLowerCase().includes(q));
    }
    return list;
  }, [roomsQuery.data, searchQuery]);

  const recentRooms = sortedRooms.slice(0, 3);
  const libraryRooms = sortedRooms.slice(3); // or show all in library if preferred, but let's separate them

  const createRoomMutation = useMutation({
    mutationFn: async () => {
      const trimmedName = form.name.trim();
      if (!trimmedName) throw new ApiError(422, "Room name is required.");
      return createRoom({ name: trimmedName, current_mode: mapUiModeToApiMode(form.uiMode) });
    },
    onSuccess: () => {
      setCreateOpen(false);
      setForm({ name: "", uiMode: "solo" });
      queryClient.invalidateQueries({ queryKey: ["rooms"] });
    },
    onError: (error) => {
      setFormError(error instanceof ApiError ? error.detail : "Failed to create room.");
    }
  });

  const deleteRoomMutation = useMutation({
    mutationFn: (roomId: string) => deleteRoom(roomId),
    onSuccess: () => {
      setDeleteTarget(null);
      queryClient.invalidateQueries({ queryKey: ["rooms"] });
    }
  });

  return (
    <div className="flex h-full w-full flex-col bg-background overflow-hidden relative font-sans">
      {/* Header */}
      <header className="flex flex-col gap-4 px-6 md:px-10 pt-8 pb-4 bg-background z-20 sticky top-0">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-10 h-10 rounded-full bg-foreground text-accent">
              <Landmark className="w-5 h-5 text-background" />
            </div>
            <div>
              <h1 className="text-2xl font-bold italic tracking-tight text-foreground font-serif">Pantheon</h1>
            </div>
          </div>
          <button className="relative flex items-center justify-center w-10 h-10 rounded-full hover:bg-foreground/5 transition-colors">
            <Bell className="w-5 h-5 text-foreground" />
            <span className="absolute top-2 right-2 w-2 h-2 bg-accent rounded-full border-2 border-background"></span>
          </button>
        </div>

        {/* Search */}
        <div className="relative w-full max-w-2xl">
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none">
            <Search className="w-5 h-5" />
          </span>
          <input
            className="w-full bg-surface border border-border rounded-xl py-3 pl-10 pr-4 text-sm font-medium placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent focus:border-accent transition-all shadow-sm text-foreground"
            placeholder="Search rooms, sessions or history..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
          />
        </div>
      </header>

      {/* Main Content Scroll Area */}
      <main className="flex-1 overflow-y-auto pb-24 px-6 md:px-10">

        {roomsQuery.isLoading ? (
          <div className="flex items-center justify-center py-20 text-muted">
            <Loader2 className="w-6 h-6 animate-spin mr-2" />
            <span>Loading rooms...</span>
          </div>
        ) : null}

        {!roomsQuery.isLoading && sortedRooms.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center gap-4">
            <div className="w-16 h-16 rounded-full bg-accent/10 flex items-center justify-center">
              <Landmark className="w-8 h-8 text-accent opacity-50" />
            </div>
            <h2 className="text-xl font-bold font-serif text-foreground">Welcome to Pantheon</h2>
            <p className="text-muted max-w-sm text-sm">Create your first room to start collaborating with AI agents.</p>
            <Button onClick={() => setCreateOpen(true)} className="mt-4 bg-accent hover:bg-accent-hover text-white rounded-full px-6">
              <Plus className="w-4 h-4 mr-2" />
              Create Room
            </Button>
          </div>
        ) : null}

        {/* Hero Section: Recent Rooms */}
        {recentRooms.length > 0 && (
          <section className="mb-10">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-foreground font-serif">Recent Rooms</h2>
              <button className="text-xs font-semibold text-accent uppercase tracking-wider hover:opacity-80">View All</button>
            </div>

            {/* Horizontal Scroll Snap */}
            <div className="flex gap-4 overflow-x-auto snap-x snap-mandatory pb-4 hide-scrollbar">
              {recentRooms.map((room, idx) => (
                <Link key={room.id} href={`/rooms/${room.id}`} className="snap-center shrink-0 w-[280px] md:w-[320px] bg-surface rounded-2xl p-4 shadow-sm border border-border flex flex-col group transition-transform hover:border-accent hover:shadow-md cursor-pointer">
                  <div className="h-32 w-full rounded-xl bg-elevated mb-4 relative overflow-hidden">
                    <img
                      alt="Room visual"
                      className="w-full h-full object-cover opacity-60 mix-blend-overlay group-hover:scale-105 transition-transform duration-700"
                      src={ABSTRACT_COVERS[idx % ABSTRACT_COVERS.length]}
                    />
                    <div className="absolute top-2 right-2 bg-black/40 backdrop-blur-md px-2 py-1 rounded-lg text-xs font-medium text-white flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-green-400"></span>
                      Active
                    </div>
                  </div>
                  <h3 className="text-lg font-serif font-semibold text-foreground mb-1 truncate">{room.name}</h3>
                  <p className="text-xs text-muted mb-3 font-medium flex items-center gap-1">
                    <span className="font-semibold px-2 py-0.5 rounded-md bg-accent/10 text-accent uppercase tracking-wide text-[10px]">
                      {ROOM_MODE_LABELS[room.current_mode]}
                    </span>
                  </p>
                  <div className="mt-auto pt-3 border-t border-border flex justify-between items-center">
                    <p className="text-xs text-muted italic">Edited {timeAgo(room.updated_at || room.created_at)}</p>
                    <button onClick={(e) => { e.preventDefault(); setDeleteTarget(room); }} className="text-muted hover:text-error transition-colors p-1 z-10">
                      <span className="text-xs opacity-0 group-hover:opacity-100 font-semibold tracking-wide">DELETE</span>
                    </button>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}

        {/* Library Grid */}
        {libraryRooms.length > 0 && (
          <section>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-foreground font-serif">Library</h2>
              <button className="w-8 h-8 flex items-center justify-center rounded-full border border-border text-foreground hover:bg-foreground hover:text-background transition-colors">
                <Settings2 className="w-4 h-4" />
              </button>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3 pb-8">
              {libraryRooms.map((room) => (
                <div key={room.id} className="relative flex items-center p-4 bg-surface rounded-xl border border-border shadow-sm hover:border-accent hover:shadow-md transition-all group">
                  <Link href={`/rooms/${room.id}`} className="absolute inset-0 z-0"></Link>
                  <div className="relative shrink-0 mr-4 z-10 pointer-events-none">
                    <div className="h-10 w-10 rounded-full bg-elevated border-2 border-background flex items-center justify-center text-foreground font-bold">
                      {room.name.substring(0, 2).toUpperCase()}
                    </div>
                    <span className="absolute -bottom-1 -right-1 flex h-4 w-4 items-center justify-center rounded-full bg-background ring-2 ring-background">
                      <span className="h-2 w-2 rounded-full bg-muted"></span>
                    </span>
                  </div>
                  <div className="flex-1 min-w-0 z-10 pointer-events-none">
                    <div className="flex justify-between items-baseline mb-1">
                      <h4 className="text-base font-bold text-foreground truncate pr-2">{room.name}</h4>
                      <span className="text-xs text-muted font-medium shrink-0">{timeAgo(room.created_at)}</span>
                    </div>
                    <p className="text-sm text-muted truncate">{ROOM_MODE_LABELS[room.current_mode]}</p>
                  </div>
                  <div className="ml-3 shrink-0 flex flex-col items-end gap-1 z-10 pointer-events-none">
                    <div className="flex items-center gap-1 bg-accent/10 px-2 py-0.5 rounded text-[10px] font-bold text-accent">
                      <MessageSquare className="w-3 h-3" /> --
                    </div>
                  </div>
                  <button
                    onClick={(e) => { e.preventDefault(); e.stopPropagation(); setDeleteTarget(room); }}
                    className="absolute right-4 bottom-2 text-muted hover:text-error transition-colors p-1 z-20 opacity-0 group-hover:opacity-100"
                  >
                    <span className="text-[10px] font-semibold tracking-wide">DEL</span>
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>

      {/* Floating Action Button */}
      <button
        onClick={() => setCreateOpen(true)}
        className="absolute bottom-10 right-10 w-14 h-14 bg-accent text-white rounded-full shadow-lg flex items-center justify-center hover:scale-105 hover:bg-accent-hover transition-all z-30"
      >
        <Plus className="w-6 h-6" />
      </button>

      <CreateRoomModal open={createOpen} onClose={() => setCreateOpen(false)} />

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete Room"
        description={`Delete '${deleteTarget?.name || "this room"}'? This action cannot be undone.`}
        confirmLabel="Delete Room"
        loading={deleteRoomMutation.isPending}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteRoomMutation.mutate(deleteTarget.id);
        }}
      />
    </div>
  );
}

