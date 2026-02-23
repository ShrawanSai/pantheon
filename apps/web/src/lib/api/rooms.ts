"use client";

import { apiFetch } from "@/lib/api/client";

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

type RoomCreateRequest = {
  name: string;
  goal?: string | null;
  current_mode: RoomMode;
};

export function listRooms(): Promise<RoomRead[]> {
  return apiFetch<RoomRead[]>("/api/v1/rooms", { method: "GET" });
}

export function createRoom(payload: RoomCreateRequest): Promise<RoomRead> {
  return apiFetch<RoomRead>("/api/v1/rooms", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function deleteRoom(roomId: string): Promise<void> {
  await apiFetch<null>(`/api/v1/rooms/${roomId}`, {
    method: "DELETE"
  });
}

