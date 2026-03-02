"use client";

import { apiFetch } from "@/lib/api/client";

// ── Pricing ──────────────────────────────────────────────────────────────────
export type AdminPricingItem = {
  model_alias: string;
  multiplier: string;
  pricing_version: string;
};

export type AdminPricingListRead = {
  pricing_version: string;
  items: AdminPricingItem[];
};

export function getAdminPricing(): Promise<AdminPricingListRead> {
  return apiFetch<AdminPricingListRead>("/api/v1/admin/pricing", { method: "GET" });
}

export function updateAdminPricing(
  model_alias: string,
  payload: { multiplier: number; pricing_version: string }
): Promise<AdminPricingItem> {
  return apiFetch<AdminPricingItem>(`/api/v1/admin/pricing/${encodeURIComponent(model_alias)}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

// ── Usage ─────────────────────────────────────────────────────────────────────
export type AdminUsageBreakdownItem = {
  model_alias: string;
  call_count: number;
  credits_burned: string;
};

export type AdminUsageDailyItem = {
  date: string;
  credits_burned: string;
  call_count: number;
};

export type AdminUsageSummaryRead = {
  total_credits_burned: string;
  total_llm_calls: number;
  total_output_tokens: number;
  from_date: string | null;
  to_date: string | null;
  breakdown: AdminUsageBreakdownItem[];
  daily: AdminUsageDailyItem[];
};

export function getAdminUsageSummary(params?: {
  bucket?: "day" | "week" | "month";
  from_date?: string;
  to_date?: string;
}): Promise<AdminUsageSummaryRead> {
  const q = new URLSearchParams();
  if (params?.bucket) q.set("bucket", params.bucket);
  if (params?.from_date) q.set("from_date", params.from_date);
  if (params?.to_date) q.set("to_date", params.to_date);
  const qs = q.toString();
  return apiFetch<AdminUsageSummaryRead>(`/api/v1/admin/usage/summary${qs ? `?${qs}` : ""}`, { method: "GET" });
}

export type AdminUsageAnalyticsRow = {
  user_id: string;
  model_alias: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_credits_burned: string;
  event_count: number;
};

export type AdminUsageAnalyticsRead = {
  rows: AdminUsageAnalyticsRow[];
  total: number;
  start_date: string;
  end_date: string;
};

export function getAdminUsageAnalytics(params: {
  start_date: string;
  end_date: string;
  limit?: number;
  offset?: number;
}): Promise<AdminUsageAnalyticsRead> {
  const q = new URLSearchParams({
    start_date: params.start_date,
    end_date: params.end_date,
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return apiFetch<AdminUsageAnalyticsRead>(`/api/v1/admin/analytics/usage?${q}`, { method: "GET" });
}

export type AdminActiveUsersRead = {
  window: string;
  as_of: string;
  active_users: number;
  new_users: number;
};

export function getAdminActiveUsers(
  window: "day" | "week" | "month" = "day"
): Promise<AdminActiveUsersRead> {
  return apiFetch<AdminActiveUsersRead>(`/api/v1/admin/analytics/active-users?window=${window}`, { method: "GET" });
}

// ── Settings ──────────────────────────────────────────────────────────────────
export type AdminSettingsRead = {
  enforcement_enabled: boolean;
  enforcement_source: string;
  low_balance_threshold: number;
  pricing_version: string;
};

export function getAdminSettings(): Promise<AdminSettingsRead> {
  return apiFetch<AdminSettingsRead>("/api/v1/admin/settings", { method: "GET" });
}

export type AdminEnforcementRead = {
  enforcement_enabled: boolean;
  source: string;
};

export function setAdminEnforcement(enabled: boolean): Promise<AdminEnforcementRead> {
  return apiFetch<AdminEnforcementRead>("/api/v1/admin/settings/enforcement", {
    method: "PATCH",
    body: JSON.stringify({ enabled }),
  });
}

export function clearAdminEnforcement(): Promise<AdminEnforcementRead> {
  return apiFetch<AdminEnforcementRead>("/api/v1/admin/settings/enforcement", { method: "DELETE" });
}

// ── Wallets ───────────────────────────────────────────────────────────────────
export type AdminWalletTransaction = {
  id: string;
  kind: string;
  amount: string;
  initiated_by: string | null;
  note: string | null;
  created_at: string;
};

export type AdminWalletRead = {
  user_id: string;
  balance: string;
  recent_transactions: AdminWalletTransaction[];
};

export function getAdminWallet(user_id: string): Promise<AdminWalletRead> {
  return apiFetch<AdminWalletRead>(`/api/v1/admin/wallets/${encodeURIComponent(user_id)}`, { method: "GET" });
}

export type AdminGrantResponse = {
  user_id: string;
  new_balance: string;
  transaction_id: string;
};

export function grantAdminCredits(
  user_id: string,
  payload: { amount: number; note?: string }
): Promise<AdminGrantResponse> {
  return apiFetch<AdminGrantResponse>(`/api/v1/admin/wallets/${encodeURIComponent(user_id)}/grant`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
