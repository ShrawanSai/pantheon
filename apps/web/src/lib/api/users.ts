"use client";

import { apiFetch } from "@/lib/api/client";

export type WalletRead = {
  user_id: string;
  balance: string;
};

export function getMyWallet(): Promise<WalletRead> {
  return apiFetch<WalletRead>("/api/v1/users/me/wallet", {
    method: "GET"
  });
}

export type TransactionRead = {
  id: string;
  kind: string;
  amount: string;
  initiated_by: string | null;
  note: string | null;
  reference_id: string | null;
  created_at: string;
};

export type TransactionsResponse = {
  transactions: TransactionRead[];
  total: number;
};

export function getMyTransactions(): Promise<TransactionsResponse> {
  return apiFetch<TransactionsResponse>("/api/v1/users/me/transactions", {
    method: "GET"
  });
}

export type TopUpRead = {
  client_secret: string;
  credits_to_grant: number;
  amount_usd: number;
};

export function createTopUpIntent(amount_usd: number): Promise<TopUpRead> {
  return apiFetch<TopUpRead>("/api/v1/users/me/wallet/top-up", {
    method: "POST",
    body: JSON.stringify({ amount_usd }),
  });
}

export type UsageEventRead = {
  id: string;
  model_alias: string;
  credits_burned: string;
  created_at: string;
};

export type UsageListRead = {
  events: UsageEventRead[];
  total: number;
};

export function getMyUsage(limit = 50): Promise<UsageListRead> {
  return apiFetch<UsageListRead>(`/api/v1/users/me/usage?limit=${limit}`, {
    method: "GET",
  });
}
