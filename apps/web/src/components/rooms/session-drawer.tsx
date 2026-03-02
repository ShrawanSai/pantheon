"use client";

import { useRef, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Plus, Loader2, MessageSquare, Check, Pencil, Trash2 } from "lucide-react";
import { createRoomSession, renameSession, deleteSession, type SessionRead } from "@/lib/api/sessions";
import { debugError, debugLog } from "@/lib/debug";

type Props = {
  roomId: string;
  sessions: SessionRead[];
  selectedSessionId: string;
  onSelect: (sessionId: string) => void;
  onClose: () => void;
};

function formatSessionDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (d.toDateString() === today.toDateString()) return `Today · ${time}`;
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday · ${time}`;
  return d.toLocaleDateString([], { month: "short", day: "numeric" }) + ` · ${time}`;
}

function SessionItem({
  session,
  index,
  isActive,
  roomId,
  onSelect,
  onDeleted,
}: {
  session: SessionRead;
  index: number;
  isActive: boolean;
  roomId: string;
  onSelect: () => void;
  onDeleted: (sessionId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  const renameMutation = useMutation({
    mutationFn: (name: string) => renameSession(session.id, name),
    onMutate: (name) => {
      debugLog("session-drawer", "rename_start", {
        roomId,
        sessionId: session.id,
        from: session.name,
        to: name,
      });
    },
    onSuccess: () => {
      debugLog("session-drawer", "rename_success", {
        roomId,
        sessionId: session.id,
      });
      queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
      setEditing(false);
    },
    onError: (error) => {
      debugError("session-drawer", "rename_failed", {
        roomId,
        sessionId: session.id,
        error,
      });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => deleteSession(roomId, session.id),
    onMutate: () => {
      debugLog("session-drawer", "delete_start", {
        roomId,
        sessionId: session.id,
      });
    },
    onSuccess: async () => {
      debugLog("session-drawer", "delete_success", {
        roomId,
        sessionId: session.id,
      });
      await queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
      onDeleted(session.id);
    },
    onError: (error) => {
      debugError("session-drawer", "delete_failed", {
        roomId,
        sessionId: session.id,
        error,
      });
    },
  });

  function startEdit(e: React.MouseEvent) {
    e.stopPropagation();
    setDraft(session.name ?? `Session ${index}`);
    setEditing(true);
    // Focus after render
    setTimeout(() => inputRef.current?.focus(), 0);
  }

  function commitRename() {
    const trimmed = draft.trim();
    if (!trimmed || trimmed === (session.name ?? `Session ${index}`)) {
      setEditing(false);
      return;
    }
    renameMutation.mutate(trimmed);
  }

  function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (deleteMutation.isPending || renameMutation.isPending) {
      return;
    }
    const confirmed = window.confirm(`Delete "${displayName}"? This cannot be undone.`);
    if (!confirmed) {
      return;
    }
    deleteMutation.mutate();
  }

  const displayName = session.name ?? `Session ${index}`;

  return (
    <div
      className={`group relative flex items-center gap-3 rounded-xl p-3.5 transition-all active:scale-[0.98] border cursor-pointer ${
        isActive
          ? "border-accent/40 bg-accent/8 shadow-sm"
          : "border-border bg-elevated/50 hover:bg-elevated hover:border-border"
      }`}
      onClick={onSelect}
    >
      {/* Session number circle */}
      <div
        className={`w-9 h-9 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${
          isActive
            ? "bg-accent text-white"
            : "bg-elevated text-muted border border-border"
        }`}
      >
        {index}
      </div>

      {/* Name / edit field */}
      <div className="flex-1 min-w-0" onClick={e => editing && e.stopPropagation()}>
        {editing ? (
          <input
            ref={inputRef}
            value={draft}
            onChange={e => setDraft(e.target.value)}
            onBlur={commitRename}
            onKeyDown={e => {
              if (e.key === "Enter") { e.preventDefault(); commitRename(); }
              if (e.key === "Escape") { setEditing(false); }
            }}
            className="w-full text-sm font-semibold bg-white dark:bg-surface border border-accent rounded-lg px-2 py-1 outline-none text-foreground"
            maxLength={200}
            onClick={e => e.stopPropagation()}
          />
        ) : (
          <div className="flex items-center gap-1.5">
            <span className={`text-sm font-semibold truncate ${isActive ? "text-accent" : "text-foreground"}`}>
              {displayName}
            </span>
            {!session.name && (
              <span className="text-[10px] text-muted/60 shrink-0">auto</span>
            )}
            {isActive && (
              <span className="text-[10px] font-bold uppercase tracking-wider text-accent bg-accent/10 px-1.5 py-0.5 rounded-full shrink-0">
                Active
              </span>
            )}
          </div>
        )}
        {!editing && (
          <p className="text-xs text-muted mt-0.5 font-mono">
            {formatSessionDate(session.created_at)}
          </p>
        )}
      </div>

      {/* Right side: checkmark or rename button */}
      <div className="flex items-center gap-1 shrink-0">
        {renameMutation.isPending || deleteMutation.isPending ? (
          <Loader2 className="h-4 w-4 text-accent animate-spin" />
        ) : isActive ? (
          <Check className="h-4 w-4 text-accent" />
        ) : null}
        {!editing && !renameMutation.isPending && !deleteMutation.isPending && (
          <button
            onClick={handleDelete}
            className="opacity-0 group-hover:opacity-100 w-7 h-7 flex items-center justify-center rounded-full hover:bg-elevated text-muted hover:text-error transition-all"
            title="Delete session"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        )}
        {!editing && !renameMutation.isPending && (
          <button
            onClick={startEdit}
            className="opacity-0 group-hover:opacity-100 w-7 h-7 flex items-center justify-center rounded-full hover:bg-elevated text-muted hover:text-foreground transition-all"
            title="Rename session"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

export function SessionDrawer({ roomId, sessions, selectedSessionId, onSelect, onClose }: Props) {
  const queryClient = useQueryClient();

  const createSessionMutation = useMutation({
    mutationFn: () => createRoomSession(roomId),
    onMutate: () => {
      debugLog("session-drawer", "create_start", { roomId });
    },
    onSuccess: async (session) => {
      debugLog("session-drawer", "create_success", {
        roomId,
        sessionId: session.id,
      });
      await queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
      onSelect(session.id);
      onClose();
    },
    onError: (error) => {
      debugError("session-drawer", "create_failed", { roomId, error });
    },
  });

  // Sort oldest-first to assign stable session numbers
  const sorted = [...sessions].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
  );

  function handleSelect(sessionId: string) {
    debugLog("session-drawer", "select_session", {
      roomId,
      selectedSessionId: sessionId,
    });
    onSelect(sessionId);
    onClose();
  }

  function handleDeleted(sessionId: string) {
    const deletedIndex = sorted.findIndex((session) => session.id === sessionId);
    const remaining = sorted.filter((session) => session.id !== sessionId);
    if (selectedSessionId !== sessionId) {
      return;
    }
    if (remaining.length === 0) {
      debugLog("session-drawer", "delete_selected_last_session", {
        roomId,
        deletedSessionId: sessionId,
      });
      onClose();
      return;
    }
    const fallbackIndex = deletedIndex >= 0 ? Math.min(deletedIndex, remaining.length - 1) : 0;
    debugLog("session-drawer", "delete_selected_fallback", {
      roomId,
      deletedSessionId: sessionId,
      fallbackSessionId: remaining[fallbackIndex].id,
    });
    onSelect(remaining[fallbackIndex].id);
  }

  return (
    <div className="fixed inset-0 z-50 flex flex-col justify-end sm:items-center sm:justify-center sm:p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel — bottom sheet on mobile, centered card on sm+ */}
      <div className="relative w-full sm:max-w-sm bg-white dark:bg-surface rounded-t-2xl sm:rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[75vh] sm:max-h-[80vh]">
        {/* Drag handle (mobile only) */}
        <div className="flex justify-center pt-3 pb-1 sm:hidden">
          <div className="w-10 h-1 rounded-full bg-border" />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-5 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <MessageSquare className="h-4 w-4 text-accent" />
            <h2 className="text-base font-bold text-foreground">Sessions</h2>
            <span className="text-xs text-muted font-mono bg-elevated px-1.5 py-0.5 rounded-full">
              {sessions.length}
            </span>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full flex items-center justify-center text-muted hover:text-foreground hover:bg-elevated transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* New session button */}
        <div className="px-4 pt-3 pb-2">
          <button
            onClick={() => createSessionMutation.mutate()}
            disabled={createSessionMutation.isPending}
            className="w-full flex items-center justify-center gap-2 h-10 rounded-xl border border-dashed border-accent/50 text-accent text-sm font-medium hover:bg-accent/5 transition-colors disabled:opacity-50"
          >
            {createSessionMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Plus className="h-4 w-4" />
            )}
            {createSessionMutation.isPending ? "Creating…" : "New Session"}
          </button>
        </div>

        {/* Session list */}
        <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
          {sorted.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted">
              No sessions yet. Create one above.
            </div>
          ) : (
            sorted.map((session, idx) => (
              <SessionItem
                key={session.id}
                session={session}
                index={idx + 1}
                isActive={session.id === selectedSessionId}
                roomId={roomId}
                onSelect={() => handleSelect(session.id)}
                onDeleted={handleDeleted}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}
