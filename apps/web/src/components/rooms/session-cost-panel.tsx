"use client";

import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, Zap, Layers, AlignLeft, TrendingUp, Loader2 } from "lucide-react";
import { ApiError } from "@/lib/api/client";
import { getSessionAnalytics, type SessionAnalyticsRead, type TurnCostRead, type ModelCostRead } from "@/lib/api/sessions";
import { debugError, debugLog } from "@/lib/debug";

type Props = {
  sessionId: string;
  onClose: () => void;
};

const CREDITS_PER_USD = 1 / 0.03;

function creditsToUsd(credits: string): string {
  return (Number(credits) / CREDITS_PER_USD).toFixed(6);
}

function fmtN(n: number): string {
  return n.toLocaleString();
}

function StatRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between text-sm py-1.5 border-b border-border last:border-0">
      <span className="text-muted">{label}</span>
      <span className="font-mono font-semibold text-foreground">{value}</span>
    </div>
  );
}

function ModelRow({ row }: { row: ModelCostRead }) {
  const total = row.input_tokens_fresh + row.input_tokens_cached + row.output_tokens;
  return (
    <div className="rounded-xl border border-border bg-elevated/50 p-3 space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-foreground">{row.model_alias}</span>
        <span className="text-sm font-mono font-bold text-accent">{Number(row.credits_burned).toFixed(4)} cr</span>
      </div>
      <div className="grid grid-cols-3 gap-1 text-xs text-muted">
        <span>{fmtN(row.input_tokens_fresh)} fresh</span>
        <span>{fmtN(row.input_tokens_cached)} cached</span>
        <span>{fmtN(row.output_tokens)} out</span>
      </div>
      <div className="text-xs text-muted">
        {fmtN(total)} total tokens &middot; {row.llm_call_count} call{row.llm_call_count !== 1 ? "s" : ""}
      </div>
    </div>
  );
}

function TurnRow({ row, isHighest }: { row: TurnCostRead; isHighest: boolean }) {
  return (
    <div className={`rounded-xl border p-3 space-y-1 ${isHighest ? "border-amber-400/50 bg-amber-50/50 dark:bg-amber-900/10" : "border-border bg-elevated/50"}`}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-muted font-mono shrink-0">
          Turn {row.turn_index ?? "?"}
          {isHighest && <span className="ml-1 text-amber-600 font-bold"> ★</span>}
        </span>
        <span className="text-sm font-mono font-bold text-accent shrink-0">{Number(row.credits_burned).toFixed(4)} cr</span>
      </div>
      {row.user_input_preview && (
        <p className="text-xs text-muted truncate">{row.user_input_preview}</p>
      )}
      <div className="text-xs text-muted">
        {fmtN(row.total_tokens)} tokens &middot; {row.llm_call_count} call{row.llm_call_count !== 1 ? "s" : ""}
      </div>
    </div>
  );
}

