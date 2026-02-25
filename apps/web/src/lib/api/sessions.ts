import { ApiError, apiFetch } from "@/lib/api/client";
import { getSupabaseBrowserClient } from "@/lib/supabase/client";
import { parseSseEvents } from "@/lib/utils/streaming";

export type SessionRead = {
  id: string;
  room_id: string | null;
  agent_id: string | null;
  started_by_user_id: string;
  created_at: string;
  deleted_at: string | null;
};

export type TurnRead = {
  id: string;
  session_id: string;
  turn_index: number;
  mode: "manual" | "tag" | "roundtable" | "orchestrator" | "standalone";
  user_input: string;
  assistant_output: string;
  status: string;
  model_alias_used: string;
  summary_triggered: boolean;
  prune_triggered: boolean;
  overflow_rejected: boolean;
  balance_after: string | null;
  low_balance: boolean;
  summary_used_fallback: boolean;
  created_at: string;
};

export type SessionMessageRead = {
  id: string;
  role: string;
  agent_name: string | null;
  content: string;
  turn_id: string | null;
  created_at: string;
};

export type SessionMessageListRead = {
  messages: SessionMessageRead[];
  total: number;
};

export type SessionTurnHistoryRead = {
  id: string;
  turn_index: number;
  mode: "manual" | "tag" | "roundtable" | "orchestrator" | "standalone";
  user_input: string;
  assistant_output: string;
  status: string;
  created_at: string;
};

export type SessionTurnListRead = {
  turns: SessionTurnHistoryRead[];
  total: number;
};

export type TurnCreatePayload = {
  message: string;
  model_alias_override?: string | null;
};

export type StreamChunkEvent = {
  type: "chunk";
  delta: string;
};

export type StreamDoneEvent = {
  type: "done";
  turn_id: string;
  provider_model: string;
  summary_used_fallback?: boolean;
  balance_after?: string;
  low_balance?: boolean;
};

export type StreamRoundEvent = {
  type: "round_start" | "round_end";
  round: number;
};

export type StreamEvent = StreamChunkEvent | StreamDoneEvent | StreamRoundEvent | Record<string, unknown>;

export type StreamTurnResult = {
  doneEvent: StreamDoneEvent | null;
  text: string;
  events: StreamEvent[];
};

function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
}

function getApiTimeoutMs(): number {
  const raw = process.env.NEXT_PUBLIC_API_TIMEOUT_MS;
  const parsed = raw ? Number(raw) : NaN;
  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed;
  }
  return 60_000;
}

async function readErrorDetail(response: Response): Promise<string> {
  let detail = response.statusText || "Request failed";
  try {
    const payload = await response.json();
    if (typeof payload?.detail === "string") {
      detail = payload.detail;
    } else if (typeof payload?.message === "string") {
      detail = payload.message;
    } else if (payload?.detail && typeof payload.detail === "object") {
      detail = payload.detail.detail || detail;
    }
    return detail;
  } catch {
    const fallback = await response.text().catch(() => "");
    if (fallback.trim()) {
      detail = fallback;
    }
    return detail;
  }
}

export function listRoomSessions(roomId: string): Promise<SessionRead[]> {
  return apiFetch<SessionRead[]>(`/api/v1/rooms/${roomId}/sessions`, {
    method: "GET"
  });
}

export function createRoomSession(roomId: string): Promise<SessionRead> {
  return apiFetch<SessionRead>(`/api/v1/rooms/${roomId}/sessions`, {
    method: "POST",
    body: JSON.stringify({})
  });
}

export function listSessionMessages(sessionId: string, limit = 100, offset = 0): Promise<SessionMessageListRead> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiFetch<SessionMessageListRead>(`/api/v1/sessions/${sessionId}/messages?${params.toString()}`, {
    method: "GET"
  });
}

export function listSessionTurns(sessionId: string, limit = 50, offset = 0): Promise<SessionTurnListRead> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return apiFetch<SessionTurnListRead>(`/api/v1/sessions/${sessionId}/turns?${params.toString()}`, {
    method: "GET"
  });
}

export function submitTurn(sessionId: string, payload: TurnCreatePayload): Promise<TurnRead> {
  return apiFetch<TurnRead>(`/api/v1/sessions/${sessionId}/turns`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function submitTurnStream(
  sessionId: string,
  payload: TurnCreatePayload,
  onEvent?: (event: StreamEvent) => void
): Promise<StreamTurnResult> {
  const supabase = getSupabaseBrowserClient();
  const {
    data: { session }
  } = await supabase.auth.getSession();

  const headers = new Headers();
  headers.set("Content-Type", "application/json");
  headers.set("Accept", "text/event-stream");
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), getApiTimeoutMs());
  let response: Response;
  try {
    response = await fetch(`${getApiBase()}/api/v1/sessions/${sessionId}/turns/stream`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload),
      signal: controller.signal
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError(504, "Streaming request timed out. Please retry.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readErrorDetail(response));
  }

  if (!response.body) {
    throw new ApiError(502, "Streaming response body is unavailable.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let text = "";
  const events: StreamEvent[] = [];
  let doneEvent: StreamDoneEvent | null = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parsed = parseSseEvents(buffer);
    buffer = parsed.rest;
    for (const event of parsed.events) {
      const typed = event as StreamEvent;
      events.push(typed);
      if (typed && typeof typed === "object" && typed.type === "chunk" && typeof typed.delta === "string") {
        text += typed.delta;
      }
      if (typed && typeof typed === "object" && typed.type === "done") {
        doneEvent = typed as StreamDoneEvent;
      }
      onEvent?.(typed);
    }
  }

  if (buffer.trim()) {
    const parsed = parseSseEvents(`${buffer}\n\n`);
    for (const event of parsed.events) {
      const typed = event as StreamEvent;
      events.push(typed);
      if (typed && typeof typed === "object" && typed.type === "chunk" && typeof typed.delta === "string") {
        text += typed.delta;
      }
      if (typed && typeof typed === "object" && typed.type === "done") {
        doneEvent = typed as StreamDoneEvent;
      }
      onEvent?.(typed);
    }
  }

  return { doneEvent, text, events };
}
