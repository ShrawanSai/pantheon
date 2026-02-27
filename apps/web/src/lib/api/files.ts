"use client";

import { apiFetch } from "@/lib/api/client";

export type UploadedFileRead = {
    id: string;
    room_id: string;
    filename: string;
    content_type: string;
    byte_size: number;
    parse_status: "pending" | "completed" | "failed";
    error_message: string | null;
    created_at: string;
    updated_at: string;
};

export function listRoomFiles(roomId: string): Promise<UploadedFileRead[]> {
    return apiFetch<UploadedFileRead[]>(`/api/v1/rooms/${roomId}/files`, {
        method: "GET"
    });
}

export function uploadFile(roomId: string, file: File): Promise<UploadedFileRead> {
    const formData = new FormData();
    formData.append("file", file);

    return apiFetch<UploadedFileRead>(`/api/v1/rooms/${roomId}/files`, {
        method: "POST",
        body: formData
    });
}
