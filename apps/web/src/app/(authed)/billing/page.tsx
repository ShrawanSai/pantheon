"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, History, Plus, X, Loader2, Zap, CheckCircle2, Info } from "lucide-react";
import { loadStripe } from "@stripe/stripe-js";
import { Elements, PaymentElement, useStripe, useElements } from "@stripe/react-stripe-js";

import { Button } from "@/components/ui/button";
import {
  getMyWallet,
  getMyTransactions,
  createTopUpIntent,
  getMyUsage,
  type TransactionsResponse,
} from "@/lib/api/users";
import { ApiError } from "@/lib/api/client";

const stripePromise = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY
  ? loadStripe(process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY)
  : null;

// ── Stripe checkout form ──────────────────────────────────────────────────
function CheckoutForm({
  amountUsd,
  creditsToGrant,
  onSuccess,
  onCancel,
}: {
  amountUsd: number;
  creditsToGrant: number;
  onSuccess: () => void;
  onCancel: () => void;
}) {
  const stripe = useStripe();
  const elements = useElements();
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);
  const [succeeded, setSucceeded] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!stripe || !elements) return;
    setError("");
    setProcessing(true);
    const result = await stripe.confirmPayment({
      elements,
      confirmParams: { return_url: window.location.href },
      redirect: "if_required",
    });
    setProcessing(false);
    if (result.error) {
      setError(result.error.message ?? "Payment failed.");
    } else {
      setSucceeded(true);
      setTimeout(onSuccess, 1500);
    }
  }

  if (succeeded) {
    return (
      <div className="flex flex-col items-center justify-center py-10 gap-3">
        <CheckCircle2 className="w-12 h-12 text-success" />
        <p className="font-bold text-foreground text-lg">Payment confirmed!</p>
        <p className="text-sm text-muted">Your balance will update shortly.</p>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="p-4 rounded-xl bg-elevated border border-border text-sm">
        <div className="flex justify-between text-muted mb-1">
          <span>Amount</span><span className="text-foreground font-bold">${amountUsd.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-muted">
          <span>Credits</span><span className="text-accent font-bold">+{creditsToGrant.toFixed(2)} cr</span>
        </div>
      </div>
      <PaymentElement />
      {error && <p className="text-sm text-error">{error}</p>}
      <div className="flex gap-3 pt-2">
        <Button type="button" variant="ghost" onClick={onCancel} className="flex-1 rounded-xl">Cancel</Button>
        <Button
          type="submit"
          disabled={!stripe || processing}
          className="flex-1 rounded-xl bg-accent hover:bg-accent-hover text-white"
        >
          {processing ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
          {processing ? "Processing…" : `Pay $${amountUsd.toFixed(2)}`}
        </Button>
      </div>
    </form>
  );
}

// ── Main billing page ─────────────────────────────────────────────────────
function formatDate(iso: string): string {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "—" : d.toLocaleDateString();
}

export default function BillingPage() {
  const queryClient = useQueryClient();
  const [topUpAmount, setTopUpAmount] = useState<number>(10);
  const [checkoutState, setCheckoutState] = useState<{
    clientSecret: string;
    amountUsd: number;
    creditsToGrant: number;
  } | null>(null);

  const walletQuery = useQuery({ queryKey: ["wallet", "me"], queryFn: getMyWallet });
  const txQuery = useQuery<TransactionsResponse>({ queryKey: ["transactions", "me"], queryFn: getMyTransactions });
  const usageQuery = useQuery({ queryKey: ["usage", "me"], queryFn: () => getMyUsage(20) });

  const topUpMutation = useMutation({
    mutationFn: () => createTopUpIntent(topUpAmount),
    onSuccess: data => {
      setCheckoutState({
        clientSecret: data.client_secret,
        amountUsd: data.amount_usd,
        creditsToGrant: data.credits_to_grant,
      });
    },
  });

  function handleTopUpSuccess() {
    setCheckoutState(null);
    queryClient.invalidateQueries({ queryKey: ["wallet", "me"] });
    queryClient.invalidateQueries({ queryKey: ["transactions", "me"] });
  }

  const balance = walletQuery.data?.balance ? Number(walletQuery.data.balance) : 0;

  return (
    <div className="flex h-full flex-col bg-background overflow-y-auto">
      <div className="mx-auto w-full max-w-5xl px-6 py-8">
        <header className="mb-8">
          <h1 className="text-2xl font-bold text-foreground tracking-tight">Billing & Credits</h1>
          <p className="mt-1 text-sm text-muted">Manage your balance and view usage history.</p>
        </header>

        <div className="grid gap-6 md:grid-cols-3">
          {/* Balance Card */}
          <div className="md:col-span-1 space-y-4">
            <div className="rounded-2xl border border-border bg-white dark:bg-surface p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <CreditCard className="h-5 w-5 text-accent" />
                <h2 className="text-lg font-semibold">Available Balance</h2>
              </div>

              <div className="mb-8">
                <div className="text-4xl font-bold tracking-tight text-foreground">
                  {walletQuery.isLoading ? <Loader2 className="w-6 h-6 animate-spin text-muted" /> : `${balance.toFixed(2)} cr`}
                </div>
                <p className="mt-1 text-sm text-muted">&asymp; ${(balance * 0.03).toFixed(4)} USD &middot; 1 cr = $0.03</p>
              </div>

              {/* Top-up controls */}
              {!checkoutState ? (
                <div className="space-y-4">
                  <div className="text-sm font-medium">Quick Top-up</div>
                  <div className="grid grid-cols-3 gap-2">
                    {[10, 25, 50].map(amount => (
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
                  <Button
                    className="w-full h-11 rounded-xl bg-accent hover:bg-accent-hover text-white font-medium"
                    disabled={topUpMutation.isPending || !stripePromise}
                    onClick={() => topUpMutation.mutate()}
                  >
                    {topUpMutation.isPending ? (
                      <Loader2 className="h-4 w-4 animate-spin mr-2" />
                    ) : (
                      <Plus className="h-4 w-4 mr-2" />
                    )}
                    {topUpMutation.isPending ? "Loading…" : `Add $${topUpAmount}`}
                  </Button>
                  {!stripePromise && (
                    <p className="text-xs text-muted text-center">Stripe not configured.</p>
                  )}
                  {topUpMutation.isError && (
                    <p className="text-xs text-error text-center">
                      {topUpMutation.error instanceof ApiError ? topUpMutation.error.detail : "Failed to start payment."}
                    </p>
                  )}
                </div>
              ) : (
                <div className="relative">
                  <button
                    onClick={() => setCheckoutState(null)}
                    className="absolute -top-1 -right-1 w-6 h-6 rounded-full bg-elevated flex items-center justify-center text-muted hover:text-foreground transition-colors"
                  >
                    <X className="w-3 h-3" />
                  </button>
                  {stripePromise && (
                    <Elements
                      stripe={stripePromise}
                      options={{ clientSecret: checkoutState.clientSecret, appearance: { theme: "stripe" } }}
                    >
                      <CheckoutForm
                        amountUsd={checkoutState.amountUsd}
                        creditsToGrant={checkoutState.creditsToGrant}
                        onSuccess={handleTopUpSuccess}
                        onCancel={() => setCheckoutState(null)}
                      />
                    </Elements>
                  )}
                </div>
              )}
            </div>

            {/* Usage breakdown */}
            {usageQuery.data?.events && usageQuery.data.events.length > 0 && (
              <div className="rounded-2xl border border-border bg-white dark:bg-surface p-5 shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <Zap className="h-4 w-4 text-muted" />
                  <h3 className="text-sm font-semibold text-foreground">Recent Usage</h3>
                </div>
                <div className="space-y-2">
                  {usageQuery.data.events.slice(0, 5).map(u => (
                    <div key={u.id} className="flex items-center justify-between text-xs">
                      <span className="text-muted font-medium">{u.model_alias}</span>
                      <span className="text-foreground font-mono">{Number(u.credits_burned).toFixed(4)} cr</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
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
                  <div className="p-6 text-center text-sm text-muted animate-pulse">Loading history…</div>
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
                      {txQuery.data.transactions.map(tx => {
                        const amt = Number(tx.amount);
                        const isCredit = amt > 0;
                        return (
                          <tr key={tx.id} className="hover:bg-elevated/30 transition-colors">
                            <td className="px-6 py-4">
                              <span className="font-medium text-foreground capitalize">{tx.kind}</span>
                              <div className="text-xs text-muted truncate max-w-[200px] mt-0.5">{tx.note || "—"}</div>
                            </td>
                            <td className="px-6 py-4">
                              <span className={`font-mono font-medium ${isCredit ? "text-success" : "text-foreground"}`}>
                                {isCredit ? "+" : ""}{Math.abs(amt).toFixed(4)} cr
                              </span>
                            </td>
                            <td className="px-6 py-4 text-muted">{formatDate(tx.created_at)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Credits Explainer */}
        <div className="mt-8 rounded-2xl border border-border bg-white dark:bg-surface p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-5">
            <Info className="h-5 w-5 text-accent" />
            <h2 className="text-lg font-semibold">How Credits Work</h2>
          </div>
          <div className="grid gap-6 md:grid-cols-3">
            <div>
              <h3 className="text-sm font-semibold text-foreground mb-2">What is a credit?</h3>
              <p className="text-sm text-muted leading-relaxed">
                Credits are Pantheon&apos;s internal billing unit. <strong className="text-foreground">1 credit = $0.03 USD</strong>. When you add $10, you receive ~333 credits. Credits are consumed as you send messages to AI agents.
              </p>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground mb-2">How are credits calculated?</h3>
              <p className="text-sm text-muted leading-relaxed mb-2">Each AI call computes <em>OE tokens</em> from your actual token usage, then applies a model multiplier:</p>
              <div className="rounded-lg bg-elevated border border-border p-3 font-mono text-xs text-foreground space-y-1">
                <div>OE = (fresh &times; 0.35) + (cached &times; 0.10) + output</div>
                <div>credits = OE &times; multiplier / 10,000</div>
              </div>
            </div>
            <div>
              <h3 className="text-sm font-semibold text-foreground mb-2">Model multipliers</h3>
              <div className="space-y-1.5">
                {[
                  { label: "Mistral Small", mult: "0.3×" },
                  { label: "Llama 4 Scout", mult: "0.5×" },
                  { label: "Qwen3 / DeepSeek", mult: "0.5×" },
                  { label: "Gemini 2.5 Flash", mult: "0.8×" },
                  { label: "GPT OSS 120B", mult: "1.5×" },
                  { label: "Gemini 2.5 Pro", mult: "2.0×" },
                ].map(row => (
                  <div key={row.label} className="flex items-center justify-between text-xs">
                    <span className="text-muted">{row.label}</span>
                    <span className="font-mono font-semibold text-foreground">{row.mult}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
