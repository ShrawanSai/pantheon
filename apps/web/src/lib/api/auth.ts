"use client";

import { apiFetch } from "@/lib/api/client";

export type AuthMeResponse = {
  user_id: string;
  email?: string;
};

export function getAuthMe(): Promise<AuthMeResponse> {
  return apiFetch<AuthMeResponse>("/api/v1/auth/me", {
    method: "GET"
  });
}

