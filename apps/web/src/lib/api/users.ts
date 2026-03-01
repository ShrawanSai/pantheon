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
  tx_type: string;
  amount: string;
  description: string;
  created_at: string;
};

export type TransactionsResponse = {
  transactions: TransactionRead[];
};

export function getMyTransactions(): Promise<TransactionsResponse> {
  return apiFetch<TransactionsResponse>("/api/v1/users/me/transactions", {
    method: "GET"
  });
}