function AnalyticsContent({ data }: { data: SessionAnalyticsRead }) {
  const totalCredits = Number(data.total_credits_burned);
  const dollarEquiv = (totalCredits / CREDITS_PER_USD).toFixed(4);
  const totalInput = data.total_input_tokens_fresh + data.total_input_tokens_cached;

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-5">
      {/* Summary totals */}
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Zap className="h-4 w-4 text-accent" />
          <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">Session Total</h3>
        </div>
        <div className="rounded-xl border border-border bg-accent/5 p-4 mb-3">
          <div className="text-3xl font-bold text-accent font-mono">
            {totalCredits.toFixed(4)} cr
          </div>
          <div className="text-sm text-muted mt-0.5">&asymp; ${dollarEquiv} USD</div>
        </div>
        <div className="space-y-0">
          <StatRow label="LLM calls" value={String(data.llm_call_count)} />
          <StatRow label="Fresh input tokens" value={fmtN(data.total_input_tokens_fresh)} />
          <StatRow label="Cached input tokens" value={fmtN(data.total_input_tokens_cached)} />
          <StatRow label="Output tokens" value={fmtN(data.total_output_tokens)} />
          <StatRow label="Total input tokens" value={fmtN(totalInput)} />
          <StatRow label="Total tokens" value={fmtN(data.total_tokens)} />
        </div>
      </section>

      {/* Highest cost turn */}
      {data.highest_cost_turn && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="h-4 w-4 text-amber-500" />
            <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">Highest Cost Turn</h3>
          </div>
          <TurnRow row={data.highest_cost_turn} isHighest={false} />
        </section>
      )}

      {/* By model */}
      {data.by_model.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <Layers className="h-4 w-4 text-muted" />
            <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">By Model</h3>
          </div>
          <div className="space-y-2">
            {data.by_model.map(row => (
              <ModelRow key={row.model_alias} row={row} />
            ))}
          </div>
        </section>
      )}

      {/* By turn */}
      {data.by_turn.length > 0 && (
        <section>
          <div className="flex items-center gap-2 mb-3">
            <AlignLeft className="h-4 w-4 text-muted" />
            <h3 className="text-sm font-bold text-foreground uppercase tracking-wide">Cost Per Turn</h3>
          </div>
          <div className="space-y-2">
            {data.by_turn.map((row, i) => (
              <TurnRow
                key={row.turn_id ?? i}
                row={row}
                isHighest={data.highest_cost_turn?.turn_id === row.turn_id && row.turn_id !== null}
              />
            ))}
          </div>
        </section>
      )}

      {data.llm_call_count === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center gap-2">
          <Zap className="h-8 w-8 text-muted/40" />
          <p className="text-sm text-muted">No LLM calls recorded yet for this session.</p>
        </div>
      )}
    </div>
  );
}

export function SessionCostPanel({ sessionId, onClose }: Props) {
  const analyticsQuery = useQuery({
    queryKey: ["sessionAnalytics", sessionId],
    queryFn: () => getSessionAnalytics(sessionId),
    staleTime: 10_000,
  });

  useEffect(() => {
    debugLog("session-cost", "load_start", { sessionId });
  }, [sessionId]);

  useEffect(() => {
    if (!analyticsQuery.data) {
      return;
    }
    debugLog("session-cost", "load_success", {
      sessionId,
      llmCallCount: analyticsQuery.data.llm_call_count,
      totalCredits: analyticsQuery.data.total_credits_burned,
    });
  }, [analyticsQuery.data, sessionId]);

  useEffect(() => {
    if (!analyticsQuery.isError) {
      return;
    }
    debugError("session-cost", "load_failed", {
      sessionId,
      error: analyticsQuery.error,
    });
  }, [analyticsQuery.error, analyticsQuery.isError, sessionId]);

  const analyticsError =
    analyticsQuery.error instanceof ApiError
      ? analyticsQuery.error.detail
      : "Failed to load analytics. The session may have no recorded calls yet.";

  return (
    <div className="fixed inset-0 z-50 flex items-stretch justify-end">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/40 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative flex flex-col w-full max-w-sm bg-white dark:bg-surface border-l border-border shadow-2xl h-full overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-border bg-elevated/30 shrink-0">
          <div className="flex items-center gap-2">
            <Zap className="h-5 w-5 text-accent" />
            <h2 className="text-base font-bold text-foreground">Session Cost</h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-full flex items-center justify-center text-muted hover:text-foreground hover:bg-elevated transition-colors"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {analyticsQuery.isLoading && (
          <div className="flex-1 flex items-center justify-center">
            <Loader2 className="h-6 w-6 animate-spin text-muted" />
          </div>
        )}

        {analyticsQuery.isError && (
          <div className="flex-1 flex items-center justify-center p-6 text-center">
            <p className="text-sm text-error">{analyticsError}</p>
          </div>
        )}

        {analyticsQuery.data && <AnalyticsContent data={analyticsQuery.data} />}
      </div>
    </div>
  );
}
