"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Modal } from "@/components/common/modal";
import { Button } from "@/components/ui/button";
import { createAgent, deleteAgent, listAgents, type AgentRead } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";

type CreateAgentFormState = {
  name: string;
  modelAlias: string;
  rolePrompt: string;
  toolPermissions: string[];
};

const AVAILABLE_MODELS: Array<{ value: string; label: string }> = [
  { value: "deepseek", label: "DeepSeek" },
  { value: "qwen", label: "Qwen" },
  { value: "llama", label: "Llama" },
  { value: "free", label: "Free" },
  { value: "gpt_oss", label: "GPT OSS" },
  { value: "premium", label: "Premium" }
];

const AVAILABLE_TOOLS: Array<{ value: string; label: string; description: string }> = [
  { value: "search", label: "Web Search", description: "Allow this agent to use Tavily web search." },
  { value: "file_read", label: "File Read", description: "Allow this agent to read uploaded files in room scope." }
];

function slugify(value: string): string {
  const base = value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
  return (base || "agent").slice(0, 40);
}

function buildAgentKey(name: string): string {
  const base = slugify(name);
  const suffix =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID().replace(/-/g, "").slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `${base}-${suffix}`.slice(0, 64);
}

function formatDate(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) {
    return "-";
  }
  return parsed.toLocaleDateString();
}

