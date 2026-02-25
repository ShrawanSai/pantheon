"use client";

import { apiFetch } from "@/lib/api/client";
import type { AgentRead } from "@/lib/api/agents";

export type RoomMode = "manual" | "roundtable" | "orchestrator";

export type RoomRead = {
  id: string;
  owner_user_id: string;
  name: string;
  goal: string | null;
  current_mode: RoomMode;
  pending_mode: RoomMode | null;
  created_at: string;
  updated_at: string;
};

export type RoomAgentRead = {
  id: string;
  room_id: string;
  agent_id: string;
  agent: AgentRead;
  position: number;
  created_at: string;
};

type RoomCreateRequest = {
  name: string;
  goal?: string | null;
  current_mode: RoomMode;
};

export function listRooms(): Promise<RoomRead[]> {
  return apiFetch<RoomRead[]>("/api/v1/rooms", { method: "GET" });
}

export function getRoom(roomId: string): Promise<RoomRead> {
  return apiFetch<RoomRead>(`/api/v1/rooms/${roomId}`, { method: "GET" });
}

export function createRoom(payload: RoomCreateRequest): Promise<RoomRead> {
  return apiFetch<RoomRead>("/api/v1/rooms", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateRoomMode(roomId: string, mode: RoomMode): Promise<RoomRead> {
  return apiFetch<RoomRead>(`/api/v1/rooms/${roomId}/mode`, {
    method: "PATCH",
    body: JSON.stringify({ mode })
  });
}

export async function deleteRoom(roomId: string): Promise<void> {
  await apiFetch<null>(`/api/v1/rooms/${roomId}`, {
    method: "DELETE"
  });
}

export function listRoomAgents(roomId: string): Promise<RoomAgentRead[]> {
  return apiFetch<RoomAgentRead[]>(`/api/v1/rooms/${roomId}/agents`, {
    method: "GET"
  });
}

export function assignRoomAgent(roomId: string, payload: { agent_id: string; position?: number }): Promise<RoomAgentRead> {
  return apiFetch<RoomAgentRead>(`/api/v1/rooms/${roomId}/agents`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function removeRoomAgent(roomId: string, agentId: string): Promise<void> {
  await apiFetch<null>(`/api/v1/rooms/${roomId}/agents/${agentId}`, {
    method: "DELETE"
  });
}
