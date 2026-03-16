"use client";

import { useState, useMemo, useEffect } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, BarChart, Bar,
} from "recharts";
import {
  Activity, Users, DollarSign, Settings, Loader2, ShieldCheck, ShieldOff,
  TrendingUp, Zap, RotateCcw, CheckCircle2, Pencil, X, Check,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  getAdminUsageSummary, getAdminUsageAnalytics, getAdminActiveUsers,
  getAdminPricing, updateAdminPricing,
  getAdminSettings, setAdminEnforcement, clearAdminEnforcement,
  grantAdminCredits,
  type AdminUsageAnalyticsRow,
} from "@/lib/api/admin";
import { ApiError } from "@/lib/api/client";

const TABS = [
  { id: "usage", label: "Usage", icon: Activity },
  { id: "users", label: "Users", icon: Users },
  { id: "pricing", label: "Pricing", icon: DollarSign },
  { id: "settings", label: "Settings", icon: Settings },
];

function dateStr(d: Date) {
  return d.toISOString().slice(0, 10);
}

function today() { return dateStr(new Date()); }
function daysAgo(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return dateStr(d);
}

// ── Usage Tab ─────────────────────────────────────────────────────────────────
function UsageTab() {
  const summaryQuery = useQuery({
    queryKey: ["admin", "usage", "summary", "30d"],
    queryFn: () => getAdminUsageSummary({ bucket: "day", from_date: daysAgo(29), to_date: today() }),
  });
  const activeQuery = useQuery({
    queryKey: ["admin", "active-users", "week"],
    queryFn: () => getAdminActiveUsers("week"),
  });

  const chartData = useMemo(() =>
    (summaryQuery.data?.daily ?? []).map(d => ({
      date: new Date(d.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
      credits: Number(d.credits_burned).toFixed(4),
      calls: d.call_count,
    })),
    [summaryQuery.data]
  );

  const breakdown = summaryQuery.data?.breakdown ?? [];
  const summary = summaryQuery.data;
  const active = activeQuery.data;

  if (summaryQuery.isLoading) {
    return <div className="flex items-center justify-center p-16 text-muted"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading...</div>;
  }

  return (
    <div className="space-y-8 animate-in fade-in duration-300">
      {/* KPI strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: "Credits Burned (30d)", value: `$${Number(summary?.total_credits_burned ?? 0).toFixed(4)}`, icon: Zap, color: "text-accent" },
          { label: "LLM Calls (30d)", value: (summary?.total_llm_calls ?? 0).toLocaleString(), icon: Activity, color: "text-blue-500" },
          { label: "Active Users (week)", value: active?.active_users?.toLocaleString() ?? "—", icon: Users, color: "text-green-500" },
          { label: "New Users (week)", value: active?.new_users?.toLocaleString() ?? "—", icon: TrendingUp, color: "text-purple-500" },
        ].map(kpi => (
          <div key={kpi.label} className="rounded-2xl border border-border bg-elevated/50 p-4">
            <div className="flex items-center gap-2 mb-2">
              <kpi.icon className={`w-4 h-4 ${kpi.color}`} />
              <span className="text-xs text-muted font-medium">{kpi.label}</span>
            </div>
            <div className="text-2xl font-bold text-foreground font-mono">{kpi.value}</div>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-4">Credits Burned — Last 30 Days</h3>
        {chartData.length > 0 ? (
          <div className="h-[260px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "hsl(var(--muted))" }} dy={8} />
                <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "hsl(var(--muted))" }} width={55} tickFormatter={v => `$${Number(v).toFixed(3)}`} />
                <Tooltip
                  contentStyle={{ backgroundColor: "hsl(var(--surface))", borderRadius: "8px", border: "1px solid hsl(var(--border))" }}
                  formatter={(v: number | undefined) => [`$${Number(v ?? 0).toFixed(4)}`, "Credits"]}
                />
                <Line type="monotone" dataKey="credits" stroke="hsl(var(--accent))" strokeWidth={2.5} dot={false} activeDot={{ r: 5, fill: "hsl(var(--accent))", stroke: "white", strokeWidth: 2 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="h-[260px] flex items-center justify-center rounded-xl border border-dashed border-border text-muted text-sm">No usage data yet.</div>
        )}
      </div>

      {/* Model breakdown */}
      {breakdown.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-foreground mb-4">By Model</h3>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={breakdown.map(b => ({ model: b.model_alias.split("/").pop(), credits: Number(b.credits_burned), calls: b.call_count }))} layout="vertical" margin={{ left: 0, right: 16 }}>
                <XAxis type="number" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "hsl(var(--muted))" }} tickFormatter={v => `$${v}`} />
                <YAxis type="category" dataKey="model" axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: "hsl(var(--muted))" }} width={100} />
                <Tooltip
                  contentStyle={{ backgroundColor: "hsl(var(--surface))", borderRadius: "8px", border: "1px solid hsl(var(--border))" }}
                  formatter={(v: number | undefined) => [`$${Number(v ?? 0).toFixed(4)}`, "Credits"]}
                />
                <Bar dataKey="credits" fill="hsl(var(--accent))" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Users Tab ─────────────────────────────────────────────────────────────────
