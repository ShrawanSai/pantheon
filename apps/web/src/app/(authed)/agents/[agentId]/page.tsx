"use client";

import { useState, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { ArrowLeft, MessageSquare, Save, Loader2, Zap, Brain, Search, FileText, Check } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { listAgents, updateAgent, createAgentSession, type AgentRead } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";

type AgentDetailPageProps = {
  params: { agentId: string };
};

const MODEL_OPTIONS: Array<{ value: string; label: string; description: string; badge?: string; supportsTools: boolean }> = [
  { value: "gemini-flash", label: "Gemini 2.5 Flash", description: "Google's fast, capable model. Great for most tasks.", badge: "Popular", supportsTools: true },
  { value: "gemini-pro", label: "Gemini 2.5 Pro", description: "Google's most powerful model. Best for complex reasoning.", badge: "Best", supportsTools: true },
  { value: "deepseek", label: "DeepSeek V3", description: "DeepSeek's latest chat model. Strong at coding and reasoning.", supportsTools: true },
  { value: "qwen3", label: "Qwen3 235B", description: "Multilingual, great for analysis tasks.", supportsTools: true },
  { value: "llama-4-scout", label: "Llama 4 Scout", description: "Meta's open-source scout model. Fast responses.", supportsTools: true },
  { value: "gpt-oss", label: "GPT OSS 120B", description: "OpenAI-compatible open-source model. Strong at instruction following.", supportsTools: true },
  { value: "mistral-small", label: "Mistral Small", description: "Lightweight free-tier model. Good for simple tasks. Does not support tools.", supportsTools: false },
];

const TOOL_OPTIONS: Array<{ value: string; label: string; description: string; icon: React.ReactNode }> = [
  { value: "search", label: "Web Search", description: "Search the web in real-time using Tavily.", icon: <Search className="w-4 h-4" /> },
  { value: "file_read", label: "File Read", description: "Read uploaded files from the room context.", icon: <FileText className="w-4 h-4" /> },
];

function agentHue(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return Math.abs(hash) % 360;
}

function initials(name: string): string {
  return name.split(/\s+/).map(w => w[0] ?? "").join("").toUpperCase().slice(0, 2);
}

export default function AgentDetailPage({ params }: AgentDetailPageProps) {
  const { agentId } = params;
  const router = useRouter();
  const queryClient = useQueryClient();

  const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: listAgents });
  const agent = agentsQuery.data?.agents?.find((a: AgentRead) => a.id === agentId) ?? null;

  const [name, setName] = useState("");
  const [modelAlias, setModelAlias] = useState("gemini-flash");
  const [rolePrompt, setRolePrompt] = useState("");
  const [toolPermissions, setToolPermissions] = useState<string[]>([]);
  const [savedMessage, setSavedMessage] = useState("");
  const [formError, setFormError] = useState("");

  // Populate form once agent loads
  useEffect(() => {
    if (agent) {
      setName(agent.name);
      setModelAlias(agent.model_alias);
      setRolePrompt(agent.role_prompt || "");
      setToolPermissions([...agent.tool_permissions]);
    }
  }, [agent]);

  const selectedModelOption = MODEL_OPTIONS.find(m => m.value === modelAlias);
  const modelSupportsTools = selectedModelOption?.supportsTools ?? true;

  // Clear tool permissions when switching to a model that doesn't support tools
  useEffect(() => {
    if (!modelSupportsTools) {
      setToolPermissions([]);
    }
  }, [modelAlias, modelSupportsTools]);

  const saveMutation = useMutation({
    mutationFn: () => {
      const trimmed = name.trim();
      if (!trimmed) throw new ApiError(422, "Agent name is required.");
      return updateAgent(agentId, {
        name: trimmed,
        model_alias: modelAlias,
        role_prompt: rolePrompt.trim(),
        tool_permissions: toolPermissions,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
      setSavedMessage("Changes saved.");
      setFormError("");
      setTimeout(() => setSavedMessage(""), 3000);
    },
    onError: err => {
      setFormError(err instanceof ApiError ? err.detail : err instanceof Error ? err.message : "Failed to save.");
    },
  });

  async function handleChat() {
    try {
      const session = await createAgentSession(agentId);
      router.push(`/agents/${agentId}/chat?session=${session.id}`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.detail : "Failed to start session.");
    }
  }

  function toggleTool(tool: string) {
    setToolPermissions(prev =>
      prev.includes(tool) ? prev.filter(t => t !== tool) : [...prev, tool]
    );
  }

  if (agentsQuery.isLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-background">
        <Loader2 className="w-6 h-6 animate-spin text-accent" />
      </div>
    );
  }

  if (!agent && !agentsQuery.isLoading) {
    return (
      <div className="flex h-full flex-col items-center justify-center bg-background gap-4">
        <p className="text-muted">Agent not found.</p>
        <Link href="/agents" className="text-accent text-sm hover:underline">← Back to Agents</Link>
      </div>
    );
  }

  const hue = agentHue(name || agent?.name || "");

  return (
    <div className="flex h-full flex-col bg-background overflow-y-auto">
      {/* Header */}
      <header className="sticky top-0 z-10 bg-background/80 backdrop-blur-md border-b border-border px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Link
            href="/agents"
            className="flex h-9 w-9 items-center justify-center rounded-full text-muted hover:bg-elevated hover:text-foreground transition-colors"
          >
            <ArrowLeft className="w-5 h-5" />
          </Link>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted">Agent Config</p>
            <h1 className="text-lg font-bold text-foreground leading-tight">{agent?.name}</h1>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            onClick={handleChat}
            className="flex items-center gap-2 rounded-full px-4 h-9 text-sm border border-border hover:border-accent hover:text-accent"
          >
            <MessageSquare className="w-4 h-4" />
            Chat
          </Button>
          <Button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="flex items-center gap-2 rounded-full px-5 h-9 text-sm bg-accent hover:bg-accent-hover text-white"
          >
            {saveMutation.isPending ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : savedMessage ? (
              <Check className="w-4 h-4" />
            ) : (
              <Save className="w-4 h-4" />
            )}
            {saveMutation.isPending ? "Saving…" : savedMessage ? "Saved!" : "Save"}
          </Button>
        </div>
      </header>

      <div className="mx-auto w-full max-w-2xl px-6 py-8 space-y-8">
        {formError && (
          <div className="p-3 bg-error/10 border border-error/20 rounded-xl text-sm text-error">{formError}</div>
        )}

        {/* Identity card */}
        <section className="bg-white dark:bg-surface rounded-2xl border border-border p-6 shadow-sm">
          <div className="flex items-center gap-4 mb-6">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center text-white text-xl font-bold shadow-md"
              style={{ background: `hsl(${hue},55%,50%)` }}
            >
              {initials(name || agent?.name || "AI")}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-bold uppercase tracking-widest text-muted mb-1">Identity</p>
              <input
                className="w-full bg-transparent text-xl font-bold text-foreground outline-none border-b-2 border-transparent focus:border-accent transition-colors pb-1 placeholder:text-muted"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="Agent Name"
              />
            </div>
          </div>
        </section>

        {/* System Prompt */}
        <section className="bg-white dark:bg-surface rounded-2xl border border-border p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Brain className="w-5 h-5 text-accent" />
            <h2 className="text-base font-bold text-foreground">System Prompt</h2>
          </div>
          <p className="text-sm text-muted mb-3">Define this agent's persona, expertise, and instructions.</p>
          <textarea
            className="w-full min-h-[160px] bg-elevated/50 border border-border rounded-xl p-4 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent transition-all resize-none"
            value={rolePrompt}
            onChange={e => setRolePrompt(e.target.value)}
            placeholder="You are a careful research assistant. You provide well-sourced, nuanced answers and always cite your reasoning…"
          />
          <p className="text-xs text-muted mt-2">{rolePrompt.length} characters</p>
        </section>

        {/* Model Selection */}
        <section className="bg-white dark:bg-surface rounded-2xl border border-border p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Zap className="w-5 h-5 text-accent" />
            <h2 className="text-base font-bold text-foreground">Model</h2>
          </div>
          <div className="grid grid-cols-1 gap-2">
            {MODEL_OPTIONS.map(opt => {
              const selected = modelAlias === opt.value;
              return (
                <button
                  key={opt.value}
                  onClick={() => setModelAlias(opt.value)}
                  className={`flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all ${selected
                    ? "border-accent bg-accent/5"
                    : "border-border hover:border-border-focus bg-elevated/30"
                    }`}
                >
                  <div className={`w-5 h-5 rounded-full border-2 flex items-center justify-center shrink-0 transition-colors ${selected ? "border-accent bg-accent" : "border-border"}`}>
                    {selected && <div className="w-2 h-2 rounded-full bg-white" />}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className={`text-sm font-bold ${selected ? "text-accent" : "text-foreground"}`}>{opt.label}</span>
                      {opt.badge && (
                        <span className="text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-accent/10 text-accent uppercase tracking-wide">
                          {opt.badge}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-muted mt-0.5">{opt.description}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        {/* Tools */}
        <section className="bg-white dark:bg-surface rounded-2xl border border-border p-6 shadow-sm">
          <div className="flex items-center gap-2 mb-4">
            <Search className="w-5 h-5 text-accent" />
            <h2 className="text-base font-bold text-foreground">Tools</h2>
          </div>
          <p className="text-sm text-muted mb-4">Enable capabilities this agent can use during conversations.</p>
          {!modelSupportsTools ? (
            <div className="p-4 bg-elevated rounded-xl border border-border text-sm text-muted">
              <span className="font-semibold text-foreground">{selectedModelOption?.label}</span> does not support tool calling. Select a different model to enable tools.
            </div>
          ) : (
            <div className="space-y-3">
              {TOOL_OPTIONS.map(tool => {
                const enabled = toolPermissions.includes(tool.value);
                return (
                  <button
                    key={tool.value}
                    onClick={() => toggleTool(tool.value)}
                    className={`w-full flex items-center gap-4 p-4 rounded-xl border-2 text-left transition-all ${enabled
                      ? "border-accent bg-accent/5"
                      : "border-border hover:border-border-focus"
                      }`}
                  >
                    <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 transition-colors ${enabled ? "bg-accent text-white" : "bg-elevated text-muted"}`}>
                      {tool.icon}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm font-bold ${enabled ? "text-accent" : "text-foreground"}`}>{tool.label}</p>
                      <p className="text-xs text-muted">{tool.description}</p>
                    </div>
                    <div className={`w-10 h-6 rounded-full border-2 flex items-center transition-all shrink-0 ${enabled ? "bg-accent border-accent" : "bg-elevated border-border"}`}>
                      <div className={`w-4 h-4 rounded-full bg-white shadow-sm transition-transform mx-0.5 ${enabled ? "translate-x-4" : "translate-x-0"}`} />
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </section>

        {/* Metadata */}
        <section className="bg-elevated/30 rounded-2xl border border-border p-4">
          <div className="grid grid-cols-2 gap-4 text-xs text-muted">
            <div>
              <p className="font-bold uppercase tracking-widest mb-1">Agent ID</p>
              <p className="font-mono text-foreground/60 truncate">{agentId}</p>
            </div>
            <div>
              <p className="font-bold uppercase tracking-widest mb-1">Created</p>
              <p className="text-foreground/60">{agent?.created_at ? new Date(agent.created_at).toLocaleDateString() : "—"}</p>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
