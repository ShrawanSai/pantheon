"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { MoreVertical, Paperclip, Send, ThumbsUp, CornerDownLeft, ArrowLeft, X, FileText, Zap, ChevronDown } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ManageRoomPanel } from "@/components/rooms/manage-room-panel";
import { SessionCostPanel } from "@/components/rooms/session-cost-panel";
import { SessionDrawer } from "@/components/rooms/session-drawer";
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
  listRoomSessions,
  listSessionMessages,
  submitTurn,
  submitTurnStream,
  type SessionRead,
  type StreamEvent
} from "@/lib/api/sessions";
import { debugError, debugLog, debugWarn } from "@/lib/debug";
import {
  listRoomFiles,
  uploadFile,
} from "@/lib/api/files";

type RoomWorkspacePageProps = {
  params: {
    roomId: string;
  };
};

const MODE_OPTIONS: Array<{ value: RoomMode; label: string; emoji: string }> = [
  { value: "manual", label: "Manual", emoji: "✋" },
  { value: "roundtable", label: "Round Table", emoji: "👥" },
  { value: "orchestrator", label: "Auto-Pilot", emoji: "🤖" },
];

// Tool call event displayed as a status bubble in the feed
type ToolSource = { title: string; url: string; snippet: string };
type ToolCallBubble = {
  id: string;
  kind: "tool_call" | "tool_result" | "agent_start" | "round";
  label: string;
  done: boolean;
  sources?: ToolSource[];
};

function parseToolSources(result: string): ToolSource[] {
  return result.split("\n")
    .filter(line => line.startsWith("- "))
    .map(line => {
      const parts = line.substring(2).split(" | ");
      return { title: parts[0]?.trim() ?? "", url: parts[1]?.trim() ?? "", snippet: parts[2]?.trim() ?? "" };
    })
    .filter(s => s.url.startsWith("http"));
}

function initials(name: string): string {
  return name.split(/\s+/).map(w => w[0] ?? "").join("").toUpperCase().slice(0, 2);
}

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
  if (d.toDateString() === yesterday.toDateString()) return "Yesterday";
  return d.toLocaleDateString([], { month: "short", day: "numeric" });
}

function fileIcon(filename: string): string {
  const ext = filename.split(".").pop()?.toLowerCase() ?? "";
  if (["pdf"].includes(ext)) return "📄";
  if (["csv", "xlsx", "xls"].includes(ext)) return "📊";
  if (["md", "txt"].includes(ext)) return "📝";
  return "📎";
}

function canonicalAgentDisplayName(name: string | null | undefined): string {
  const raw = (name ?? "").trim();
  if (!raw) return "Agent";
  const normalized = raw.toLowerCase();
  if (/\b(manager|conductor|synthesizer|director)\b/.test(normalized)) {
    return "Director";
  }
  return raw;
}

function getRoomAgentKey(assignment: RoomAgentRead, agents: Map<string, AgentRead>): string {
  const direct = assignment.agent?.agent_key?.trim();
  if (direct) return direct;
  const fromMap = agents.get(assignment.agent_id)?.agent_key?.trim();
  if (fromMap) return fromMap;
  return "";
}

