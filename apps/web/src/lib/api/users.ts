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