function UsersTab() {
  const [grantTarget, setGrantTarget] = useState<string | null>(null);
  const [grantAmount, setGrantAmount] = useState("5");
  const [grantNote, setGrantNote] = useState("");
  const queryClient = useQueryClient();

  const today30 = useMemo(() => ({ start: daysAgo(29), end: today() }), []);

  const analyticsQuery = useQuery({
    queryKey: ["admin", "analytics", "usage", today30],
    queryFn: () => getAdminUsageAnalytics({ start_date: today30.start, end_date: today30.end, limit: 100 }),
  });

  // Aggregate by user_id
  const users = useMemo(() => {
    const map = new Map<string, { user_id: string; total_credits: number; total_calls: number; models: Set<string> }>();
    for (const row of (analyticsQuery.data?.rows ?? [])) {
      const existing = map.get(row.user_id);
      if (existing) {
        existing.total_credits += Number(row.total_credits_burned);
        existing.total_calls += row.event_count;
        existing.models.add(row.model_alias.split("/").pop() ?? row.model_alias);
      } else {
        map.set(row.user_id, {
          user_id: row.user_id,
          total_credits: Number(row.total_credits_burned),
          total_calls: row.event_count,
          models: new Set([row.model_alias.split("/").pop() ?? row.model_alias]),
        });
      }
    }
    return [...map.values()].sort((a, b) => b.total_credits - a.total_credits);
  }, [analyticsQuery.data]);

  const grantMutation = useMutation({
    mutationFn: () => grantAdminCredits(grantTarget!, { amount: parseFloat(grantAmount), note: grantNote || undefined }),
    onSuccess: () => {
      setGrantTarget(null);
      setGrantAmount("5");
      setGrantNote("");
      queryClient.invalidateQueries({ queryKey: ["admin"] });
    },
  });

  if (analyticsQuery.isLoading) {
    return <div className="flex items-center justify-center p-16 text-muted"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading...</div>;
  }

  return (
    <div className="animate-in fade-in duration-300 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Active Users — Last 30 Days ({users.length})</h2>
      </div>

      {users.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted">No user activity in this window.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-elevated/50 text-muted sticky top-0">
              <tr>
                <th className="px-5 py-3 font-medium">User ID</th>
                <th className="px-5 py-3 font-medium text-right">Credits (30d)</th>
                <th className="px-5 py-3 font-medium text-right">Calls</th>
                <th className="px-5 py-3 font-medium">Models</th>
                <th className="px-5 py-3 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map(u => (
                <tr key={u.user_id} className="hover:bg-elevated/30 transition-colors">
                  <td className="px-5 py-3 font-mono text-xs text-muted max-w-[160px] truncate" title={u.user_id}>
                    {u.user_id.slice(0, 12)}…
                  </td>
                  <td className="px-5 py-3 text-right font-mono text-foreground">${u.total_credits.toFixed(4)}</td>
                  <td className="px-5 py-3 text-right text-muted">{u.total_calls.toLocaleString()}</td>
                  <td className="px-5 py-3">
                    <div className="flex flex-wrap gap-1">
                      {[...u.models].slice(0, 3).map(m => (
                        <span key={m} className="text-[10px] px-1.5 py-0.5 rounded bg-elevated border border-border text-muted">{m}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-5 py-3 text-right">
                    {grantTarget === u.user_id ? (
                      <div className="flex items-center gap-2 justify-end">
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={grantAmount}
                          onChange={e => setGrantAmount(e.target.value)}
                          className="w-20 h-7 rounded-lg border border-border bg-input px-2 text-xs text-foreground focus:ring-1 focus:ring-accent outline-none"
                        />
                        <input
                          type="text"
                          placeholder="Note…"
                          value={grantNote}
                          onChange={e => setGrantNote(e.target.value)}
                          className="w-24 h-7 rounded-lg border border-border bg-input px-2 text-xs text-foreground focus:ring-1 focus:ring-accent outline-none"
                        />
                        <button
                          onClick={() => grantMutation.mutate()}
                          disabled={grantMutation.isPending || !grantAmount}
                          className="h-7 w-7 flex items-center justify-center rounded-lg bg-success/10 text-success hover:bg-success/20 transition-colors disabled:opacity-50"
                        >
                          {grantMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                        </button>
                        <button onClick={() => setGrantTarget(null)} className="h-7 w-7 flex items-center justify-center rounded-lg bg-elevated hover:bg-elevated/70 text-muted transition-colors">
                          <X className="w-3 h-3" />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setGrantTarget(u.user_id)}
                        className="text-xs px-3 py-1.5 rounded-lg border border-border bg-elevated text-muted hover:text-accent hover:border-accent transition-colors"
                      >
                        + Grant
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {grantMutation.isError && (
        <p className="text-xs text-error">{grantMutation.error instanceof ApiError ? grantMutation.error.detail : "Grant failed."}</p>
      )}
    </div>
  );
}

// ── Pricing Tab ───────────────────────────────────────────────────────────────
function PricingTab() {
  const queryClient = useQueryClient();
  const pricingQuery = useQuery({ queryKey: ["admin", "pricing"], queryFn: getAdminPricing });
  const [editingModel, setEditingModel] = useState<string | null>(null);
  const [editMultiplier, setEditMultiplier] = useState("");

  const updateMutation = useMutation({
    mutationFn: (vars: { model_alias: string; multiplier: number; pricing_version: string }) =>
      updateAdminPricing(vars.model_alias, { multiplier: vars.multiplier, pricing_version: vars.pricing_version }),
    onSuccess: () => {
      setEditingModel(null);
      queryClient.invalidateQueries({ queryKey: ["admin", "pricing"] });
    },
  });

  if (pricingQuery.isLoading) {
    return <div className="flex items-center justify-center p-16 text-muted"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading...</div>;
  }

  const items = pricingQuery.data?.items ?? [];
  const pricingVersion = pricingQuery.data?.pricing_version ?? "";

  return (
    <div className="animate-in fade-in duration-300 space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">Model Pricing</h2>
        <span className="text-xs text-muted font-mono bg-elevated px-2 py-1 rounded-md border border-border">v{pricingVersion}</span>
      </div>

      {items.length === 0 ? (
        <div className="py-12 text-center text-sm text-muted">No pricing data found.</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full text-left text-sm">
            <thead className="bg-elevated/50 text-muted">
              <tr>
                <th className="px-5 py-3 font-medium">Model Alias</th>
                <th className="px-5 py-3 font-medium">Provider</th>
                <th className="px-5 py-3 font-medium text-right">Multiplier</th>
                <th className="px-5 py-3 font-medium text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map(item => {
                const provider = item.model_alias.split("/")[0] ?? "—";
                const model = item.model_alias.split("/").slice(1).join("/") || item.model_alias;
                const isEditing = editingModel === item.model_alias;
                return (
                  <tr key={item.model_alias} className="hover:bg-elevated/30 transition-colors">
                    <td className="px-5 py-3">
                      <div className="font-medium text-foreground text-xs font-mono">{model}</div>
                    </td>
                    <td className="px-5 py-3 text-muted capitalize">{provider}</td>
                    <td className="px-5 py-3 text-right">
                      {isEditing ? (
                        <input
                          type="number"
                          min="0.01"
                          max="100"
                          step="0.01"
                          value={editMultiplier}
                          onChange={e => setEditMultiplier(e.target.value)}
                          className="w-24 h-7 rounded-lg border border-accent bg-input px-2 text-xs text-foreground focus:ring-1 focus:ring-accent outline-none text-right"
                          autoFocus
                        />
                      ) : (
                        <span className="font-mono text-foreground">{Number(item.multiplier).toFixed(2)}×</span>
                      )}
                    </td>
                    <td className="px-5 py-3 text-right">
                      {isEditing ? (
                        <div className="flex items-center gap-1.5 justify-end">
                          <button
                            onClick={() => updateMutation.mutate({ model_alias: item.model_alias, multiplier: parseFloat(editMultiplier), pricing_version: item.pricing_version })}
                            disabled={updateMutation.isPending}
                            className="h-7 w-7 flex items-center justify-center rounded-lg bg-accent/10 text-accent hover:bg-accent/20 transition-colors disabled:opacity-50"
                          >
                            {updateMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Check className="w-3 h-3" />}
                          </button>
                          <button onClick={() => setEditingModel(null)} className="h-7 w-7 flex items-center justify-center rounded-lg bg-elevated text-muted hover:text-foreground transition-colors">
                            <X className="w-3 h-3" />
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => { setEditingModel(item.model_alias); setEditMultiplier(item.multiplier); }}
                          className="h-7 w-7 flex items-center justify-center rounded-lg bg-elevated border border-border text-muted hover:text-accent hover:border-accent transition-colors"
                        >
                          <Pencil className="w-3 h-3" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {updateMutation.isError && (
        <p className="text-xs text-error">{updateMutation.error instanceof ApiError ? updateMutation.error.detail : "Update failed."}</p>
      )}
    </div>
  );
}

// ── Settings Tab ──────────────────────────────────────────────────────────────
function SettingsTab() {
  const queryClient = useQueryClient();
  const settingsQuery = useQuery({ queryKey: ["admin", "settings"], queryFn: getAdminSettings });

  const setEnforcementMutation = useMutation({
    mutationFn: (enabled: boolean) => setAdminEnforcement(enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "settings"] }),
  });

  const clearEnforcementMutation = useMutation({
    mutationFn: () => clearAdminEnforcement(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin", "settings"] }),
  });

  if (settingsQuery.isLoading) {
    return <div className="flex items-center justify-center p-16 text-muted"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading...</div>;
  }

  const s = settingsQuery.data;
  const isMutating = setEnforcementMutation.isPending || clearEnforcementMutation.isPending;

  return (
    <div className="animate-in fade-in duration-300 max-w-lg space-y-6">
      <h2 className="text-sm font-semibold text-foreground">System Settings</h2>

      {/* Credit Enforcement */}
      <div className="rounded-2xl border border-border bg-elevated/30 p-5 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              {s?.enforcement_enabled
                ? <ShieldCheck className="w-4 h-4 text-success" />
                : <ShieldOff className="w-4 h-4 text-error" />}
              <span className="text-sm font-semibold text-foreground">Credit Enforcement</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-elevated border border-border text-muted font-mono">{s?.enforcement_source ?? "—"}</span>
            </div>
            <p className="text-xs text-muted leading-relaxed">
              When enabled, users with insufficient balance are blocked from making LLM calls.
            </p>
          </div>
          <button
            disabled={isMutating}
            onClick={() => setEnforcementMutation.mutate(!s?.enforcement_enabled)}
            className={`relative shrink-0 w-11 h-6 rounded-full transition-colors disabled:opacity-50 ${s?.enforcement_enabled ? "bg-success" : "bg-border"}`}
          >
            <span className={`absolute top-1 w-4 h-4 rounded-full bg-white shadow transition-all ${s?.enforcement_enabled ? "left-6" : "left-1"}`} />
          </button>
        </div>

        <button
          disabled={isMutating}
          onClick={() => clearEnforcementMutation.mutate()}
          className="flex items-center gap-1.5 text-xs text-muted hover:text-foreground transition-colors"
        >
          <RotateCcw className="w-3 h-3" />
          Reset to config default
        </button>
      </div>

      {/* Low balance threshold */}
      <div className="rounded-2xl border border-border bg-elevated/30 p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-foreground mb-1">Low Balance Threshold</div>
            <div className="text-xs text-muted">Users below this balance will receive a low-balance warning.</div>
          </div>
          <span className="font-mono text-lg font-bold text-foreground">${s?.low_balance_threshold?.toFixed(2) ?? "—"}</span>
        </div>
      </div>

      {/* Pricing version */}
      <div className="rounded-2xl border border-border bg-elevated/30 p-5">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-semibold text-foreground mb-1">Active Pricing Version</div>
            <div className="text-xs text-muted">Adjust multipliers in the Pricing tab.</div>
          </div>
          <span className="font-mono text-sm font-bold text-foreground px-2 py-1 bg-elevated border border-border rounded-md">{s?.pricing_version ?? "—"}</span>
        </div>
      </div>

      {(setEnforcementMutation.isSuccess || clearEnforcementMutation.isSuccess) && (
        <div className="flex items-center gap-2 text-xs text-success">
          <CheckCircle2 className="w-4 h-4" /> Settings updated.
        </div>
      )}
      {(setEnforcementMutation.isError || clearEnforcementMutation.isError) && (
        <p className="text-xs text-error">Failed to update settings.</p>
      )}
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function AdminDashboardPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState("usage");

  const accessQuery = useQuery({
    queryKey: ["admin", "settings"],
    queryFn: getAdminSettings,
    retry: false,
    staleTime: 60_000,
  });

  useEffect(() => {
    if (accessQuery.isError) {
      router.replace("/rooms");
    }
  }, [accessQuery.isError, router]);

  if (accessQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center text-muted">
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        Checking access…
      </div>
    );
  }

  if (accessQuery.isError) {
    return null;
  }

  return (
    <div className="flex h-full flex-col bg-background overflow-y-auto">
      <div className="mx-auto w-full max-w-6xl px-6 py-8">
        <header className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-xl bg-accent/10 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-accent" />
            </div>
            <h1 className="text-2xl font-bold text-foreground tracking-tight">Admin Console</h1>
          </div>
          <p className="text-sm text-muted">Platform usage, billing enforcement, model pricing, and credit management.</p>
        </header>

        {/* Tab bar */}
        <div className="mb-6 flex gap-1 border-b border-border pb-px">
          {TABS.map(tab => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 -mb-px ${active
                  ? "border-accent text-accent"
                  : "border-transparent text-muted hover:text-foreground"
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Content */}
        <div className="rounded-2xl border border-border bg-white dark:bg-surface p-6 shadow-sm min-h-[400px]">
          {activeTab === "usage" && <UsageTab />}
          {activeTab === "users" && <UsersTab />}
          {activeTab === "pricing" && <PricingTab />}
          {activeTab === "settings" && <SettingsTab />}
        </div>
      </div>
    </div>
  );
}
