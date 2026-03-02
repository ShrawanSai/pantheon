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

function getApiTimeoutMs(): number {
  const raw = process.env.NEXT_PUBLIC_API_TIMEOUT_MS;
  const parsed = raw ? Number(raw) : NaN;
  if (Number.isFinite(parsed) && parsed > 0) {
    return parsed;
  }
  return 15_000;
}

function parseErrorDetail(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== "object") {
    return fallback;
  }

  const data = payload as Record<string, unknown>;
  const detail = data.detail;
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (item && typeof item === "object" ? (item as Record<string, unknown>).msg : null))
      .filter((msg): msg is string => typeof msg === "string" && msg.trim().length > 0);
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  if (detail && typeof detail === "object") {
    const detailObj = detail as Record<string, unknown>;
    if (typeof detailObj.message === "string") {
      return detailObj.message;
    }
    if (typeof detailObj.detail === "string") {
      return detailObj.detail;
    }
    if (typeof detailObj.code === "string") {
      return detailObj.code;
    }
  }
  if (typeof data.message === "string") {
    return data.message;
  }
  return fallback;
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
  
  if (!(init?.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  if (session?.access_token) {
    headers.set("Authorization", `Bearer ${session.access_token}`);
  }

  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), getApiTimeoutMs());
  let response: Response;
  try {
    response = await fetch(`${getApiBase()}${path}`, {
      ...init,
      headers,
      signal: controller.signal
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      throw new ApiError(504, "Request timed out. Please retry.");
    }
    throw error;
  } finally {
    window.clearTimeout(timeout);
  }

  if (!response.ok) {
    let detail = response.statusText || "Request failed";
    try {
      const payload = await response.json();
      detail = parseErrorDetail(payload, detail);
    } catch {
      const fallback = await response.text().catch(() => "");
      if (fallback.trim()) {
        detail = fallback;
      }
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
