"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PlusCircle, ArrowRight, ArrowLeft, Loader2, Search, CheckCircle2 } from "lucide-react";

import { Modal } from "@/components/common/modal";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api/client";
import { createRoom, assignRoomAgent, type RoomMode, type RoomRead } from "@/lib/api/rooms";
import { listAgents, type AgentRead } from "@/lib/api/agents";

type RoomUiMode = "solo" | "team" | "auto";

type CreateRoomFormState = {
    name: string;
    goal: string;
    uiMode: RoomUiMode;
    selectedAgentIds: Set<string>;
};

const ROOM_MODE_DESCRIPTIONS: Record<RoomUiMode, string> = {
    solo: "One primary agent replies each turn, like a normal chat.",
    team: "A team of agents replies in sequence so you get multiple perspectives.",
    auto: "A manager coordinates specialists and returns one consolidated answer."
};

function mapUiModeToApiMode(mode: RoomUiMode): RoomMode {
    if (mode === "solo") return "manual";
    if (mode === "team") return "roundtable";
    return "orchestrator";
}

export function CreateRoomModal({ open, onClose }: { open: boolean; onClose: () => void }) {
    const queryClient = useQueryClient();
    const [step, setStep] = useState<1 | 2>(1);
    const [form, setForm] = useState<CreateRoomFormState>({
        name: "",
        goal: "",
        uiMode: "solo",
        selectedAgentIds: new Set()
    });
    const [formError, setFormError] = useState("");
    const [searchQuery, setSearchQuery] = useState("");

    const agentsQuery = useQuery({ queryKey: ["agents"], queryFn: listAgents });

    const filteredAgents = (agentsQuery.data?.agents || []).filter(agent =>
        agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (agent.role_prompt && agent.role_prompt.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    const resetForm = () => {
        setForm({ name: "", goal: "", uiMode: "solo", selectedAgentIds: new Set() });
        setStep(1);
        setFormError("");
        setSearchQuery("");
    };

    const handleClose = () => {
        if (!createMutation.isPending) {
            resetForm();
            onClose();
        }
    };

    const createMutation = useMutation({
        mutationFn: async () => {
            const trimmedName = form.name.trim();
            if (!trimmedName) throw new ApiError(422, "Room name is required.");

            const newRoom = await createRoom({
                name: trimmedName,
                goal: form.goal.trim() || undefined,
                current_mode: mapUiModeToApiMode(form.uiMode)
            });

            // Add agents to room
            if (form.selectedAgentIds.size > 0) {
                const addedAgents = Array.from(form.selectedAgentIds);
                await Promise.all(addedAgents.map(agentId => assignRoomAgent(newRoom.id, { agent_id: agentId })));
            }

            return newRoom;
        },
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["rooms"] });
            handleClose();
        },
        onError: (error) => {
            setFormError(error instanceof ApiError ? error.detail : "Failed to create room.");
        }
    });

    const toggleAgent = (agentId: string) => {
        const next = new Set(form.selectedAgentIds);
        if (next.has(agentId)) {
            next.delete(agentId);
        } else {
            next.add(agentId);
        }
        setForm(prev => ({ ...prev, selectedAgentIds: next }));
    };

    const isStep1Valid = form.name.trim().length > 0;

    return (
        <Modal open={open} title="" onClose={handleClose}>
            <div className="w-full max-w-lg min-h-[400px] flex flex-col font-sans">

                {/* Header equivalent styled like the Stitch component */}
                <div className="flex items-center justify-between mb-6">
                    <div className="flex flex-col">
                        <span className="text-accent font-semibold tracking-widest text-[10px] uppercase mb-1 block">Step 0{step} / 02</span>
                        <h2 className="font-serif text-2xl font-bold text-foreground">
                            {step === 1 ? "New Council" : "Add Agents"}
                        </h2>
                    </div>
                    {step === 2 && (
                        <Button type="button" variant="ghost" size="sm" onClick={() => setStep(1)} className="rounded-full text-muted hover:text-foreground">
                            <ArrowLeft className="w-4 h-4 mr-2" /> Back
                        </Button>
                    )}
                </div>

                {formError ? <div className="mb-4 p-3 bg-error/10 border border-error/20 rounded-lg text-sm text-error">{formError}</div> : null}

                {step === 1 ? (
                    <form className="flex-1 flex flex-col gap-5" onSubmit={e => { e.preventDefault(); if (isStep1Valid) setStep(2); }}>
                        <p className="text-muted text-sm leading-relaxed mb-2">
                            Every great gathering begins with a shared intention. Define the identity and purpose of your new assembly.
                        </p>

                        <label className="grid gap-1.5 text-sm">
                            <span className="text-accent font-semibold uppercase text-xs tracking-wider">Council Name <span className="text-error">*</span></span>
                            <input
                                className="w-full bg-transparent border-b-2 border-border focus:border-accent border-t-0 border-l-0 border-r-0 px-1 py-3 text-lg placeholder:text-muted focus:ring-0 transition-all outline-none"
                                value={form.name}
                                onChange={(e) => setForm((prev) => ({ ...prev, name: e.target.value }))}
                                placeholder="e.g. The Sapphire Circle"
                                autoFocus
                            />
                        </label>

                        <label className="grid gap-1.5 text-sm">
                            <span className="text-accent font-semibold uppercase text-xs tracking-wider">Purpose & Description</span>
                            <textarea
                                className="w-full bg-surface/50 rounded-xl border border-border p-4 text-sm placeholder:text-muted focus:ring-2 focus:ring-accent/50 focus:border-accent transition-all outline-none resize-none"
                                value={form.goal}
                                onChange={(e) => setForm((prev) => ({ ...prev, goal: e.target.value }))}
                                placeholder="What brings this council together? Define your shared goals..."
                                rows={3}
                            />
                        </label>

                        <label className="grid gap-1.5 text-sm mt-2">
                            <span className="text-accent font-semibold uppercase text-xs tracking-wider">Operation Mode</span>
                            <div className="relative">
                                <select
                                    className="w-full h-11 appearance-none rounded-xl border border-border bg-input px-4 text-foreground focus:ring-2 focus:ring-accent/50 focus:border-accent outline-none transition-all shadow-sm"
                                    value={form.uiMode}
                                    onChange={(e) => setForm((prev) => ({ ...prev, uiMode: e.target.value as RoomUiMode }))}
                                >
                                    <option value="solo">Manual / Solo (Tag agents to reply)</option>
                                    <option value="team">Team Discussion (Sequential replies)</option>
                                    <option value="auto">Auto-Pilot (Manager coordinates)</option>
                                </select>
                            </div>
                            <p className="text-xs text-muted mt-1 leading-relaxed">{ROOM_MODE_DESCRIPTIONS[form.uiMode]}</p>
                        </label>

                        <div className="mt-auto pt-6 flex justify-end gap-3">
                            <Button type="button" variant="ghost" onClick={handleClose} className="rounded-full">Cancel</Button>
                            <Button type="submit" disabled={!isStep1Valid} className="bg-accent hover:bg-accent-hover text-white rounded-full px-6">
                                Continue <ArrowRight className="w-4 h-4 ml-2" />
                            </Button>
                        </div>
                    </form>
                ) : (
                    <div className="flex-1 flex flex-col h-[60vh] max-h-[500px]">
                        {/* Search Agents */}
                        <div className="relative w-full mb-4 shrink-0">
                            <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none">
                                <Search className="w-5 h-5" />
                            </span>
                            <input
                                className="w-full bg-surface border border-border rounded-xl py-3 pl-10 pr-4 text-sm font-medium placeholder:text-muted focus:outline-none focus:ring-1 focus:ring-accent focus:border-accent transition-all shadow-sm text-foreground"
                                placeholder="Search templates to add..."
                                value={searchQuery}
                                onChange={e => setSearchQuery(e.target.value)}
                            />
                        </div>

                        {/* Agent List */}
                        <div className="flex-1 overflow-y-auto hide-scrollbar flex flex-col gap-3 pr-2 pb-6">
                            {agentsQuery.isLoading ? (
                                <div className="flex items-center justify-center p-8 text-muted"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Loading agents...</div>
                            ) : filteredAgents.length === 0 ? (
                                <div className="text-center p-8 text-muted text-sm border border-dashed border-border rounded-xl">No agents found matching your search.</div>
                            ) : (
                                filteredAgents.map(agent => {
                                    const isSelected = form.selectedAgentIds.has(agent.id);
                                    return (
                                        <div
                                            key={agent.id}
                                            onClick={() => toggleAgent(agent.id)}
                                            className={`flex flex-col gap-3 rounded-xl p-4 border shadow-sm cursor-pointer transition-all ${isSelected ? 'bg-accent/5 border-accent ring-1 ring-accent' : 'bg-surface border-border hover:border-accent/50'}`}
                                        >
                                            <div className="flex items-center gap-3">
                                                <div className={`size-10 rounded-full flex items-center justify-center font-bold text-sm ${isSelected ? 'bg-accent text-white' : 'bg-elevated text-foreground'}`}>
                                                    {agent.name.substring(0, 2).toUpperCase()}
                                                </div>
                                                <div className="flex flex-col flex-1">
                                                    <div className="flex items-center justify-between">
                                                        <h4 className="text-foreground font-bold">{agent.name}</h4>
                                                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-elevated text-muted uppercase">{(agent.model_alias || "AI").replace('openai/', '').replace('anthropic/', '').substring(0, 10)}</span>
                                                    </div>
                                                    <p className="text-muted text-xs font-medium line-clamp-1">{agent.role_prompt || "General AI"}</p>
                                                </div>
                                            </div>
                                            <div className="flex items-center justify-between mt-1">
                                                <span className="text-[10px] uppercase font-bold text-muted">Select to Add</span>
                                                <div className={`size-5 rounded-full border flex items-center justify-center ${isSelected ? 'bg-accent border-accent text-white' : 'border-border text-transparent'}`}>
                                                    <CheckCircle2 className="w-3 h-3" />
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })
                            )}
                        </div>

                        <div className="mt-auto pt-4 border-t border-border shrink-0 flex justify-end gap-3 bg-background">
                            <Button type="button" variant="ghost" onClick={handleClose} disabled={createMutation.isPending} className="rounded-full">Cancel</Button>
                            <Button
                                onClick={() => createMutation.mutate()}
                                disabled={createMutation.isPending}
                                className="bg-accent hover:bg-accent-hover text-white rounded-full px-6 flex-1 sm:flex-none"
                            >
                                {createMutation.isPending ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <PlusCircle className="w-4 h-4 mr-2" />}
                                {createMutation.isPending ? "Building Room..." : `Launch with ${form.selectedAgentIds.size} Agent${form.selectedAgentIds.size !== 1 ? 's' : ''}`}
                            </Button>
                        </div>
                    </div>
                )}
            </div>
        </Modal>
    );
}
