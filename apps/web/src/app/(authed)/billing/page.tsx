"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CreditCard, History, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getMyWallet, getMyTransactions, type TransactionsResponse } from "@/lib/api/users";

function formatDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleDateString();
}

export default function BillingPage() {
  const [topUpAmount, setTopUpAmount] = useState<number>(10);

  const walletQuery = useQuery({
    queryKey: ["wallet", "me"],
    queryFn: getMyWallet,
  });

  const txQuery = useQuery<TransactionsResponse>({
    queryKey: ["transactions", "me"],
    queryFn: getMyTransactions,
  });

  return (
    <div className="flex h-full flex-col bg-background p-6">
      <div className="mx-auto w-full max-w-5xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-[24px] font-bold text-foreground tracking-tight">Billing & Credits</h1>
            <p className="mt-1 text-sm text-muted">Manage your balance and view usage history.</p>
          </div>
        </header>

        <div className="grid gap-6 md:grid-cols-3">
          {/* Balance Card */}
          <div className="md:col-span-1">
            <div className="rounded-2xl border border-border bg-white dark:bg-surface p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <CreditCard className="h-5 w-5 text-accent" />
                <h2 className="text-lg font-semibold">Available Balance</h2>
              </div>

              <div className="mb-8">
                <div className="text-4xl font-bold tracking-tight text-foreground">
                  ${walletQuery.isLoading ? "..." : (walletQuery.data?.balance ? Number(walletQuery.data.balance).toFixed(2) : "0.00")}
                </div>
                <p className="mt-1 text-sm text-muted">Credits used for AI API calls</p>
              </div>

              <div className="space-y-4">
                <div className="text-sm font-medium">Quick Top-up</div>
                <div className="grid grid-cols-3 gap-2">
                  {[10, 25, 50].map((amount) => (
                    <button
                      key={amount}
                      onClick={() => setTopUpAmount(amount)}
                      className={`rounded-lg border px-3 py-2 text-sm font-medium transition-colors ${topUpAmount === amount
                        ? "border-accent bg-accent/10 text-accent"
                        : "border-border hover:bg-elevated text-foreground"
                        }`}
                    >
                      ${amount}
                    </button>
                  ))}
                </div>
                <Button className="w-full h-11 rounded-xl bg-accent hover:bg-accent-hover text-white font-medium">
                  <Plus className="h-4 w-4 mr-2" />
                  Add ${topUpAmount}
                </Button>
              </div>
            </div>
          </div>

          {/* Transaction History */}
          <div className="md:col-span-2">
            <div className="rounded-2xl border border-border bg-white dark:bg-surface shadow-sm overflow-hidden h-full flex flex-col">
              <div className="p-6 border-b border-border flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <History className="h-5 w-5 text-muted" />
                  <h2 className="text-lg font-semibold">Transaction History</h2>
                </div>
              </div>

              <div className="flex-1 overflow-auto">
                {txQuery.isLoading ? (
                  <div className="p-6 text-center text-sm text-muted animate-pulse">Loading history...</div>
                ) : !txQuery.data?.transactions?.length ? (
                  <div className="p-12 text-center">
                    <p className="text-sm text-muted">No transactions found.</p>
                  </div>
                ) : (
                  <table className="w-full text-left text-sm">
                    <thead className="bg-elevated/50 text-muted sticky top-0">
                      <tr>
                        <th className="px-6 py-3 font-medium">Type</th>
                        <th className="px-6 py-3 font-medium">Amount</th>
                        <th className="px-6 py-3 font-medium">Date</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {txQuery.data.transactions.map((tx: any) => (
                        <tr key={tx.id} className="hover:bg-elevated/30 transition-colors">
                          <td className="px-6 py-4">
                            <span className="font-medium text-foreground capitalize">{tx.tx_type}</span>
                            <div className="text-xs text-muted truncate max-w-[200px] mt-0.5">{tx.description || "—"}</div>
                          </td>
                          <td className="px-6 py-4">
                            <span className={`font-mono font-medium ${tx.amount.startsWith("-") ? "text-foreground" : "text-success"}`}>
                              {tx.amount.startsWith("-") ? "" : "+"}${Math.abs(Number(tx.amount)).toFixed(2)}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-muted">
                            {formatDate(tx.created_at)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
