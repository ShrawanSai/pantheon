"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { MoreVertical, Paperclip, Send, ThumbsUp, CornerDownLeft, ArrowLeft } from "lucide-react";

import { ManageRoomPanel } from "@/components/rooms/manage-room-panel";
import { listAgents, type AgentRead } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import {
  assignRoomAgent,
  getRoom,
  listRoomAgents,
  removeRoomAgent,
  updateRoomMode,
  type RoomAgentRead,
  type RoomMode
} from "@/lib/api/rooms";
import {
  createRoomSession,
  listRoomSessions,
  listSessionMessages,
  listSessionTurns,
  submitTurn,
  submitTurnStream,
  type SessionRead,
  type StreamEvent
} from "@/lib/api/sessions";
import {
  listRoomFiles,
  uploadFile,
} from "@/lib/api/files";

type RoomWorkspacePageProps = {
  params: {
    roomId: string;
  };
};

const MODE_OPTIONS: Array<{ value: RoomMode; label: string; icon: string }> = [
  { value: "manual", label: "Manual", icon: "touch_app" },
  { value: "roundtable", label: "Round Table", icon: "groups" },
  { value: "orchestrator", label: "Auto-Pilot", icon: "smart_toy" },
];

/** Returns initials (up to 2 chars) for an agent name */
function initials(name: string): string {
  return name
    .split(/\s+/)
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

/** Hue derived from agent name for a stable unique colour */
function agentHue(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return Math.abs(hash) % 360;
}

function formatTime(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function formatDateGroup(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const today = new Date();
  const yesterday = new Date(today);
  yesterday.setDate(yesterday.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return `Today, ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`;
  if (d.toDateString() === yesterday.toDateString()) return `Yesterday`;
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

export default function RoomWorkspacePage({ params }: RoomWorkspacePageProps) {
  const router = useRouter();
  const roomId = params.roomId;
  const queryClient = useQueryClient();

  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [messageInput, setMessageInput] = useState("");
  const [composerError, setComposerError] = useState("");
  const [streamingEnabled] = useState(true);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamDraft, setStreamDraft] = useState("");
  const [streamAgentName, setStreamAgentName] = useState("");
  const [managePanelOpen, setManagePanelOpen] = useState(false);
  // Manual mode – which agents are currently "addressed"
  const [addressedAgentIds, setAddressedAgentIds] = useState<Set<string>>(new Set());
  // Feedback state: set of message IDs the user has "approved"
  const [approvedMessages, setApprovedMessages] = useState<Set<string>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Queries ─────────────────────────────────────────────────────────────
  const roomQuery = useQuery({ queryKey: ["room", roomId], queryFn: () => getRoom(roomId) });
  const roomAgentsQuery = useQuery({ queryKey: ["roomAgents", roomId], queryFn: () => listRoomAgents(roomId) });
  const allAgentsQuery = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const sessionsQuery = useQuery({ queryKey: ["roomSessions", roomId], queryFn: () => listRoomSessions(roomId) });
  const messagesQuery = useQuery({
    queryKey: ["sessionMessages", selectedSessionId],
    queryFn: () => listSessionMessages(selectedSessionId),
    enabled: Boolean(selectedSessionId),
    refetchInterval: isStreaming ? false : 4000,
  });
  const filesQuery = useQuery({ queryKey: ["roomFiles", roomId], queryFn: () => listRoomFiles(roomId) });

  const currentMode = roomQuery.data?.current_mode ?? "manual";

  // Auto-select session
  useEffect(() => {
    const sessions = sessionsQuery.data || [];
    if (!selectedSessionId && sessions.length > 0) setSelectedSessionId(sessions[0].id);
    else if (selectedSessionId && sessions.every((s) => s.id !== selectedSessionId)) {
      setSelectedSessionId(sessions[0]?.id || "");
    }
  }, [selectedSessionId, sessionsQuery.data]);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messagesQuery.data, streamDraft, isStreaming]);

  // Build a lookup from agent_id → RoomAgentRead
  const agentMap = useMemo(() => {
    const agents = allAgentsQuery.data?.agents ?? [];
    const map = new Map<string, AgentRead>();
    agents.forEach((a) => map.set(a.id, a));
    return map;
  }, [allAgentsQuery.data]);

  const roomAgents = roomAgentsQuery.data ?? [];

  // ── Mode mutation ────────────────────────────────────────────────────────
  const setModeMutation = useMutation({
    mutationFn: (mode: RoomMode) => updateRoomMode(roomId, mode),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["room", roomId] }),
  });

  // ── Session creation ─────────────────────────────────────────────────────
  const createSessionMutation = useMutation({
    mutationFn: () => createRoomSession(roomId),
    onSuccess: async (session) => {
      setSelectedSessionId(session.id);
      await queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
    },
  });

  // ── File upload ──────────────────────────────────────────────────────────
  const uploadFileMutation = useMutation({
    mutationFn: (file: File) => uploadFile(roomId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["roomFiles", roomId] }),
  });

  // ── Send turn ────────────────────────────────────────────────────────────
  async function handleSendTurn() {
    setComposerError("");
    const trimmed = messageInput.trim();
    if (!selectedSessionId) { setComposerError("Create a session first."); return; }
    if (!trimmed) return;

    // Build final message: prepend @mentions for manual mode addressed agents
    let finalMessage = trimmed;
    if (currentMode === "manual" && addressedAgentIds.size > 0) {
      const mentions = [...addressedAgentIds]
        .map((id) => agentMap.get(id)?.name ?? "")
        .filter(Boolean)
        .map((n) => `@${n}`)
        .join(" ");
      finalMessage = `${mentions} ${trimmed}`;
    }

    setMessageInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    if (!streamingEnabled) {
      try {
        await submitTurn(selectedSessionId, { message: finalMessage });
        await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
      } catch (err) {
        setComposerError(err instanceof ApiError ? err.detail : "Failed to send.");
        setMessageInput(finalMessage);
      }
      return;
    }

    setIsStreaming(true);
    setStreamDraft("");
    setStreamAgentName("Thinking...");
    try {
      await submitTurnStream(selectedSessionId, { message: finalMessage }, (event: StreamEvent) => {
        if (event.type === "chunk" && typeof event.delta === "string") {
          setStreamDraft((prev) => prev + event.delta);
        }
      });
      await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
      await queryClient.invalidateQueries({ queryKey: ["sessionTurns", selectedSessionId] });
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : "Stream failed.";
      try {
        await submitTurn(selectedSessionId, { message: finalMessage });
        await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
      } catch {
        setComposerError(detail);
        setMessageInput(finalMessage);
      }
    } finally {
      setIsStreaming(false);
      setStreamDraft("");
      setStreamAgentName("");
    }
  }

  // ── Textarea auto-grow ───────────────────────────────────────────────────
  function handleTextareaChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setMessageInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  }

  // ── Toggle addressed agent (manual mode) ─────────────────────────────────
  function toggleAddressed(agentId: string) {
    setAddressedAgentIds((prev) => {
      const next = new Set(prev);
      if (next.has(agentId)) next.delete(agentId);
      else next.add(agentId);
      return next;
    });
  }

  const messages = messagesQuery.data?.messages ?? [];
  const sessions = sessionsQuery.data ?? [];

  return (
    <div className="flex h-full flex-col bg-background-light dark:bg-background overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="flex-none bg-white dark:bg-surface border-b border-border px-4 pt-4 pb-2 z-10">
        {/* Top row */}
        <div className="flex items-center justify-between mb-3">
          <button
            onClick={() => router.push("/rooms")}
            className="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-elevated hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>

          {/* Session switcher */}
          <div className="flex items-center gap-1 max-w-[200px] overflow-x-auto">
            {sessions.slice(0, 5).map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedSessionId(s.id)}
                className={`shrink-0 h-7 px-3 rounded-full text-xs font-medium transition-colors ${s.id === selectedSessionId
                  ? "bg-accent text-white"
                  : "bg-elevated text-muted hover:text-foreground"
                  }`}
              >
                #{s.id.slice(0, 4)}
              </button>
            ))}
            <button
              onClick={() => createSessionMutation.mutate()}
              disabled={createSessionMutation.isPending}
              className="shrink-0 h-7 px-3 rounded-full text-xs border border-dashed border-border text-muted hover:border-accent hover:text-accent transition-colors"
            >
              {createSessionMutation.isPending ? "…" : "+ New"}
            </button>
          </div>

          <div className="flex items-center gap-1">
            <span className="text-xs font-medium text-muted">
              {roomAgents.length} {roomAgents.length === 1 ? "agent" : "agents"}
            </span>
            <button
              onClick={() => setManagePanelOpen(true)}
              className="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-elevated hover:text-foreground transition-colors"
            >
              <MoreVertical className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Room name */}
        <h1 className="text-center text-lg font-bold text-foreground mb-3">
          {roomQuery.data?.name ?? "Council Room"}
        </h1>

        {/* Mode selector */}
        <div className="flex gap-2 overflow-x-auto pb-1">
          {MODE_OPTIONS.map((opt) => {
            const active = currentMode === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => setModeMutation.mutate(opt.value)}
                disabled={setModeMutation.isPending}
                className={`flex h-9 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-medium transition-all active:scale-95 ${active
                  ? "bg-accent text-white shadow-sm"
                  : "bg-elevated text-muted hover:text-foreground border border-border"
                  }`}
              >
                <span className="text-[16px]">
                  {opt.value === "manual" ? "✋" : opt.value === "roundtable" ? "👥" : "🤖"}
                </span>
                {opt.label}
              </button>
            );
          })}
        </div>
      </header>

      {/* ── Message Feed ─────────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto p-4 space-y-5">
        {/* Date divider – show once at start */}
        {messages.length > 0 && (
          <div className="flex justify-center">
            <span className="px-3 py-1 rounded-full bg-elevated text-xs text-muted border border-border">
              {formatDateGroup(messages[0].created_at)}
            </span>
          </div>
        )}

        {/* Empty state */}
        {!selectedSessionId && (
          <div className="flex h-40 items-center justify-center rounded-2xl border-2 border-dashed border-border text-center">
            <div>
              <p className="font-semibold text-foreground">No Active Session</p>
              <p className="text-sm text-muted mt-1">Create a new session to begin.</p>
            </div>
          </div>
        )}

        {selectedSessionId && messages.length === 0 && !isStreaming && (
          <div className="flex flex-col items-center justify-center py-16 gap-3 text-center">
            <div className="text-4xl">🏛️</div>
            <p className="font-semibold text-foreground">The Council Awaits</p>
            <p className="text-sm text-muted max-w-xs">
              {currentMode === "manual"
                ? "Select agents to address below, then send your message."
                : currentMode === "roundtable"
                  ? "All agents will weigh in on your query."
                  : "The manager will orchestrate and synthesize responses for you."}
            </p>
          </div>
        )}

        {/* Messages */}
        {messages.map((message) => {
          const isUser = message.role === "user";

          if (isUser) {
            return (
              <div key={message.id} className="flex items-end gap-3 justify-end group">
                <div className="flex flex-col items-end gap-1 max-w-[85%]">
                  {/* @mentions in the message are highlighted */}
                  <div className="rounded-2xl rounded-tr-sm px-5 py-3.5 bg-accent text-white shadow-sm">
                    <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
                      {message.content.split(/(@\w[\w\s]*)/).map((part, i) =>
                        part.startsWith("@") ? (
                          <strong key={i} className="font-bold text-white/90 bg-white/10 rounded px-1">
                            {part}
                          </strong>
                        ) : (
                          <span key={i}>{part}</span>
                        )
                      )}
                    </p>
                  </div>
                  <span className="text-[11px] text-muted opacity-0 group-hover:opacity-100 transition-opacity">
                    {formatTime(message.created_at)}
                  </span>
                </div>
                {/* User avatar */}
                <div className="h-8 w-8 shrink-0 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xs font-bold border-2 border-white dark:border-surface">
                  U
                </div>
              </div>
            );
          }

          // Agent message
          const agentName = message.agent_name || "Agent";
          const hue = agentHue(agentName);
          const isApproved = approvedMessages.has(message.id);

          return (
            <div key={message.id} className="flex gap-3 group">
              {/* Avatar column */}
              <div className="flex flex-col items-center gap-1 shrink-0">
                <div
                  className="h-10 w-10 rounded-full flex items-center justify-center text-white text-xs font-bold border-2 border-white dark:border-surface shadow-sm relative"
                  style={{ background: `hsl(${hue},55%,50%)` }}
                >
                  {initials(agentName)}
                  <div
                    className="absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full border border-white dark:border-surface flex items-center justify-center"
                    style={{ background: `hsl(${hue},65%,40%)` }}
                  >
                    <span className="text-[8px] text-white font-bold">{agentName[0]}</span>
                  </div>
                </div>
                {/* Vertical stem line */}
                <div className="w-px flex-1 bg-border rounded-full" style={{ minHeight: 12 }} />
              </div>

              {/* Bubble */}
              <div className="flex flex-col items-start max-w-[88%] min-w-0 pb-2">
                {/* Agent name */}
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-sm font-bold text-foreground">{agentName}</span>
                </div>

                {/* Message content */}
                <div className="bg-white dark:bg-surface rounded-2xl rounded-tl-sm p-4 border border-border shadow-sm w-full">
                  <p className="text-[15px] leading-relaxed text-foreground whitespace-pre-wrap">{message.content}</p>

                  {/* Feedback row */}
                  <div className="mt-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() =>
                        setApprovedMessages((prev) => {
                          const next = new Set(prev);
                          if (next.has(message.id)) next.delete(message.id);
                          else next.add(message.id);
                          return next;
                        })
                      }
                      className={`flex items-center gap-1 px-3 py-1.5 rounded-lg border text-xs font-medium transition-colors ${isApproved
                        ? "bg-accent/10 border-accent text-accent"
                        : "bg-elevated border-border text-muted hover:text-accent hover:border-accent"
                        }`}
                    >
                      <ThumbsUp className="w-3.5 h-3.5" />
                      {isApproved ? "Noted" : "Valid"}
                    </button>
                    <button
                      onClick={() => {
                        setMessageInput(`@${agentName} `);
                        textareaRef.current?.focus();
                      }}
                      className="flex items-center gap-1 px-3 py-1.5 rounded-lg border border-border bg-elevated text-xs font-medium text-muted hover:text-accent hover:border-accent transition-colors"
                    >
                      <CornerDownLeft className="w-3.5 h-3.5" />
                      Reply
                    </button>
                  </div>
                </div>

                <span className="text-[11px] text-muted mt-1 ml-1 opacity-0 group-hover:opacity-100 transition-opacity">
                  {formatTime(message.created_at)}
                </span>
              </div>
            </div>
          );
        })}

        {/* Streaming indicator */}
        {isStreaming && (
          <div className="flex gap-3">
            <div className="h-10 w-10 shrink-0 rounded-full bg-accent/20 flex items-center justify-center border-2 border-white dark:border-surface">
              <span className="text-accent text-xs font-bold">AI</span>
            </div>
            <div className="flex flex-col items-start max-w-[88%]">
              {streamAgentName && (
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-sm font-bold text-foreground">{streamAgentName}</span>
                </div>
              )}
              <div className="bg-white dark:bg-surface rounded-2xl rounded-tl-sm p-4 border border-border shadow-sm w-full">
                {streamDraft ? (
                  <p className="text-[15px] leading-relaxed text-foreground whitespace-pre-wrap">{streamDraft}</p>
                ) : (
                  <div className="flex items-center gap-2 text-muted text-sm">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                    <span className="text-xs font-mono">
                      {currentMode === "orchestrator" ? "Synthesizer drafting..." : "Responding..."}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {composerError && (
          <div className="text-center text-sm text-error py-2">{composerError}</div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* ── Input Area ──────────────────────────────────────────────────────── */}
      <footer className="flex-none bg-white dark:bg-surface border-t border-border px-4 pt-3 pb-4">
        {/* File chips */}
        {filesQuery.data && filesQuery.data.length > 0 && (
          <div className="mb-2 flex flex-wrap gap-1.5">
            {filesQuery.data.map((f) => (
              <span
                key={f.id}
                className="text-[11px] bg-elevated px-2 py-1 rounded-lg border border-border text-muted truncate max-w-[140px]"
              >
                📎 {f.filename}
              </span>
            ))}
          </div>
        )}

        {/* Manual mode: Agent addressing chips */}
        {currentMode === "manual" && roomAgents.length > 0 && (
          <div className="flex items-center gap-2 mb-3 overflow-x-auto pb-1">
            <span className="text-[11px] font-semibold text-muted uppercase tracking-widest shrink-0">To:</span>
            {roomAgents.map((ra) => {
              const agent = agentMap.get(ra.agent_id);
              const name = agent?.name ?? ra.agent_id.slice(0, 8);
              const hue = agentHue(name);
              const active = addressedAgentIds.has(ra.agent_id);
              return (
                <button
                  key={ra.agent_id}
                  onClick={() => toggleAddressed(ra.agent_id)}
                  className={`flex items-center gap-1.5 pl-1 pr-3 py-1 rounded-full text-sm font-medium shrink-0 transition-all active:scale-95 border ${active
                    ? "text-white shadow-sm border-transparent"
                    : "text-muted border-border bg-elevated hover:bg-elevated"
                    }`}
                  style={active ? { background: `hsl(${hue},55%,50%)`, borderColor: `hsl(${hue},55%,50%)` } : {}}
                >
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
                    style={
                      active
                        ? { background: "rgba(255,255,255,0.2)", color: "white" }
                        : { background: `hsl(${hue},40%,88%)`, color: `hsl(${hue},55%,35%)` }
                    }
                  >
                    {initials(name)}
                  </div>
                  <span>{name}</span>
                </button>
              );
            })}
          </div>
        )}

        {/* Composer */}
        <div className="flex items-end gap-2 rounded-[20px] border border-border bg-input p-2 shadow-sm transition-all focus-within:border-accent focus-within:ring-1 focus-within:ring-accent/30">
          {/* File upload */}
          <input
            type="file"
            id="file-upload"
            className="hidden"
            accept=".txt,.md,.csv,.pdf"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) uploadFileMutation.mutate(file);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => document.getElementById("file-upload")?.click()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted hover:bg-elevated hover:text-foreground transition-colors"
          >
            <Paperclip className="w-5 h-5" />
          </button>

          {/* Textarea */}
          <textarea
            ref={textareaRef}
            className="min-h-[40px] max-h-[160px] w-full resize-none bg-transparent px-1 py-2 text-[15px] text-foreground outline-none placeholder:text-muted"
            placeholder={
              currentMode === "manual"
                ? "Direct the Council…"
                : currentMode === "roundtable"
                  ? "Ask the Round Table…"
                  : "Give the Auto-Pilot a mission…"
            }
            rows={1}
            value={messageInput}
            onChange={handleTextareaChange}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSendTurn();
              }
            }}
            disabled={!selectedSessionId || isStreaming}
          />

          {/* Send */}
          <button
            onClick={handleSendTurn}
            disabled={!selectedSessionId || isStreaming || !messageInput.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-white shadow-sm hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-95"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </footer>

      {/* ── Manage Panel ────────────────────────────────────────────────────── */}
      {managePanelOpen && roomQuery.data && (
        <ManageRoomPanel
          room={roomQuery.data}
          agents={roomAgents}
          allAgents={allAgentsQuery.data?.agents ?? []}
          onClose={() => setManagePanelOpen(false)}
        />
      )}
    </div>
  );
}