function normalizeMentionText(input: string): string {
  return input
    .replace(/[‑–—−﹘﹣－]/g, "-")
    .replace(/\u200B/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export default function RoomWorkspacePage({ params }: RoomWorkspacePageProps) {
  const router = useRouter();
  const roomId = params.roomId;
  const queryClient = useQueryClient();

  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [messageInput, setMessageInput] = useState("");
  const [composerError, setComposerError] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamDraft, setStreamDraft] = useState("");
  const [streamAgentName, setStreamAgentName] = useState("");
  const [toolBubbles, setToolBubbles] = useState<ToolCallBubble[]>([]);
  const [managePanelOpen, setManagePanelOpen] = useState(false);
  const [costPanelOpen, setCostPanelOpen] = useState(false);
  const [sessionDrawerOpen, setSessionDrawerOpen] = useState(false);
  const [addressedAgentKeys, setAddressedAgentKeys] = useState<Set<string>>(new Set());
  const [approvedMessages, setApprovedMessages] = useState<Set<string>>(new Set());
  const [isFinalAnswer, setIsFinalAnswer] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // ── Queries ────────────────────────────────────────────────────────────
  const roomQuery = useQuery({ queryKey: ["room", roomId], queryFn: () => getRoom(roomId) });
  const roomAgentsQuery = useQuery({ queryKey: ["roomAgents", roomId], queryFn: () => listRoomAgents(roomId) });
  const allAgentsQuery = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const sessionsQuery = useQuery({ queryKey: ["roomSessions", roomId], queryFn: () => listRoomSessions(roomId), staleTime: 10_000, refetchInterval: 15_000 });
  const messagesQuery = useQuery({
    queryKey: ["sessionMessages", selectedSessionId],
    queryFn: () => listSessionMessages(selectedSessionId),
    enabled: Boolean(selectedSessionId),
    refetchInterval: isStreaming ? false : 4000,
  });
  const filesQuery = useQuery({ queryKey: ["roomFiles", roomId], queryFn: () => listRoomFiles(roomId) });

  const currentMode = roomQuery.data?.current_mode ?? "manual";

  useEffect(() => {
    const sessions = sessionsQuery.data || [];
    debugLog("room-workspace", "sessions_query_update", {
      roomId,
      count: sessions.length,
      sessions: sessions.map((session) => ({
        id: session.id,
        name: session.name,
        createdAt: session.created_at,
      })),
    });
    if (!selectedSessionId && sessions.length > 0) setSelectedSessionId(sessions[0].id);
    else if (selectedSessionId && sessions.every(s => s.id !== selectedSessionId)) {
      setSelectedSessionId(sessions[0]?.id || "");
    }
  }, [selectedSessionId, sessionsQuery.data]);

  useEffect(() => {
    debugLog("room-workspace", "mode_changed", {
      roomId,
      mode: currentMode,
    });
  }, [currentMode, roomId]);

  useEffect(() => {
    if (!selectedSessionId) {
      return;
    }
    debugLog("room-workspace", "selected_session_changed", {
      roomId,
      selectedSessionId,
    });
  }, [roomId, selectedSessionId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messagesQuery.data, streamDraft, isStreaming, toolBubbles]);

  const agentMap = useMemo(() => {
    const agents = allAgentsQuery.data?.agents ?? [];
    const map = new Map<string, AgentRead>();
    agents.forEach(a => map.set(a.id, a));
    return map;
  }, [allAgentsQuery.data]);

  const roomAgents = roomAgentsQuery.data ?? [];

  // ── Mutations ──────────────────────────────────────────────────────────
  const setModeMutation = useMutation({
    mutationFn: (mode: RoomMode) => updateRoomMode(roomId, mode),
    onMutate: (mode: RoomMode) => {
      debugLog("room-mode", "attempt_update", { roomId, from: currentMode, to: mode });
    },
    onSuccess: (updated) => {
      debugLog("room-mode", "update_success", { roomId, newMode: updated.current_mode });
      queryClient.invalidateQueries({ queryKey: ["room", roomId] });
    },
    onError: (error) => {
      debugError("room-mode", "update_failed", error);
    },
  });

  const uploadFileMutation = useMutation({
    mutationFn: (file: File) => uploadFile(roomId, file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["roomFiles", roomId] }),
  });

  const removeFileMutation = useMutation({
    mutationFn: async (_fileId: string) => { /* file deletion not in API yet — noop */ },
  });

  // ── Send turn ──────────────────────────────────────────────────────────
  async function handleSendTurn() {
    setComposerError("");
    const trimmed = messageInput.trim();
    debugLog("turn-send", "start", {
      roomId,
      sessionId: selectedSessionId,
      mode: currentMode,
      addressedAgentKeys: [...addressedAgentKeys],
      messagePreview: trimmed.slice(0, 140),
    });
    if (!selectedSessionId) { setComposerError("Create a session first."); return; }
    if (!trimmed) return;
    if (currentMode === "manual" && addressedAgentKeys.size === 0 && roomAgents.length > 0) {
      debugWarn("turn-send", "blocked_manual_no_tag", {
        roomId,
        sessionId: selectedSessionId,
        roomAgents: roomAgents.map((ra) => ra.agent.agent_key),
      });
      setComposerError("Tag at least one agent to reply (e.g. click an agent below), or switch to Round Table or Auto-Pilot mode.");
      return;
    }

    const selectedAgentKeys = [...addressedAgentKeys].filter(Boolean);

    let finalMessage = normalizeMentionText(trimmed);
    if (selectedAgentKeys.length > 0) {
      const mentions = selectedAgentKeys.map(k => `@${k}`).join(" ");
      finalMessage = normalizeMentionText(`${mentions} ${trimmed}`);
    }

    setMessageInput("");
    if (textareaRef.current) textareaRef.current.style.height = "auto";

    setIsStreaming(true);
    setStreamDraft("");
    setStreamAgentName("Thinking...");
    setToolBubbles([]);
    setIsFinalAnswer(false);

    try {
      debugLog("turn-send", "stream_submit", {
        roomId,
        sessionId: selectedSessionId,
        finalMessagePreview: finalMessage.slice(0, 180),
        selectedAgentKeys,
      });
      await submitTurnStream(
        selectedSessionId,
        {
          message: finalMessage,
        },
        (event: StreamEvent) => {
        const e = event as Record<string, unknown>;
        if (typeof e.type === "string" && e.type !== "chunk") {
          debugLog("turn-stream", "event", e);
        }

        if (e.type === "agent_start" && typeof e.agent_name === "string") {
          const displayName = canonicalAgentDisplayName(e.agent_name);
          setStreamAgentName(displayName);
          setToolBubbles(prev => [...prev, {
            id: `as-${Date.now()}-${Math.random()}`,
            kind: "agent_start",
            label: `${displayName} is thinking…`,
            done: false,
          }]);
        }

        if (e.type === "round_start" && typeof e.round === "number") {
          setToolBubbles(prev => [...prev, {
            id: `round-${e.round}-${Date.now()}`,
            kind: "round",
            label: `Round ${e.round}`,
            done: false,
          }]);
        }

        if (e.type === "tool_start" && typeof e.tool === "string") {
          const toolLabel = e.tool === "search"
            ? `🔍 Searching the web…`
            : e.tool === "file_read"
              ? `📄 Reading file…`
              : `🔧 Calling ${e.tool}…`;
          setToolBubbles(prev => [...prev, {
            id: `tc-${Date.now()}-${Math.random()}`,
            kind: "tool_call",
            label: toolLabel,
            done: false,
          }]);
        }

        if (e.type === "tool_end" && typeof e.tool === "string") {
          const sources = typeof e.result === "string" ? parseToolSources(e.result) : [];
          setToolBubbles(prev =>
            prev.map(b =>
              b.kind === "tool_call" && !b.done
                ? { ...b, done: true, label: b.label.replace("…", " ✓"), sources: sources.length > 0 ? sources : undefined }
                : b
            )
          );
        }

        if (e.type === "chunk" && typeof e.delta === "string") {
          setStreamDraft(prev => prev + e.delta);
          // Mark previous agent_start bubble done once text starts flowing
          setToolBubbles(prev =>
            prev.map(b => b.kind === "agent_start" && !b.done ? { ...b, done: true } : b)
          );
        }

        if (e.type === "done") {
          debugLog("turn-stream", "done_event", e);
          if (currentMode === "orchestrator" && addressedAgentKeys.size === 0) setIsFinalAnswer(true);
        }
      });
      await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
      // Refresh sessions list after first turn so auto-generated name appears
      queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
      debugLog("turn-send", "stream_success", { roomId, sessionId: selectedSessionId });
    } catch (err) {
      const detail = err instanceof ApiError ? err.detail : "Stream failed.";
      debugError("turn-send", "stream_failed_fallback_to_non_stream", { error: err, detail });
      try {
        await submitTurn(selectedSessionId, {
          message: finalMessage,
        });
        await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
        queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
        debugLog("turn-send", "non_stream_fallback_success", { roomId, sessionId: selectedSessionId });
      } catch {
        debugError("turn-send", "non_stream_fallback_failed", { roomId, sessionId: selectedSessionId, detail });
        setComposerError(detail);
        setMessageInput(finalMessage);
      }
    } finally {
      debugLog("turn-send", "done", { roomId, sessionId: selectedSessionId });
      setIsStreaming(false);
      setStreamDraft("");
      setStreamAgentName("");
      setToolBubbles([]);
      setIsFinalAnswer(false);
    }
  }

  function handleTextareaChange(e: React.ChangeEvent<HTMLTextAreaElement>) {
    setMessageInput(e.target.value);
    e.target.style.height = "auto";
    e.target.style.height = `${Math.min(e.target.scrollHeight, 160)}px`;
  }

  function toggleAddressed(agentKey: string) {
    setAddressedAgentKeys(prev => {
      const next = new Set(prev);
      if (next.has(agentKey)) next.delete(agentKey); else next.add(agentKey);
      return next;
    });
  }

  const messages = messagesQuery.data?.messages ?? [];
  const sessions = sessionsQuery.data ?? [];
  const files = filesQuery.data ?? [];

  useEffect(() => {
    const availableKeys = new Set(
      roomAgents
        .map((assignment) => getRoomAgentKey(assignment, agentMap))
        .filter(Boolean)
    );
    setAddressedAgentKeys((prev) => {
      const next = new Set([...prev].filter((key) => availableKeys.has(key)));
      if (next.size === prev.size) {
        return prev;
      }
      debugLog("turn-send", "pruned_stale_addressed_keys", {
        roomId,
        kept: [...next],
        dropped: [...prev].filter((key) => !availableKeys.has(key)),
      });
      return next;
    });
  }, [agentMap, roomAgents, roomId]);

  return (
    <div className="flex h-full flex-col bg-background-light dark:bg-background overflow-hidden">
      {/* ── Header ─────────────────────────────────────────────────────── */}
      <header className="flex-none bg-white dark:bg-surface border-b border-border px-4 pt-4 pb-3 z-10">
        {/* Row 1: Back + Room name + Actions */}
        <div className="flex items-center justify-between pl-14 lg:pl-0 mb-2">
          <button
            onClick={() => router.push("/rooms")}
            className="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-elevated hover:text-foreground transition-colors shrink-0"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>

          {/* Room name — centered */}
          <h1 className="flex-1 text-center text-base font-bold text-foreground px-2 truncate">
            {roomQuery.data?.name ?? "Council Room"}
          </h1>

          {/* Right actions */}
          <div className="flex items-center gap-1 shrink-0">
            {/* Agent avatars */}
            {roomAgents.length > 0 && (
              <div className="flex -space-x-1.5">
                {roomAgents.slice(0, 3).map(ra => {
                  const agent = agentMap.get(ra.agent_id);
                  const name = agent?.name ?? ra.agent_id.slice(0, 8);
                  const hue = agentHue(name);
                  return (
                    <div
                      key={ra.agent_id}
                      title={name}
                      className="w-7 h-7 rounded-full border-2 border-white dark:border-surface flex items-center justify-center text-[10px] font-bold text-white shrink-0"
                      style={{ background: `hsl(${hue},55%,50%)` }}
                    >
                      {initials(name)}
                    </div>
                  );
                })}
                {roomAgents.length > 3 && (
                  <div className="w-7 h-7 rounded-full border-2 border-white dark:border-surface bg-elevated flex items-center justify-center text-[10px] font-bold text-muted shrink-0">
                    +{roomAgents.length - 3}
                  </div>
                )}
              </div>
            )}
            {selectedSessionId && (
              <button
                onClick={() => setCostPanelOpen(true)}
                title="Session cost"
                className="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-elevated hover:text-foreground transition-colors"
              >
                <Zap className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={() => setManagePanelOpen(true)}
              className="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-elevated hover:text-foreground transition-colors"
            >
              <MoreVertical className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Row 2: Session indicator chip */}
        {(() => {
          const sorted = [...sessions].sort(
            (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
          );
          const activeIdx = sorted.findIndex(s => s.id === selectedSessionId);
          const sessionNum = activeIdx >= 0 ? activeIdx + 1 : null;
          const activeSession = sorted[activeIdx];
          const sessionLabel = activeSession?.name
            ? activeSession.name
            : sessionNum
              ? `Session ${sessionNum}`
              : sessions.length === 0
                ? "No sessions"
                : "Select session";
          const timeLabel = activeSession
            ? (() => {
                const d = new Date(activeSession.created_at);
                if (isNaN(d.getTime())) return "";
                const today = new Date();
                const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
                if (d.toDateString() === today.toDateString()) return `Today ${time}`;
                return d.toLocaleDateString([], { month: "short", day: "numeric" });
              })()
            : null;
          return (
            <div className="flex justify-center mb-2">
              <button
                onClick={() => setSessionDrawerOpen(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-elevated border border-border text-sm font-medium text-foreground hover:bg-elevated hover:border-accent/50 transition-all active:scale-95"
              >
                <span className="font-semibold">{sessionLabel}</span>
                {timeLabel && (
                  <>
                    <span className="text-muted text-xs">·</span>
                    <span className="text-muted text-xs">{timeLabel}</span>
                  </>
                )}
                <ChevronDown className="h-3.5 w-3.5 text-muted" />
              </button>
            </div>
          );
        })()}

        {/* Row 3: Mode pills */}
        <div className="flex gap-2 overflow-x-auto pb-0.5 hide-scrollbar">
          {MODE_OPTIONS.map(opt => {
            const active = currentMode === opt.value;
            return (
              <button
                key={opt.value}
                onClick={() => setModeMutation.mutate(opt.value)}
                disabled={setModeMutation.isPending}
                className={`flex h-8 shrink-0 items-center gap-1.5 rounded-full px-3.5 text-xs font-medium transition-all active:scale-95 ${active
                  ? "bg-accent text-white shadow-sm"
                  : "bg-elevated text-muted hover:text-foreground border border-border"
                  }`}
              >
                <span className="text-sm">{opt.emoji}</span>
                {opt.label}
              </button>
            );
          })}
        </div>
      </header>

      {/* ── Message Feed ───────────────────────────────────────────────── */}
      <main className="flex-1 overflow-y-auto p-4 space-y-5">
        {messages.length > 0 && (
          <div className="flex justify-center">
            <span className="px-3 py-1 rounded-full bg-elevated text-xs text-muted border border-border">
              {formatDateGroup(messages[0].created_at)}
            </span>
          </div>
        )}

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
                  : "The Director will orchestrate and synthesize responses for you."}
            </p>
          </div>
        )}

        {messages.map(message => {
          const isUser = message.role === "user";

          if (isUser) {
            return (
              <div key={message.id} className="flex items-end gap-3 justify-end group">
                <div className="flex flex-col items-end gap-1 max-w-[85%]">
                  <div className="rounded-2xl rounded-tr-sm px-5 py-3.5 bg-accent text-white shadow-sm">
                    <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
                      {message.content.split(/(@\w[\w\s]*)/).map((part, i) =>
                        part.startsWith("@") ? (
                          <strong key={i} className="font-bold text-white/90 bg-white/10 rounded px-1">{part}</strong>
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
                <div className="h-8 w-8 shrink-0 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xs font-bold border-2 border-white dark:border-surface">
                  U
                </div>
              </div>
            );
          }

          // Agent message
          const agentName = canonicalAgentDisplayName(message.agent_name);
          const hue = agentHue(agentName);
          const isApproved = approvedMessages.has(message.id);
          const isSynthesized = ["synthesizer", "orchestrator", "conductor", "director"].some(k => message.agent_name?.toLowerCase().includes(k));

          return (
            <div key={message.id} className="flex gap-3 group">
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
                <div className="w-px flex-1 bg-border rounded-full" style={{ minHeight: 12 }} />
              </div>

              <div className="flex flex-col items-start max-w-[88%] min-w-0 pb-2">
                <div className="flex items-center gap-2 mb-1.5">
                  <span className="text-sm font-bold text-foreground">{agentName}</span>
                  {isSynthesized && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-mode-auto/10 text-mode-auto uppercase tracking-wide">
                      Final Answer
                    </span>
                  )}
                </div>

                {/* Auto-pilot synthesized answer gets a special card */}
                <div className={`rounded-2xl rounded-tl-sm p-4 border shadow-sm w-full ${isSynthesized
                  ? "bg-gradient-to-br from-mode-auto/5 to-background border-mode-auto/30"
                  : "bg-white dark:bg-surface border-border"
                  }`}>
                  <div className="prose prose-sm dark:prose-invert max-w-none text-foreground [&>p]:my-1.5 [&>ul]:my-1.5 [&>ol]:my-1.5 [&>h1]:text-base [&>h1]:font-bold [&>h1]:mt-3 [&>h1]:mb-1 [&>h2]:text-sm [&>h2]:font-bold [&>h2]:mt-2.5 [&>h2]:mb-1 [&>h3]:text-sm [&>h3]:font-semibold [&>h3]:mt-2 [&>h3]:mb-0.5 [&_table]:w-full [&_table]:border-collapse [&_table]:my-2 [&_table]:text-sm [&_th]:border [&_th]:border-border [&_th]:bg-elevated [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_th]:text-foreground [&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-1.5 [&_tr:nth-child(even)_td]:bg-elevated/40 [&_code]:bg-elevated [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_pre]:bg-elevated [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:overflow-x-auto [&_blockquote]:border-l-2 [&_blockquote]:border-accent/40 [&_blockquote]:pl-3 [&_blockquote]:text-muted">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                  </div>

                  <div className="mt-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button
                      onClick={() =>
                        setApprovedMessages(prev => {
                          const next = new Set(prev);
                          if (next.has(message.id)) next.delete(message.id); else next.add(message.id);
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
                        const matched = roomAgents.find((assignment) => {
                          const candidateName = canonicalAgentDisplayName(
                            assignment.agent?.name ?? agentMap.get(assignment.agent_id)?.name
                          );
                          return candidateName.toLowerCase() === agentName.toLowerCase();
                        });
                        if (matched) {
                          const key = getRoomAgentKey(matched, agentMap);
                          if (key) {
                            setAddressedAgentKeys((prev) => new Set(prev).add(key));
                            setMessageInput(`@${key} `);
                          } else {
                            setMessageInput(`@${agentName} `);
                          }
                        } else {
                          setMessageInput(`@${agentName} `);
                        }
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

        {/* ── Streaming area ─────────────────────────────────────────── */}
        {isStreaming && (
          <div className="flex flex-col gap-2">
            {/* Tool call / event bubbles */}
            {toolBubbles.map(bubble => (
              <div key={bubble.id} className="flex flex-col items-center gap-1.5">
                <span className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all ${bubble.done
                  ? "bg-elevated border-border text-muted opacity-70"
                  : "bg-accent/5 border-accent/30 text-accent animate-pulse"
                  }`}>
                  {bubble.label}
                </span>
                {/* Clickable source links from web search */}
                {bubble.done && bubble.sources && bubble.sources.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 justify-center max-w-lg">
                    {bubble.sources.slice(0, 5).map((src, i) => (
                      <a
                        key={i}
                        href={src.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={src.snippet}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-elevated border border-border text-[11px] text-muted hover:text-accent hover:border-accent transition-colors max-w-[180px]"
                      >
                        <span className="truncate">{src.title || src.url}</span>
                        <span className="shrink-0 opacity-50">↗</span>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {/* Streaming text bubble */}
            {(streamDraft || (!streamDraft && toolBubbles.length === 0)) && (
              <div className="flex gap-3">
                <div
                  className="h-10 w-10 shrink-0 rounded-full flex items-center justify-center border-2 border-white dark:border-surface text-white text-xs font-bold"
                  style={{ background: streamAgentName && streamAgentName !== "Thinking..." ? `hsl(${agentHue(streamAgentName)},55%,50%)` : "hsl(var(--accent))" }}
                >
                  {streamAgentName && streamAgentName !== "Thinking..." ? initials(streamAgentName) : "AI"}
                </div>
                <div className="flex flex-col items-start max-w-[88%]">
                  {streamAgentName && (
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-sm font-bold text-foreground">{streamAgentName}</span>
                      {currentMode === "orchestrator" && isFinalAnswer && (
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-mode-auto/10 text-mode-auto uppercase tracking-wide">
                          Final Answer
                        </span>
                      )}
                    </div>
                  )}
                  <div className={`rounded-2xl rounded-tl-sm p-4 border shadow-sm w-full ${isFinalAnswer
                    ? "bg-gradient-to-br from-mode-auto/5 to-background border-mode-auto/30"
                    : "bg-white dark:bg-surface border-border"
                    }`}>
                    {streamDraft ? (
                      <div className="prose prose-sm dark:prose-invert max-w-none text-foreground [&>p]:my-1.5 [&_table]:w-full [&_table]:border-collapse [&_table]:my-2 [&_table]:text-sm [&_th]:border [&_th]:border-border [&_th]:bg-elevated [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-1.5 [&_tr:nth-child(even)_td]:bg-elevated/40 [&_code]:bg-elevated [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamDraft}</ReactMarkdown>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-muted text-sm">
                        <div className="flex gap-1">
                          <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "0ms" }} />
                          <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "150ms" }} />
                          <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "300ms" }} />
                        </div>
                        <span className="text-xs font-mono">
                          {currentMode === "orchestrator" ? "Synthesizer drafting…" : "Responding…"}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {composerError && (
          <div className="text-center text-sm text-error py-2">{composerError}</div>
        )}

        <div ref={bottomRef} />
      </main>

      {/* ── Input Area ──────────────────────────────────────────────────── */}
      <footer className="flex-none bg-white dark:bg-surface border-t border-border px-4 pt-3 pb-4">
        {/* Attached files */}
        {files.length > 0 && (
          <div className="mb-3 flex flex-wrap gap-2">
            {files.map(f => (
              <div
                key={f.id}
                className="flex items-center gap-1.5 bg-elevated border border-border rounded-lg px-3 py-1.5 text-xs text-foreground group"
              >
                <span>{fileIcon(f.filename)}</span>
                <span className="font-medium max-w-[120px] truncate">{f.filename}</span>
                <button
                  onClick={() => removeFileMutation.mutate(f.id)}
                  className="text-muted hover:text-error transition-colors opacity-0 group-hover:opacity-100 ml-1"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        {/* File upload progress */}
        {uploadFileMutation.isPending && (
          <div className="mb-2 flex items-center gap-2 text-xs text-muted animate-pulse">
            <FileText className="w-3.5 h-3.5" />
            <span>Uploading file…</span>
          </div>
        )}

        {/* Agent addressing chips - available in all modes */}
        {roomAgents.length > 0 && (
          <div className="flex items-center gap-2 mb-3 overflow-x-auto pb-1 hide-scrollbar">
            <span className="text-[11px] font-semibold text-muted uppercase tracking-widest shrink-0">
              {currentMode === "manual" ? "To:" : "Direct:"}
            </span>
            {roomAgents.map(ra => {
              const agent = agentMap.get(ra.agent_id);
              const name = agent?.name ?? ra.agent_id.slice(0, 8);
              const agentKey = getRoomAgentKey(ra, agentMap);
              const hue = agentHue(name);
              const active = addressedAgentKeys.has(agentKey);
              return (
                <button
                  key={ra.agent_id}
                  onClick={() => toggleAddressed(agentKey)}
                  disabled={!agentKey}
                  className={`flex items-center gap-1.5 pl-1 pr-3 py-1 rounded-full text-sm font-medium shrink-0 transition-all active:scale-95 border ${active
                    ? "text-white shadow-sm border-transparent"
                    : "text-muted border-border bg-elevated hover:bg-elevated"
                    }`}
                  style={active ? { background: `hsl(${hue},55%,50%)`, borderColor: `hsl(${hue},55%,50%)` } : {}}
                >
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-bold"
                    style={active
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
          <input
            type="file"
            id="file-upload"
            className="hidden"
            accept=".txt,.md,.csv,.pdf"
            onChange={e => {
              const file = e.target.files?.[0];
              if (file) uploadFileMutation.mutate(file);
              e.target.value = "";
            }}
          />
          <button
            onClick={() => document.getElementById("file-upload")?.click()}
            title="Attach file"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-muted hover:bg-elevated hover:text-foreground transition-colors"
          >
            <Paperclip className="w-5 h-5" />
          </button>

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
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSendTurn(); }
            }}
            disabled={!selectedSessionId || isStreaming}
          />

          <button
            onClick={handleSendTurn}
            disabled={!selectedSessionId || isStreaming || !messageInput.trim()}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-accent text-white shadow-sm hover:bg-accent-hover disabled:opacity-40 disabled:cursor-not-allowed transition-all active:scale-95"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </footer>

      {/* ── Manage Panel ────────────────────────────────────────────────── */}
      {managePanelOpen && roomQuery.data && (
        <ManageRoomPanel
          room={roomQuery.data}
          agents={roomAgents}
          allAgents={allAgentsQuery.data?.agents ?? []}
          onClose={() => setManagePanelOpen(false)}
        />
      )}

      {costPanelOpen && selectedSessionId && (
        <SessionCostPanel
          sessionId={selectedSessionId}
          onClose={() => setCostPanelOpen(false)}
        />
      )}

      {sessionDrawerOpen && (
        <SessionDrawer
          roomId={roomId}
          sessions={sessions}
          selectedSessionId={selectedSessionId}
          onSelect={setSelectedSessionId}
          onClose={() => setSessionDrawerOpen(false)}
        />
      )}
    </div>
  );
}