export default function AgentsPage() {
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<AgentRead | null>(null);
  const [formError, setFormError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [form, setForm] = useState<CreateAgentFormState>({
    name: "",
    modelAlias: "deepseek",
    rolePrompt: "",
    toolPermissions: []
  });

  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: listAgents
  });

  const agents = useMemo(() => agentsQuery.data?.agents || [], [agentsQuery.data]);

  const createAgentMutation = useMutation({
    mutationFn: async () => {
      const trimmedName = form.name.trim();
      const trimmedModel = form.modelAlias.trim();
      if (!trimmedName) {
        throw new ApiError(422, "Agent name is required.");
      }
      if (!trimmedModel) {
        throw new ApiError(422, "Model is required.");
      }
      return createAgent({
        agent_key: buildAgentKey(trimmedName),
        name: trimmedName,
        model_alias: trimmedModel,
        role_prompt: form.rolePrompt.trim(),
        tool_permissions: form.toolPermissions
      });
    },
    onMutate: async () => {
      setFormError("");
      setActionMessage("");
      await queryClient.cancelQueries({ queryKey: ["agents"] });
      const previous = queryClient.getQueryData<{ agents: AgentRead[]; total: number }>(["agents"]);
      const optimistic: AgentRead = {
        id: `temp-${Date.now()}`,
        owner_user_id: "me",
        agent_key: `${slugify(form.name)}-pending`,
        name: form.name || "Untitled Agent",
        model_alias: form.modelAlias || "deepseek",
        role_prompt: form.rolePrompt,
        tool_permissions: form.toolPermissions,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      queryClient.setQueryData(["agents"], {
        agents: [optimistic, ...(previous?.agents || [])],
        total: (previous?.total || 0) + 1
      });
      return { previous };
    },
    onError: (error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["agents"], context.previous);
      }
      setFormError(error instanceof ApiError ? error.detail : error instanceof Error ? error.message : "Failed to create agent.");
    },
    onSuccess: () => {
      setCreateOpen(false);
      setForm({ name: "", modelAlias: "deepseek", rolePrompt: "", toolPermissions: [] });
      setActionMessage("Agent created successfully.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    }
  });

  const deleteAgentMutation = useMutation({
    mutationFn: (agentId: string) => deleteAgent(agentId),
    onMutate: async (agentId) => {
      setActionMessage("");
      await queryClient.cancelQueries({ queryKey: ["agents"] });
      const previous = queryClient.getQueryData<{ agents: AgentRead[]; total: number }>(["agents"]);
      queryClient.setQueryData(["agents"], {
        agents: (previous?.agents || []).filter((agent) => agent.id !== agentId),
        total: Math.max((previous?.total || 1) - 1, 0)
      });
      return { previous };
    },
    onError: (error, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(["agents"], context.previous);
      }
      setActionMessage(error instanceof ApiError ? error.detail : error instanceof Error ? error.message : "Failed to delete agent.");
    },
    onSuccess: () => {
      setDeleteTarget(null);
      setActionMessage("Agent deleted.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    }
  });

  return (
    <section className="rounded-xl border border-[--border] bg-[--bg-surface] p-5">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Agents</h1>
          <p className="mt-1 text-sm text-[--text-muted]">Manage reusable agents.</p>
        </div>
        <Button type="button" onClick={() => setCreateOpen(true)}>
          Create Agent
        </Button>
      </div>

      {actionMessage ? <p className="mb-3 text-sm text-[--text-muted]">{actionMessage}</p> : null}
      {agentsQuery.isError ? (
        <p className="mb-3 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
          {agentsQuery.error instanceof ApiError
            ? agentsQuery.error.detail
            : agentsQuery.error instanceof Error
              ? agentsQuery.error.message
              : "Failed to load agents."}
        </p>
      ) : null}

      {agentsQuery.isLoading ? <p className="text-sm text-[--text-muted]">Loading agents...</p> : null}

      {!agentsQuery.isLoading && agents.length === 0 ? (
        <div className="rounded-md border border-dashed border-[--border] p-6 text-center text-sm text-[--text-muted]">
          No agents yet. Create your first agent.
        </div>
      ) : null}

      {agents.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2">
          {agents.map((agent) => (
            <article key={agent.id} className="rounded-lg border border-[--border] bg-[--bg-base] p-4">
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-lg font-semibold">{agent.name}</h2>
                <span className="rounded-md bg-[--accent]/20 px-2 py-1 text-xs font-medium">{agent.model_alias}</span>
              </div>
              <p className="mt-2 text-xs text-[--text-muted]">Provider: OpenRouter</p>
              <p className="mt-1 text-xs text-[--text-muted]">
                Tools: {agent.tool_permissions.length > 0 ? agent.tool_permissions.join(", ") : "none"}
              </p>
              <p className="mt-1 text-xs text-[--text-muted]">Created: {formatDate(agent.created_at)}</p>
              <div className="mt-4 flex justify-end">
                <Button type="button" variant="ghost" onClick={() => setDeleteTarget(agent)}>
                  Delete
                </Button>
              </div>
            </article>
          ))}
        </div>
      ) : null}

      <Modal open={createOpen} title="Create agent" onClose={() => setCreateOpen(false)}>
        <form
          className="grid gap-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (createAgentMutation.isPending) {
              return;
            }
            createAgentMutation.mutate();
          }}
        >
          <label className="grid gap-1 text-sm">
            <span className="text-[--text-muted]">Name</span>
            <input
              className="h-10 rounded-md border border-[--border] bg-[--bg-base] px-3 text-[--text-primary]"
              value={form.name}
              onChange={(event) => setForm((prev) => ({ ...prev, name: event.target.value }))}
              placeholder="Researcher"
            />
          </label>

          <label className="grid gap-1 text-sm">
            <span className="text-[--text-muted]">Model</span>
            <select
              className="h-10 rounded-md border border-[--border] bg-[--bg-base] px-3 text-[--text-primary]"
              value={form.modelAlias}
              onChange={(event) => setForm((prev) => ({ ...prev, modelAlias: event.target.value }))}
            >
              {AVAILABLE_MODELS.map((model) => (
                <option key={model.value} value={model.value}>
                  {model.label}
                </option>
              ))}
            </select>
          </label>

          <label className="grid gap-1 text-sm">
            <span className="text-[--text-muted]">System prompt</span>
            <textarea
              className="min-h-28 rounded-md border border-[--border] bg-[--bg-base] px-3 py-2 text-[--text-primary]"
              value={form.rolePrompt}
              onChange={(event) => setForm((prev) => ({ ...prev, rolePrompt: event.target.value }))}
              placeholder="You are a careful research assistant..."
            />
          </label>

          <fieldset className="grid gap-2 rounded-md border border-[--border] bg-[--bg-base] p-3">
            <legend className="px-1 text-sm text-[--text-muted]">Tools</legend>
            {AVAILABLE_TOOLS.map((tool) => {
              const checked = form.toolPermissions.includes(tool.value);
              return (
                <label key={tool.value} className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="mt-1"
                    checked={checked}
                    onChange={(event) => {
                      setForm((prev) => {
                        if (event.target.checked) {
                          return { ...prev, toolPermissions: [...prev.toolPermissions, tool.value] };
                        }
                        return { ...prev, toolPermissions: prev.toolPermissions.filter((value) => value !== tool.value) };
                      });
                    }}
                  />
                  <span>
                    <span className="font-medium">{tool.label}</span>
                    <span className="block text-xs text-[--text-muted]">{tool.description}</span>
                  </span>
                </label>
              );
            })}
          </fieldset>

          {formError ? <p className="text-sm text-red-300">{formError}</p> : null}

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setCreateOpen(false)} disabled={createAgentMutation.isPending}>
              Cancel
            </Button>
            <Button type="submit" disabled={createAgentMutation.isPending}>
              {createAgentMutation.isPending ? "Creating..." : "Create"}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete agent"
        description={`Delete '${deleteTarget?.name || "this agent"}'? This action cannot be undone.`}
        confirmLabel="Delete"
        loading={deleteAgentMutation.isPending}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteAgentMutation.mutate(deleteTarget.id);
          }
        }}
      />
    </section>
  );
}
