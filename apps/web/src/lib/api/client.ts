"use client";

import { getSupabaseBrowserClient } from "@/lib/supabase/client";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

function getApiBase(): string {
  return process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
}

async function redirectToLogin() {
  const supabase = getSupabaseBrowserClient();
  await supabase.auth.signOut();
  window.location.href = "/auth/login";
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const supabase = getSupabaseBrowserClient();
  const {
    data: { session }
  } = await supabase.auth.getSession();

  const headers = new Headers(init?.headers || {});
  headers.set("Content-Type", "application/json");
  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  const response = await fetch(`${getApiBase()}${path}`, {
    ...init,
    headers
  });

  if (!response.ok) {
    let detail = response.statusText || "Request failed";
    try {
      const payload = await response.json();
      if (typeof payload?.detail === "string") {
        detail = payload.detail;
      } else if (payload?.detail && typeof payload.detail === "object") {
        detail = payload.detail.detail || detail;
      }
    } catch {
      // keep default detail
    }

    if (response.status === 401) {
      await redirectToLogin();
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") || "";
  if (!contentType.toLowerCase().includes("application/json")) {
    const text = await response.text();
    return (text as unknown) as T;
  }

  const bodyText = await response.text();
  if (!bodyText.trim()) {
    return undefined as T;
  }
  return JSON.parse(bodyText) as T;
}
