"use client";

import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { MessageSquare } from "lucide-react";

import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { Modal } from "@/components/common/modal";
import { Button } from "@/components/ui/button";
import { createAgent, createAgentSession, deleteAgent, listAgents, updateAgent, type AgentRead } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";

type AgentFormState = {
  name: string;
  modelAlias: string;
  rolePrompt: string;
  toolPermissions: string[];
};

const EMPTY_FORM: AgentFormState = {
  name: "",
  modelAlias: "deepseek",
  rolePrompt: "",
  toolPermissions: []
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
  const router = useRouter();

  // Modal state
  const [modalOpen, setModalOpen] = useState(false);
  const [editingAgent, setEditingAgent] = useState<AgentRead | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AgentRead | null>(null);
  const [formError, setFormError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [form, setForm] = useState<AgentFormState>(EMPTY_FORM);

  const isEditing = editingAgent !== null;
  const modalTitle = isEditing ? `Edit ${editingAgent.name}` : "Create agent";

  const agentsQuery = useQuery({
    queryKey: ["agents"],
    queryFn: listAgents
  });

  const agents = useMemo(() => agentsQuery.data?.agents || [], [agentsQuery.data]);

  // --- Open modal for create ---
  function openCreateModal() {
    setEditingAgent(null);
    setForm(EMPTY_FORM);
    setFormError("");
    setModalOpen(true);
  }

  // --- Open modal for edit ---
  function openEditModal(agent: AgentRead) {
    setEditingAgent(agent);
    setForm({
      name: agent.name,
      modelAlias: agent.model_alias,
      rolePrompt: agent.role_prompt || "",
      toolPermissions: [...agent.tool_permissions]
    });
    setFormError("");
    setModalOpen(true);
  }

  // --- Create mutation ---
  const createMutation = useMutation({
    mutationFn: async () => {
      const trimmedName = form.name.trim();
      if (!trimmedName) throw new ApiError(422, "Agent name is required.");
      return createAgent({
        agent_key: buildAgentKey(trimmedName),
        name: trimmedName,
        model_alias: form.modelAlias.trim(),
        role_prompt: form.rolePrompt.trim(),
        tool_permissions: form.toolPermissions
      });
    },
    onError: (error) => {
      setFormError(error instanceof ApiError ? error.detail : error instanceof Error ? error.message : "Failed to create agent.");
    },
    onSuccess: () => {
      setModalOpen(false);
      setForm(EMPTY_FORM);
      setActionMessage("Agent created successfully.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    }
  });

  // --- Update mutation ---
  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!editingAgent) throw new Error("No agent selected for editing.");
      const trimmedName = form.name.trim();
      if (!trimmedName) throw new ApiError(422, "Agent name is required.");
      return updateAgent(editingAgent.id, {
        name: trimmedName,
        model_alias: form.modelAlias.trim(),
        role_prompt: form.rolePrompt.trim(),
        tool_permissions: form.toolPermissions
      });
    },
    onError: (error) => {
      setFormError(error instanceof ApiError ? error.detail : error instanceof Error ? error.message : "Failed to update agent.");
    },
    onSuccess: () => {
      setModalOpen(false);
      setEditingAgent(null);
      setForm(EMPTY_FORM);
      setActionMessage("Agent updated successfully.");
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["agents"] });
    }
  });

  // --- Delete mutation ---
  const deleteMutation = useMutation({
    mutationFn: (agentId: string) => deleteAgent(agentId),
    onError: (error) => {
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

  // --- Start chat with agent ---
  async function handleChatWithAgent(agent: AgentRead) {
    try {
      const session = await createAgentSession(agent.id);
      router.push(`/agents/${agent.id}/chat?session=${session.id}`);
    } catch (error) {
      setActionMessage(error instanceof ApiError ? error.detail : "Failed to start agent session.");
    }
  }

  // --- Form submit handler ---
  function handleFormSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (isEditing) {
      if (!updateMutation.isPending) updateMutation.mutate();
    } else {
      if (!createMutation.isPending) createMutation.mutate();
    }
  }

  const isSaving = createMutation.isPending || updateMutation.isPending;

  return (
    <div className="flex h-full flex-col bg-background p-6">
      <div className="mx-auto w-full max-w-6xl">
        <header className="mb-8 flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="text-[24px] font-bold text-foreground tracking-tight">Agents</h1>
            <p className="mt-1 text-sm text-muted">Manage your custom council members.</p>
          </div>
          <Button onClick={openCreateModal} className="rounded-full bg-accent hover:bg-accent-hover text-white px-6 h-10 transition-colors shadow-sm">
            Create Agent
          </Button>
        </header>

        {actionMessage && <p className="mb-4 text-sm text-success">{actionMessage}</p>}
        {agentsQuery.isError && (
          <p className="mb-4 rounded-md bg-error/10 p-4 text-sm text-error border border-error/20">
            {agentsQuery.error instanceof ApiError ? agentsQuery.error.detail : agentsQuery.error instanceof Error ? agentsQuery.error.message : "Failed to load agents."}
          </p>
        )}

        {agentsQuery.isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3].map(i => (
              <div key={i} className="h-48 rounded-xl bg-surface animate-pulse" />
            ))}
          </div>
        ) : null}

        {!agentsQuery.isLoading && agents.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed border-border bg-surface py-24 text-center">
            <h3 className="text-lg font-semibold text-foreground mb-2">No agents yet</h3>
            <p className="text-sm text-muted max-w-sm mb-6">Create specialized agents to provide different perspectives in your council.</p>
            <Button onClick={openCreateModal} className="rounded-full bg-accent hover:bg-accent-hover text-white">Create your first agent</Button>
          </div>
        ) : null}

        {agents.length > 0 ? (
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2 lg:grid-cols-3">
            {agents.map((agent) => (
              <article key={agent.id} className="group flex flex-col justify-between rounded-xl bg-white dark:bg-surface border border-border p-5 shadow-[0_2px_10px_rgb(0,0,0,0.02)] transition-all hover:shadow-[0_8px_30px_rgb(0,0,0,0.06)] hover:border-borderFocus">
                <div>
                  <div className="mb-3 flex items-start justify-between gap-2">
                    <h2 className="text-lg font-bold text-foreground leading-tight">{agent.name}</h2>
                    <span className="shrink-0 rounded-full bg-elevated px-2.5 py-0.5 text-[10px] font-medium text-muted border border-border">
                      {agent.model_alias}
                    </span>
                  </div>
                  <p className="line-clamp-3 text-sm text-secondary leading-relaxed mb-4">
                    {agent.role_prompt || "No system prompt defined."}
                  </p>
                  <div className="flex flex-wrap gap-1 mb-4">
                    {agent.tool_permissions.map(tool => (
                      <span key={tool} className="rounded border border-border bg-background px-1.5 py-0.5 text-[10px] text-muted">
                        {tool}
                      </span>
                    ))}
                    {agent.tool_permissions.length === 0 && <span className="text-[10px] text-muted italic">No tools</span>}
                  </div>
                </div>

                <div className="flex items-center justify-between pt-4 border-t border-border mt-auto">
                  <span className="text-[10px] text-muted">Created {formatDate(agent.created_at)}</span>
                  <div className="flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                    <Button
                      type="button"
                      variant="ghost"
                      className="h-8 px-2.5 text-xs text-accent hover:text-accent-hover hover:bg-accent/10 gap-1"
                      onClick={() => handleChatWithAgent(agent)}
                    >
                      <MessageSquare className="h-3.5 w-3.5" />
                      Chat
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      className="h-8 px-2 text-xs text-muted hover:text-foreground"
                      onClick={() => openEditModal(agent)}
                    >
                      Edit
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      className="h-8 px-2 text-xs text-error hover:bg-error/10"
                      onClick={() => setDeleteTarget(agent)}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        ) : null}
      </div>

      {/* Create / Edit Modal */}
      <Modal open={modalOpen} title={modalTitle} onClose={() => setModalOpen(false)}>
        <form className="grid gap-3" onSubmit={handleFormSubmit}>
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

          {formError ? <p className="text-sm text-error">{formError}</p> : null}

          <div className="mt-2 flex justify-end gap-2">
            <Button type="button" variant="ghost" onClick={() => setModalOpen(false)} disabled={isSaving}>
              Cancel
            </Button>
            <Button type="submit" disabled={isSaving} className="bg-accent hover:bg-accent-hover text-white">
              {isSaving ? (isEditing ? "Saving..." : "Creating...") : (isEditing ? "Save Changes" : "Create")}
            </Button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete agent"
        description={`Delete '${deleteTarget?.name || "this agent"}'? This action cannot be undone.`}
        confirmLabel="Delete"
        loading={deleteMutation.isPending}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteMutation.mutate(deleteTarget.id);
          }
        }}
      />
    </div>
  );
}
