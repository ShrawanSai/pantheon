"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
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
  type UploadedFileRead
} from "@/lib/api/files";

type RoomWorkspacePageProps = {
  params: {
    roomId: string;
  };
};

const MODE_OPTIONS: Array<{ value: RoomMode; label: string; description: string }> = [
  {
    value: "manual",
    label: "Solo Chat",
    description: "One primary agent responds each turn."
  },
  {
    value: "roundtable",
    label: "Team Discussion",
    description: "Agents respond in sequence with multiple viewpoints."
  },
  {
    value: "orchestrator",
    label: "Auto Best Answer",
    description: "A manager coordinates specialists and synthesizes one answer."
  }
];

function formatDateTime(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleString();
}

export default function RoomWorkspacePage({ params }: RoomWorkspacePageProps) {
  const roomId = params.roomId;
  const queryClient = useQueryClient();

  const [modeDraft, setModeDraft] = useState<RoomMode>("manual");
  const [assignAgentId, setAssignAgentId] = useState("");
  const [selectedSessionId, setSelectedSessionId] = useState("");
  const [messageInput, setMessageInput] = useState("");
  const [composerError, setComposerError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [streamingEnabled, setStreamingEnabled] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamDraft, setStreamDraft] = useState("");
  const [streamTrace, setStreamTrace] = useState<string[]>([]);

  const roomQuery = useQuery({
    queryKey: ["room", roomId],
    queryFn: () => getRoom(roomId)
  });

  const roomAgentsQuery = useQuery({
    queryKey: ["roomAgents", roomId],
    queryFn: () => listRoomAgents(roomId)
  });

  const allAgentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: listAgents
  });

  const sessionsQuery = useQuery({
    queryKey: ["roomSessions", roomId],
    queryFn: () => listRoomSessions(roomId)
  });

  const messagesQuery = useQuery({
    queryKey: ["sessionMessages", selectedSessionId],
    queryFn: () => listSessionMessages(selectedSessionId),
    enabled: Boolean(selectedSessionId)
  });

  const turnsQuery = useQuery({
    queryKey: ["sessionTurns", selectedSessionId],
    queryFn: () => listSessionTurns(selectedSessionId),
    enabled: Boolean(selectedSessionId)
  });

  const filesQuery = useQuery({
    queryKey: ["roomFiles", roomId],
    queryFn: () => listRoomFiles(roomId)
  });

  useEffect(() => {
    if (roomQuery.data) {
      setModeDraft(roomQuery.data.current_mode);
    }
  }, [roomQuery.data]);

  useEffect(() => {
    const sessions = sessionsQuery.data || [];
    if (!selectedSessionId && sessions.length > 0) {
      setSelectedSessionId(sessions[0].id);
    } else if (selectedSessionId && sessions.every((session) => session.id !== selectedSessionId)) {
      setSelectedSessionId(sessions[0]?.id || "");
    }
  }, [selectedSessionId, sessionsQuery.data]);

  const assignedAgentIds = useMemo(
    () => new Set((roomAgentsQuery.data || []).map((assignment) => assignment.agent_id)),
    [roomAgentsQuery.data]
  );

  const assignableAgents = useMemo(() => {
    const all = allAgentsQuery.data?.agents || [];
    return all.filter((agent) => !assignedAgentIds.has(agent.id));
  }, [allAgentsQuery.data, assignedAgentIds]);

  const saveModeMutation = useMutation({
    mutationFn: async () => updateRoomMode(roomId, modeDraft),
    onSuccess: async () => {
      setActionMessage("Room mode updated.");
      await queryClient.invalidateQueries({ queryKey: ["room", roomId] });
      await queryClient.invalidateQueries({ queryKey: ["rooms"] });
    },
    onError: (error) => {
      setActionMessage(error instanceof ApiError ? error.detail : "Failed to update room mode.");
    }
  });

  const assignMutation = useMutation({
    mutationFn: async (agentId: string) => assignRoomAgent(roomId, { agent_id: agentId }),
    onSuccess: async () => {
      setAssignAgentId("");
      setActionMessage("Agent assigned to room.");
      await queryClient.invalidateQueries({ queryKey: ["roomAgents", roomId] });
    },
    onError: (error) => {
      setActionMessage(error instanceof ApiError ? error.detail : "Failed to assign agent.");
    }
  });

  const unassignMutation = useMutation({
    mutationFn: async (agentId: string) => removeRoomAgent(roomId, agentId),
    onSuccess: async () => {
      setActionMessage("Agent removed from room.");
      await queryClient.invalidateQueries({ queryKey: ["roomAgents", roomId] });
    },
    onError: (error) => {
      setActionMessage(error instanceof ApiError ? error.detail : "Failed to remove agent.");
    }
  });

  const createSessionMutation = useMutation({
    mutationFn: async () => createRoomSession(roomId),
    onSuccess: async (session) => {
      setSelectedSessionId(session.id);
      setActionMessage("Session created.");
      await queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
      await queryClient.invalidateQueries({ queryKey: ["sessionMessages", session.id] });
      await queryClient.invalidateQueries({ queryKey: ["sessionTurns", session.id] });
    },
    onError: (error) => {
      setActionMessage(error instanceof ApiError ? error.detail : "Failed to create session.");
    }
  });

  const submitTurnMutation = useMutation({
    mutationFn: async ({ sessionId, message }: { sessionId: string; message: string }) =>
      submitTurn(sessionId, { message }),
    onSuccess: async () => {
      setMessageInput("");
      setComposerError("");
      setActionMessage("Turn sent.");
      await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
      await queryClient.invalidateQueries({ queryKey: ["sessionTurns", selectedSessionId] });
      await queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
    },
    onError: (error) => {
      setComposerError(error instanceof ApiError ? error.detail : "Failed to send turn.");
    }
  });

  const uploadFileMutation = useMutation({
    mutationFn: async (file: File) => uploadFile(roomId, file),
    onSuccess: async () => {
      setActionMessage("File uploaded successfully.");
      await queryClient.invalidateQueries({ queryKey: ["roomFiles", roomId] });
    },
    onError: (error) => {
      setActionMessage(error instanceof ApiError ? error.detail : "Failed to upload file.");
    }
  });

  async function handleSendTurn() {
    setComposerError("");
    setActionMessage("");
    const trimmed = messageInput.trim();
    if (!selectedSessionId) {
      setComposerError("Create or select a session first.");
      return;
    }
    if (!trimmed) {
      setComposerError("Message is required.");
      return;
    }

    if (!streamingEnabled) {
      await submitTurnMutation.mutateAsync({ sessionId: selectedSessionId, message: trimmed });
      return;
    }

    setIsStreaming(true);
    setStreamDraft("");
    setStreamTrace(["Connecting stream..."]);
    try {
      let sawChunk = false;
      const streamResult = await submitTurnStream(selectedSessionId, { message: trimmed }, (event: StreamEvent) => {
        if (event.type === "chunk" && typeof event.delta === "string") {
          sawChunk = true;
          setStreamDraft((prev) => prev + event.delta);
          return;
        }
        if ((event.type === "round_start" || event.type === "round_end") && typeof event.round === "number") {
          const label = event.type === "round_start" ? `Round ${event.round} started` : `Round ${event.round} finished`;
          setStreamTrace((prev) => [...prev, label]);
        }
      });
      setMessageInput("");
      if (streamResult.doneEvent) {
        const doneTurnId = streamResult.doneEvent.turn_id;
        setStreamTrace((prev) => [...prev, `Done event received (turn ${doneTurnId.slice(0, 8)})`]);
      } else {
        setStreamTrace((prev) => [...prev, "Stream ended without explicit done event."]);
      }
      setActionMessage(
        sawChunk
          ? "Stream complete."
          : "Stream completed but no incremental chunks were emitted by the backend response."
      );
      await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
      await queryClient.invalidateQueries({ queryKey: ["sessionTurns", selectedSessionId] });
    } catch (error) {
      const detail = error instanceof ApiError ? error.detail : "Streaming failed.";
      setStreamTrace((prev) => [...prev, `Stream failed: ${detail}`, "Falling back to standard send..."]);
      try {
        await submitTurn(selectedSessionId, { message: trimmed });
        setMessageInput("");
        setComposerError("");
        setActionMessage(`Streaming unavailable (${detail}). Turn sent via standard mode.`);
        await queryClient.invalidateQueries({ queryKey: ["sessionMessages", selectedSessionId] });
        await queryClient.invalidateQueries({ queryKey: ["sessionTurns", selectedSessionId] });
        await queryClient.invalidateQueries({ queryKey: ["roomSessions", roomId] });
      } catch {
        setComposerError(detail);
      }
    } finally {
      setIsStreaming(false);
    }
  }

  const selectedSession: SessionRead | undefined = (sessionsQuery.data || []).find((item) => item.id === selectedSessionId);

  return (
    <section className="grid gap-4">
      <header className="rounded-xl border border-[--border] bg-[--bg-surface] p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">{roomQuery.data?.name || "Room"}</h1>
            <p className="mt-1 text-sm text-[--text-muted]">
              {roomQuery.data?.goal || "Room workspace for sessions, agent assignment, and chat history."}
            </p>
          </div>
          <Button type="button" onClick={() => createSessionMutation.mutate()} disabled={createSessionMutation.isPending}>
            {createSessionMutation.isPending ? "Creating session..." : "New Session"}
          </Button>
        </div>
        {actionMessage ? <p className="mt-3 text-sm text-[--text-muted]">{actionMessage}</p> : null}
      </header>

      <div className="grid gap-4 xl:grid-cols-[380px_1fr]">
        <div className="grid gap-4">
          <article className="rounded-xl border border-[--border] bg-[--bg-surface] p-4">
            <h2 className="text-lg font-semibold">Room Mode</h2>
            <label className="mt-3 grid gap-1 text-sm">
              <span className="text-[--text-muted]">Interaction style</span>
              <select
                className="h-10 rounded-md border border-[--border] bg-[--bg-base] px-3 text-[--text-primary]"
                value={modeDraft}
                onChange={(event) => setModeDraft(event.target.value as RoomMode)}
              >
                {MODE_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
              <span className="text-xs text-[--text-muted]">
                {MODE_OPTIONS.find((option) => option.value === modeDraft)?.description}
              </span>
            </label>
            <div className="mt-3">
              <Button type="button" onClick={() => saveModeMutation.mutate()} disabled={saveModeMutation.isPending}>
                {saveModeMutation.isPending ? "Saving..." : "Save Mode"}
              </Button>
            </div>
          </article>

          <article className="rounded-xl border border-[--border] bg-[--bg-surface] p-4">
            <h2 className="text-lg font-semibold">Assigned Agents</h2>
            <div className="mt-3 grid gap-2">
              {(roomAgentsQuery.data || []).map((assignment: RoomAgentRead) => (
                <div key={assignment.id} className="rounded-md border border-[--border] bg-[--bg-base] p-3 text-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <div className="font-medium">{assignment.agent.name}</div>
                      <div className="text-xs text-[--text-muted]">
                        {assignment.agent.model_alias} · #{assignment.position}
                      </div>
                    </div>
                    <Button
                      type="button"
                      variant="ghost"
                      onClick={() => unassignMutation.mutate(assignment.agent_id)}
                      disabled={unassignMutation.isPending}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
              {!roomAgentsQuery.isLoading && (roomAgentsQuery.data || []).length === 0 ? (
                <p className="text-sm text-[--text-muted]">No agents assigned yet.</p>
              ) : null}
            </div>
            <div className="mt-3 grid gap-2">
              <select
                className="h-10 rounded-md border border-[--border] bg-[--bg-base] px-3 text-[--text-primary]"
                value={assignAgentId}
                onChange={(event) => setAssignAgentId(event.target.value)}
              >
                <option value="">Select an agent to assign</option>
                {assignableAgents.map((agent: AgentRead) => (
                  <option key={agent.id} value={agent.id}>
                    {agent.name} ({agent.model_alias})
                  </option>
                ))}
              </select>
              <Button
                type="button"
                onClick={() => {
                  if (assignAgentId) {
                    assignMutation.mutate(assignAgentId);
                  }
                }}
                disabled={!assignAgentId || assignMutation.isPending}
              >
                {assignMutation.isPending ? "Assigning..." : "Assign Agent"}
              </Button>
            </div>
          </article>

          <article className="rounded-xl border border-[--border] bg-[--bg-surface] p-4">
            <h2 className="text-lg font-semibold">Sessions</h2>
            <div className="mt-3 grid gap-2">
              {(sessionsQuery.data || []).map((session: SessionRead) => (
                <button
                  key={session.id}
                  type="button"
                  onClick={() => setSelectedSessionId(session.id)}
                  className={[
                    "rounded-md border px-3 py-2 text-left text-sm transition-colors",
                    selectedSessionId === session.id
                      ? "border-[--accent] bg-[--accent]/15"
                      : "border-[--border] bg-[--bg-base] hover:bg-[--bg-elevated]"
                  ].join(" ")}
                >
                  <div className="font-medium">Session {session.id.slice(0, 8)}</div>
                  <div className="text-xs text-[--text-muted]">{formatDateTime(session.created_at)}</div>
                </button>
              ))}
              {!sessionsQuery.isLoading && (sessionsQuery.data || []).length === 0 ? (
                <p className="text-sm text-[--text-muted]">No sessions yet. Create one to start chatting.</p>
              ) : null}
            </div>
          </article>
        </div>

        <article className="rounded-xl border border-[--border] bg-[--bg-surface] p-4">
          <h2 className="text-lg font-semibold">Workspace</h2>
          <p className="mt-1 text-sm text-[--text-muted]">
            {selectedSession
              ? `Session ${selectedSession.id.slice(0, 8)} · created ${formatDateTime(selectedSession.created_at)}`
              : "Select a session to view history and send turns."}
          </p>

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <div className="rounded-md border border-[--border] bg-[--bg-base] p-3">
              <h3 className="text-sm font-semibold">Messages</h3>
              <div className="mt-2 max-h-72 space-y-2 overflow-y-auto pr-1">
                {(messagesQuery.data?.messages || []).map((message) => (
                  <div key={message.id} className="rounded border border-[--border] p-2 text-sm">
                    <div className="text-xs text-[--text-muted]">
                      {message.role}
                      {message.agent_name ? ` · ${message.agent_name}` : ""} · {formatDateTime(message.created_at)}
                    </div>
                    <p className="mt-1 whitespace-pre-wrap">{message.content}</p>
                  </div>
                ))}
                {selectedSessionId && !messagesQuery.isLoading && (messagesQuery.data?.messages || []).length === 0 ? (
                  <p className="text-sm text-[--text-muted]">No messages yet.</p>
                ) : null}
              </div>
            </div>

            <div className="rounded-md border border-[--border] bg-[--bg-base] p-3">
              <h3 className="text-sm font-semibold">Turns</h3>
              <div className="mt-2 max-h-72 space-y-2 overflow-y-auto pr-1">
                {(turnsQuery.data?.turns || []).map((turn) => (
                  <div key={turn.id} className="rounded border border-[--border] p-2 text-sm">
                    <div className="text-xs text-[--text-muted]">
                      #{turn.turn_index} · {turn.mode} · {turn.status} · {formatDateTime(turn.created_at)}
                    </div>
                    <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-[--text-muted]">{turn.assistant_output}</p>
                  </div>
                ))}
                {selectedSessionId && !turnsQuery.isLoading && (turnsQuery.data?.turns || []).length === 0 ? (
                  <p className="text-sm text-[--text-muted]">No turns yet.</p>
                ) : null}
              </div>
            </div>
          </div>

          <div className="mt-4 rounded-md border border-[--border] bg-[--bg-base] p-3">
            <div className="flex items-center justify-between mb-2">
              <h3 className="text-sm font-semibold">Attached Files</h3>
            </div>
            {filesQuery.data && filesQuery.data.length > 0 ? (
              <div className="flex flex-wrap gap-2 text-xs">
                {filesQuery.data.map((file) => (
                  <div key={file.id} className="flex items-center gap-1 rounded bg-[--bg-surface] px-2 py-1 border border-[--border]" title={`ID: ${file.id}\nStatus: ${file.parse_status}`}>
                    <span
                      className="inline-block h-2 w-2 rounded-full"
                      style={{
                        backgroundColor:
                          file.parse_status === "completed"
                            ? "var(--green)"
                            : file.parse_status === "failed"
                              ? "var(--red)"
                              : "var(--orange)"
                      }}
                    />
                    {file.filename}
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-[--text-muted]">No files uploaded for this room.</p>
            )}
          </div>

          <div className="mt-4 grid gap-2">
            <label className="text-sm text-[--text-muted]" htmlFor="turn-message">
              Send a turn
            </label>
            <textarea
              id="turn-message"
              className="min-h-28 rounded-md border border-[--border] bg-[--bg-base] px-3 py-2 text-[--text-primary]"
              value={messageInput}
              onChange={(event) => setMessageInput(event.target.value)}
              placeholder="Type your message..."
              disabled={!selectedSessionId || isStreaming || submitTurnMutation.isPending}
            />
            <div className="flex items-center justify-between">
              <label className="inline-flex items-center gap-2 text-sm text-[--text-muted]">
                <input
                  type="checkbox"
                  checked={streamingEnabled}
                  onChange={(event) => setStreamingEnabled(event.target.checked)}
                  disabled={!selectedSessionId || isStreaming || submitTurnMutation.isPending}
                />
                Enable streaming
              </label>
              <div>
                <input
                  type="file"
                  id="file-upload"
                  className="hidden"
                  accept=".txt,.md,.csv"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      uploadFileMutation.mutate(file);
                    }
                    e.target.value = "";
                  }}
                />
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => document.getElementById("file-upload")?.click()}
                  disabled={uploadFileMutation.isPending}
                  title="Upload File (.txt, .md, .csv)"
                >
                  {uploadFileMutation.isPending ? "Uploading..." : "📎"}
                </Button>
                <Button
                  className="ml-2"
                  type="button"
                  onClick={handleSendTurn}
                  disabled={!selectedSessionId || isStreaming || submitTurnMutation.isPending}
                >
                  {isStreaming ? "Streaming..." : submitTurnMutation.isPending ? "Sending..." : "Send Turn"}
                </Button>
              </div>
            </div>
            {composerError ? <p className="text-sm text-red-300">{composerError}</p> : null}
          </div>

          {isStreaming || streamDraft || streamTrace.length > 0 ? (
            <div className="mt-4 rounded-md border border-[--border] bg-[--bg-base] p-3">
              <h3 className="text-sm font-semibold">Live Response</h3>
              {streamTrace.length > 0 ? (
                <ul className="mt-2 space-y-1 text-xs text-[--text-muted]">
                  {streamTrace.map((line, index) => (
                    <li key={`${line}-${index}`}>{line}</li>
                  ))}
                </ul>
              ) : null}
              <p className="mt-2 whitespace-pre-wrap text-sm">{streamDraft || "Waiting for chunks..."}</p>
            </div>
          ) : null}
        </article>
      </div>
    </section>
  );
}
