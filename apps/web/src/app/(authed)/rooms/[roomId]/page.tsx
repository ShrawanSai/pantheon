"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { MoreVertical, Paperclip, Send, ThumbsUp, CornerDownLeft, ArrowLeft, X, FileText, Zap, ChevronDown, Loader2, Plus } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ManageRoomPanel } from "@/components/rooms/manage-room-panel";
import { SessionCostPanel } from "@/components/rooms/session-cost-panel";
import { SessionDrawer } from "@/components/rooms/session-drawer";
import { listAgents, type AgentRead } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import {
  getRoom,
  listRoomAgents,
  updateRoomMode,
  type RoomAgentRead,
  type RoomMode
} from "@/lib/api/rooms";
import {
  listRoomSessions,
  listSessionMessages,
  createRoomSession,
  submitTurn,
  submitTurnStream,
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

const AGENT_ERROR_RE = /\[\[agent_error\]\]\s*type=(\S+)\s*message=([\s\S]*)/;

function AgentErrorCard({ content }: { content: string }) {
  // Strip optional "AgentName: " prefix before [[agent_error]]
  const withoutPrefix = content.replace(/^[^[]+(?=\[\[agent_error\]\])/, "").trim();
  const match = withoutPrefix.match(AGENT_ERROR_RE);
  const errorType = match?.[1] ?? "Error";
  const errorMessage = match?.[2]?.trim() ?? content;
  // Extract a human-readable summary from OpenRouter 400 messages
  const innerMatch = errorMessage.match(/'message':\s*'([^']+)'/);
  const summary = innerMatch ? innerMatch[1] : errorMessage.slice(0, 200);
  return (
    <div className="flex flex-col gap-1.5 rounded-xl border border-error/30 bg-error/5 p-3">
      <div className="flex items-center gap-2">
        <span className="text-xs font-bold uppercase tracking-wide text-error">{errorType}</span>
      </div>
      <p className="text-sm text-error/80 font-mono break-all">{summary}</p>
    </div>
  );
}

// Matches legacy "Tool Call: search({...}) -> {result_count: 5}" stored messages
const TOOL_CALL_RE = /^Tool Call: (\w+)\((\{[\s\S]*?\})\) -> /;

function LegacyToolCallCard({ content }: { content: string }) {
  const match = content.match(TOOL_CALL_RE);
  if (!match) return <p className="text-xs text-muted font-mono break-all">{content}</p>;
  const [, toolName, inputRaw] = match;
  let query = "";
  try { query = JSON.parse(inputRaw)?.query ?? ""; } catch { /* ignore */ }
  const label = toolName === "search" && query ? `🔍 ${query}` : `🔧 ${toolName}`;
  return (
    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border bg-elevated border-border text-muted">
      {label}
    </span>
  );
}

const mdComponents: React.ComponentProps<typeof ReactMarkdown>["components"] = {
  a: ({ href, children }) => (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline underline-offset-2 decoration-accent/50 hover:decoration-accent break-all"
    >
      {children}
    </a>
  ),
};

const PROSE_CLASSES =
  "prose prose-sm dark:prose-invert max-w-none text-foreground " +
  "[&>p]:my-1.5 [&>ul]:my-1.5 [&>ol]:my-1.5 " +
  "[&>h1]:text-base [&>h1]:font-bold [&>h1]:mt-3 [&>h1]:mb-1 " +
  "[&>h2]:text-sm [&>h2]:font-bold [&>h2]:mt-2.5 [&>h2]:mb-1 " +
  "[&>h3]:text-sm [&>h3]:font-semibold [&>h3]:mt-2 [&>h3]:mb-0.5 " +
  "[&_table]:w-full [&_table]:border-collapse [&_table]:my-2 [&_table]:text-sm " +
  "[&_th]:border [&_th]:border-border [&_th]:bg-elevated [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold [&_th]:text-foreground " +
  "[&_td]:border [&_td]:border-border [&_td]:px-3 [&_td]:py-1.5 [&_tr:nth-child(even)_td]:bg-elevated/40 " +
  "[&_code]:bg-elevated [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs " +
  "[&_pre]:bg-elevated [&_pre]:rounded-lg [&_pre]:p-3 [&_pre]:overflow-x-auto " +
  "[&_blockquote]:border-l-2 [&_blockquote]:border-accent/40 [&_blockquote]:pl-3 [&_blockquote]:text-muted " +
  "prose-a:text-accent prose-a:no-underline";

function Markdown({ children }: { children: string }) {
  return (
    <div className={PROSE_CLASSES}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

function MessageContent({ content }: { content: string }) {
  if (content.startsWith("Tool Call: ")) {
    return <LegacyToolCallCard content={content} />;
  }
  if (content.includes("[[agent_error]]")) {
    const parts = content.split(/((?:[^\[]*\[\[agent_error\]\][^\n]*))/g).filter(Boolean);
    return (
      <div className="flex flex-col gap-2">
        {parts.map((part, i) =>
          part.includes("[[agent_error]]") ? (
            <AgentErrorCard key={i} content={part} />
          ) : part.trim() ? (
            <Markdown key={i}>{part}</Markdown>
          ) : null
        )}
      </div>
    );
  }
  return <Markdown>{content}</Markdown>;
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
  const streamDraftRef = useRef(""); // mirrors streamDraft for synchronous reads in event handlers
  const [streamAgentName, setStreamAgentName] = useState("");
  // Committed responses from agents that have already finished (shown while next agent thinks)
  const [committedAgentMessages, setCommittedAgentMessages] = useState<Array<{ agentName: string; content: string }>>([]);
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
  const sessionsQuery = useQuery({ queryKey: ["roomSessions", roomId], queryFn: () => listRoomSessions(roomId), staleTime: 3_000, refetchInterval: 5_000 });
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

  const createSessionMutation = useMutation({
    mutationFn: () => createRoomSession(roomId),
    onSuccess: async (session) => {
      await queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
      setSelectedSessionId(session.id);
    },
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
    streamDraftRef.current = "";
    setStreamDraft("");
    setStreamAgentName("Thinking...");
    setToolBubbles([]);
    setIsFinalAnswer(false);
    setCommittedAgentMessages([]);

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
          streamDraftRef.current += e.delta;
          setStreamDraft(streamDraftRef.current);
          // Mark previous agent_start bubble done once text starts flowing
          setToolBubbles(prev =>
            prev.map(b => b.kind === "agent_start" && !b.done ? { ...b, done: true } : b)
          );
        }

        if (e.type === "agent_end" && typeof e.agent_name === "string") {
          const endedAgentName = canonicalAgentDisplayName(e.agent_name);
          // Ensure the thinking bubble for this agent is resolved
          setToolBubbles(prev =>
            prev.map(b => b.kind === "agent_start" && !b.done ? { ...b, done: true } : b)
          );
          // Commit completed response — read from ref (synchronous, no double-invoke risk)
          const draft = streamDraftRef.current;
          if (draft) {
            setCommittedAgentMessages(prev => [...prev, { agentName: endedAgentName, content: draft }]);
          }
          streamDraftRef.current = "";
          setStreamDraft("");
        }

        if (e.type === "done") {
          debugLog("turn-stream", "done_event", e);
          if (currentMode === "orchestrator" && addressedAgentKeys.size === 0) setIsFinalAnswer(true);
        }
      });
      await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
      // Refresh sessions list immediately and again after a delay so auto-generated name appears
      // (background naming task takes 2-5s to complete the LLM call)
      queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] }), 5000);
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
      streamDraftRef.current = "";
      setStreamDraft("");
      setStreamAgentName("");
      setToolBubbles([]);
      setIsFinalAnswer(false);
      setCommittedAgentMessages([]);
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

  const messages = (messagesQuery.data?.messages ?? []).filter(
    m => m.role === "user" || (
      m.role === "assistant" &&
      !m.content.startsWith("Tool Call: ") &&
      !m.content.startsWith("🔍 ")
    )
  );
  const sessions = sessionsQuery.data ?? [];
  const files = filesQuery.data ?? [];

  // Allow creating a new session only if the current session already has at least one user message
  const canCreateSession = sessions.length === 0 || messages.some(m => m.role === "user");

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
          <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
            <div className="text-5xl">🏛️</div>
            <div>
              <p className="font-bold text-foreground text-lg">Welcome to {roomQuery.data?.name ?? "your room"}</p>
              <p className="text-sm text-muted mt-1">Start a session to begin talking with your agents.</p>
            </div>
            <button
              onClick={() => createSessionMutation.mutate()}
              disabled={createSessionMutation.isPending}
              className="flex items-center gap-2 px-5 py-2.5 rounded-full bg-accent text-white text-sm font-semibold shadow-sm hover:bg-accent-hover disabled:opacity-50 transition-all active:scale-95"
            >
              {createSessionMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Plus className="w-4 h-4" />
              )}
              {createSessionMutation.isPending ? "Creating…" : "Start Session"}
            </button>
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
                  <MessageContent content={message.content} />

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

        {/* ── Committed agent responses (already done, shown while next agent thinks) ── */}
        {isStreaming && committedAgentMessages.map((msg, idx) => (
          <div key={`committed-${idx}`} className="flex gap-3">
            <div
              className="h-10 w-10 shrink-0 rounded-full flex items-center justify-center border-2 border-white dark:border-surface text-white text-xs font-bold"
              style={{ background: `hsl(${agentHue(msg.agentName)},55%,50%)` }}
            >
              {initials(msg.agentName)}
            </div>
            <div className="flex flex-col items-start max-w-[88%] gap-1.5">
              <span className="text-sm font-bold text-foreground">{msg.agentName}</span>
              <div className="rounded-2xl rounded-tl-sm p-4 border shadow-sm w-full bg-white dark:bg-surface border-border">
                <Markdown>{msg.content}</Markdown>
              </div>
            </div>
          </div>
        ))}

        {/* ── Streaming area ─────────────────────────────────────────── */}
        {isStreaming && (
          <div className="flex gap-3">
            {/* Avatar */}
            <div
              className="h-10 w-10 shrink-0 rounded-full flex items-center justify-center border-2 border-white dark:border-surface text-white text-xs font-bold"
              style={{ background: streamAgentName && streamAgentName !== "Thinking..." ? `hsl(${agentHue(streamAgentName)},55%,50%)` : "hsl(var(--accent))" }}
            >
              {streamAgentName && streamAgentName !== "Thinking..." ? initials(streamAgentName) : "AI"}
            </div>

            <div className="flex flex-col items-start max-w-[88%] gap-1.5">
              {/* Agent name */}
              {streamAgentName && (
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-foreground">{streamAgentName}</span>
                  {currentMode === "orchestrator" && isFinalAnswer && (
                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-mode-auto/10 text-mode-auto uppercase tracking-wide">
                      Final Answer
                    </span>
                  )}
                </div>
              )}

              {/* Content bubble: streaming text or thinking dots */}
              <div className={`rounded-2xl rounded-tl-sm p-4 border shadow-sm w-full ${isFinalAnswer
                ? "bg-gradient-to-br from-mode-auto/5 to-background border-mode-auto/30"
                : "bg-white dark:bg-surface border-border"
              }`}>
                {streamDraft ? (
                  <Markdown>{streamDraft}</Markdown>
                ) : (
                  <div className="flex items-center gap-2 text-muted text-sm">
                    <div className="flex gap-1">
                      <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-2 h-2 rounded-full bg-accent animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                    <span className="text-xs font-mono">
                      {toolBubbles.length > 0 ? "Processing…" : currentMode === "orchestrator" ? "Synthesizer drafting…" : "Responding…"}
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

      {/* ── Input Area ──────────────────────────────────────────────────── */}
      <footer className="flex-none bg-white dark:bg-surface border-t border-border px-4 pt-3 pb-4">
        {/* Live agent status strip — visible above input while streaming */}
        {isStreaming && toolBubbles.length > 0 && (
          <div className="mb-3 flex flex-col gap-1">
            {toolBubbles.map(bubble => (
              <div key={bubble.id} className="flex flex-col gap-1">
                <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium border self-start transition-all ${bubble.done
                  ? "bg-elevated border-border text-muted opacity-60"
                  : "bg-accent/5 border-accent/30 text-accent animate-pulse"
                }`}>
                  {bubble.label}
                </span>
                {bubble.done && bubble.sources && bubble.sources.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 ml-1">
                    {bubble.sources.slice(0, 5).map((src, i) => (
                      <a
                        key={i}
                        href={src.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={src.snippet}
                        className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-elevated border border-border text-[11px] text-muted hover:text-accent hover:border-accent transition-colors max-w-[200px]"
                      >
                        <span className="truncate">{src.title || src.url}</span>
                        <span className="shrink-0 opacity-50">↗</span>
                      </a>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

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
            {isStreaming
              ? <Loader2 className="w-4 h-4 animate-spin" />
              : <Send className="w-4 h-4" />
            }
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
          canCreate={canCreateSession}
          onSelect={setSelectedSessionId}
          onClose={() => setSessionDrawerOpen(false)}
        />
      )}
    </div>
  );
}
