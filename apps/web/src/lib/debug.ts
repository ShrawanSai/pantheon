"use client";

function isEnabled(): boolean {
  if (process.env.NEXT_PUBLIC_DEBUG_LOGS === "true") {
    return true;
  }
  if (typeof window === "undefined") {
    return false;
  }
  return window.localStorage.getItem("pantheon_debug") === "1";
}

export function debugLog(scope: string, message: string, payload?: unknown): void {
  if (!isEnabled()) return;
  if (payload === undefined) {
    console.log(`[pantheon:${scope}] ${message}`);
    return;
  }
  console.log(`[pantheon:${scope}] ${message}`, payload);
}

export function debugWarn(scope: string, message: string, payload?: unknown): void {
  if (!isEnabled()) return;
  if (payload === undefined) {
    console.warn(`[pantheon:${scope}] ${message}`);
    return;
  }
  console.warn(`[pantheon:${scope}] ${message}`, payload);
}

export function debugError(scope: string, message: string, payload?: unknown): void {
  if (!isEnabled()) return;
  if (payload === undefined) {
    console.error(`[pantheon:${scope}] ${message}`);
    return;
  }
  console.error(`[pantheon:${scope}] ${message}`, payload);
}

