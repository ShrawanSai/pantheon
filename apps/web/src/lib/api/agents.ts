"use client";

import { apiFetch } from "@/lib/api/client";

export type AgentRead = {
  id: string;
  owner_user_id: string;
  agent_key: string;
  name: string;
  model_alias: string;
  role_prompt: string;
  tool_permissions: string[];
  created_at: string;
  updated_at: string;
};

type AgentCreateRequest = {
  agent_key: string;
  name: string;
  model_alias: string;
  role_prompt?: string;
  tool_permissions?: string[];
};

type AgentUpdateRequest = {
  name?: string;
  model_alias?: string;
  role_prompt?: string;
  tool_permissions?: string[];
};

export function listAgents(): Promise<{ agents: AgentRead[]; total: number }> {
  return apiFetch<{ agents: AgentRead[]; total: number }>("/api/v1/agents", {
    method: "GET"
  });
}

export function createAgent(payload: AgentCreateRequest): Promise<AgentRead> {
  return apiFetch<AgentRead>("/api/v1/agents", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function updateAgent(agentId: string, payload: AgentUpdateRequest): Promise<AgentRead> {
  return apiFetch<AgentRead>(`/api/v1/agents/${agentId}`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function deleteAgent(agentId: string): Promise<void> {
  await apiFetch<null>(`/api/v1/agents/${agentId}`, {
    method: "DELETE"
  });
}

export function createAgentSession(agentId: string): Promise<{ id: string; agent_id: string }> {
  return apiFetch<{ id: string; agent_id: string }>(`/api/v1/agents/${agentId}/sessions`, {
    method: "POST"
  });
}

export function listAgentSessions(agentId: string): Promise<{ sessions: Array<{ id: string; agent_id: string; created_at: string }> }> {
  return apiFetch<{ sessions: Array<{ id: string; agent_id: string; created_at: string }> }>(`/api/v1/agents/${agentId}/sessions`, {
    method: "GET"
  });
}
