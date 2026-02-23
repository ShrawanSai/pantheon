"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Modal } from "@/components/common/modal";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { createRoom, deleteRoom, listRooms, type RoomMode, type RoomRead } from "@/lib/api/rooms";

type RoomUiMode = "chat" | "task" | "mixed";

type CreateRoomFormState = {
  name: string;
  uiMode: RoomUiMode;
};

const ROOM_MODE_LABELS: Record<RoomMode, string> = {
  manual: "chat",
  roundtable: "task",
  orchestrator: "mixed"
};

function mapUiModeToApiMode(mode: RoomUiMode): RoomMode {
  if (mode === "chat") {
    return "manual";
  }
  if (mode === "task") {
    return "roundtable";
  }
  return "orchestrator";
}

function formatDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleDateString();
}

export default function RoomsPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<RoomRead | null>(null);
  const [form, setForm] = useState<CreateRoomFormState>({
    name: "",
    uiMode: "chat"
  });
  const [formError, setFormError] = useState("");
  const [actionMessage, setActionMessage] = useState("");

  const roomsQuery = useQuery({
    queryKey: ["rooms"],
    queryFn: listRooms
  });

  const sortedRooms = useMemo(() => {
    return [...(roomsQuery.data || [])].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
  }, [roomsQuery.data]);

  const createRoomMutation = useMutation({
    mutationFn: async () => {
      const trimmedName = form.name.trim();
      if (!trimmedName) {
        throw new ApiError(422, "Room name is required.");
      }
      return createRoom({
        name: trimmedName,
        current_mode: mapUiModeToApiMode(form.uiMode)
      });
    },
    onMutate: async () => {
      setFormError("");
      setActionMessage("");
      await queryClient.cancelQueries({ queryKey: ["rooms"] });
      const previousRooms = queryClient.getQueryData<RoomRead[]>(["rooms"]);
      const optimisticRoom: RoomRead = {
        id: `temp-${Date.now()}`,
        owner_user_id: "me",
        name: form.name.trim() || "Untitled room",
        goal: null,
        current_mode: mapUiModeToApiMode(form.uiMode),
        pending_mode: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      queryClient.setQueryData<RoomRead[]>(["rooms"], (old) => [optimisticRoom, ...(old || [])]);
      return { previousRooms };
    },
    onError: (error, _vars, context) => {
      if (context?.previousRooms) {
        queryClient.setQueryData(["rooms"], context.previousRooms);
      }
      setFormError(error instanceof ApiError ? error.detail : error instanceof Error ? error.message : "Failed to create room.");
    },
    onSuccess: () => {
      setCreateOpen(false);
      setForm({ name: "", uiMode: "chat" });
      setActionMessage("Room created successfully.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["rooms"] });
    }
  });

  const deleteRoomMutation = useMutation({
    mutationFn: (roomId: string) => deleteRoom(roomId),
    onMutate: async (roomId) => {
      setActionMessage("");
      await queryClient.cancelQueries({ queryKey: ["rooms"] });
      const previousRooms = queryClient.getQueryData<RoomRead[]>(["rooms"]);
      queryClient.setQueryData<RoomRead[]>(["rooms"], (old) => (old || []).filter((room) => room.id !== roomId));
      return { previousRooms };
    },
    onError: (error, _vars, context) => {
      if (context?.previousRooms) {
        queryClient.setQueryData(["rooms"], context.previousRooms);
      }
      setActionMessage(error instanceof ApiError ? error.detail : error instanceof Error ? error.message : "Failed to delete room.");
    },
    onSuccess: () => {
      setDeleteTarget(null);
      setActionMessage("Room deleted.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["rooms"] });
    }
  });

  return (
    <section className="rounded-xl border border-[--border] bg-[--bg-surface] p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Rooms</h1>
          <p className="mt-1 text-sm text-[--text-muted]">Manage rooms and session workspaces.</p>
        </div>
        <Button type="button" onClick={() => setCreateOpen(true)}>
          Create Room
        </Button>
      </div>

      {actionMessage ? <p className="mb-3 text-sm text-[--text-muted]">{actionMessage}</p> : null}
      {roomsQuery.isError ? (
        <p className="mb-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
          {(roomsQuery.error as ApiError).detail || "Failed to load rooms."}
        </p>
      ) : null}

      {roomsQuery.isLoading ? <p className="text-sm text-[--text-muted]">Loading rooms...</p> : null}

      {!roomsQuery.isLoading && sortedRooms.length === 0 ? (
        <div className="rounded-md border border-dashed border-[--border] p-6 text-center text-sm text-[--text-muted]">
          No rooms yet. Create your first room.
        </div>
      ) : null}

      {sortedRooms.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2">
          {sortedRooms.map((room) => (
            <article key={room.id} className="rounded-lg border border-[--border] bg-[--bg-base] p-4">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-lg font-semibold">{room.name}</h2>
                <span className="rounded-md bg-[--accent]/20 px-2 py-1 text-xs font-medium text-[--text-primary]">
                  {ROOM_MODE_LABELS[room.current_mode]}
                </span>
              </div>
              <p className="mt-2 text-xs text-[--text-muted]">Created: {formatDate(room.created_at)}</p>
              <div className="mt-4 flex justify-end">
                <Button type="button" variant="ghost" onClick={() => setDeleteTarget(room)}>
                  Delete
                </Button>
              </div>
            </article>
          ))}
        </div>
      ) : null}

      <Modal open={createOpen} title="Create room" onClose={() => setCreateOpen(false)}>
        <form
          className="grid gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (createRoomMutation.isPending) {
              return;
            }
            createRoomMutation.mutate();
          }}
        >
          <label className="grid gap-1 text-sm">
            <span className="text-[--text-muted]">Room name</span>
            <input
              className="h-10 rounded-md border border-[--border] bg-[--bg-base] px-3 text-[--text-primary]"
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="Weekly Client Memo"
            />
          </label>

          <label className="grid gap-1 text-sm">
            <span className="text-[--text-muted]">Mode</span>
            <select
              className="h-10 rounded-md border border-[--border] bg-[--bg-base] px-3 text-[--text-primary]"
              value={form.uiMode}
              onChange={(event) => setForm((prev) => ({ ...prev, uiMode: event.target.value as RoomUiMode }))}
            >
              <option value="chat">chat</option>
              <option value="task">task</option>
              <option value="mixed">mixed</option>
            </select>
          </label>

          {formError ? <p className="text-sm text-red-300">{formError}</p> : null}

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)} disabled={createRoomMutation.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={createRoomMutation.isPending}>
              {createRoomMutation.isPending ? "Creating..." : "Create"}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete room"
        description={`Delete '${deleteTarget?.name || "this room"}'? This action cannot be undone.`}
        confirmLabel="Delete"
        loading={deleteRoomMutation.isPending}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteRoomMutation.mutate(deleteTarget.id);
          }
        }}
      />
    </section>
  );
}
