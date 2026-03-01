"use client";

import { useState } from "react";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { X, GripVertical, Ban, PlusCircle, Touchpad, Users, Zap, Trash2, ArrowLeft, Search, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { updateRoomMode, removeRoomAgent, deleteRoom, assignRoomAgent, type RoomRead, type RoomMode, type RoomAgentRead } from "@/lib/api/rooms";
import { type AgentRead } from "@/lib/api/agents";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { useRouter } from "next/navigation";

type ManageRoomPanelProps = {
    room: RoomRead;
    agents: RoomAgentRead[];
    allAgents: AgentRead[];
    onClose: () => void;
};

export function ManageRoomPanel({ room, agents, allAgents, onClose }: ManageRoomPanelProps) {
    const router = useRouter();
    const queryClient = useQueryClient();
    const [deleteConfOpen, setDeleteConfOpen] = useState(false);
    const [isAddingExpert, setIsAddingExpert] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const [addingIds, setAddingIds] = useState<Set<string>>(new Set());

    const modeMutation = useMutation({
        mutationFn: async (mode: RoomMode) => updateRoomMode(room.id, mode),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["room", room.id] });
        }
    });

    const removeAgentMutation = useMutation({
        mutationFn: async (agentId: string) => removeRoomAgent(room.id, agentId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["roomAgents", room.id] });
        }
    });

    const deleteRoomMutation = useMutation({
        mutationFn: async () => deleteRoom(room.id),
        onSuccess: () => {
            router.push("/rooms");
        }
    });

    const assignAgentMutation = useMutation({
        mutationFn: async (agentId: string) => assignRoomAgent(room.id, { agent_id: agentId }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ["roomAgents", room.id] });
        }
    });

    const assignedAgentIds = new Set(agents.map(a => a.agent_id));
    const availableAgents = allAgents.filter(a => !assignedAgentIds.has(a.id) && (
        a.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (a.role_prompt && a.role_prompt.toLowerCase().includes(searchQuery.toLowerCase()))
    ));

    const handleAddAgents = async () => {
        if (addingIds.size === 0) {
            setIsAddingExpert(false);
            return;
        }
        const ids = Array.from(addingIds);
        await Promise.all(ids.map(id => assignAgentMutation.mutateAsync(id)));
        setAddingIds(new Set());
        setIsAddingExpert(false);
    };

    // Basic styling mapping closely to Stitch design "Manage Room"
    return (
        <div className="fixed inset-y-0 right-0 w-full md:w-[480px] bg-background border-l border-border shadow-2xl flex flex-col z-50 animate-in slide-in-from-right duration-300">
            <div className="flex items-center bg-background/80 backdrop-blur-md sticky top-0 z-10 p-4 pb-2 justify-between border-b border-border/50">
                <button onClick={() => isAddingExpert ? setIsAddingExpert(false) : onClose()} className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-foreground hover:bg-elevated transition-colors cursor-pointer">
                    <ArrowLeft className="w-5 h-5" />
                </button>
                <div className="flex flex-col items-center flex-1">
                    <h2 className="text-muted text-xs font-bold uppercase tracking-[0.2em] leading-tight">{isAddingExpert ? "Add Experts" : "Manage Council"}</h2>
                    <h3 className="text-foreground text-base font-semibold leading-tight">{room.name}</h3>
                </div>
                <div className="flex w-10 items-center justify-end">
                    <button onClick={onClose} className="flex items-center justify-center rounded-full h-10 w-10 text-muted hover:text-foreground transition-colors">
                        <X className="w-5 h-5" />
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto hide-scrollbar pb-12 flex flex-col">
                {isAddingExpert ? (
                    <div className="px-6 pt-6 flex flex-col h-full gap-4">
                        <div className="relative w-full shrink-0">
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
                        <div className="flex-1 flex flex-col gap-3 pb-4">
                            {availableAgents.length === 0 ? (
                                <div className="text-center p-8 text-muted text-sm border border-dashed border-border rounded-xl">No available agents found.</div>
                            ) : (
                                availableAgents.map((agent) => {
                                    const isSelected = addingIds.has(agent.id);
                                    return (
                                        <div
                                            key={agent.id}
                                            onClick={() => {
                                                const next = new Set(addingIds);
                                                isSelected ? next.delete(agent.id) : next.add(agent.id);
                                                setAddingIds(next);
                                            }}
                                            className={`flex flex-col gap-3 rounded-xl p-4 border shadow-sm cursor-pointer transition-all ${isSelected ? 'bg-accent/5 border-accent ring-1 ring-accent' : 'bg-surface border-border hover:border-accent/50'}`}
                                        >
                                            <div className="flex items-center gap-3">
                                                <div className={`size-10 rounded-full flex items-center justify-center font-bold text-sm ${isSelected ? 'bg-accent text-white' : 'bg-elevated text-foreground'}`}>
                                                    {agent.name.substring(0, 2).toUpperCase()}
                                                </div>
                                                <div className="flex flex-col flex-1 min-w-0">
                                                    <h4 className="text-foreground font-bold truncate">{agent.name}</h4>
                                                    <span className="text-muted text-xs font-medium truncate">{agent.role_prompt || "General AI"}</span>
                                                </div>
                                                <div className={`size-5 rounded-full border flex items-center justify-center shrink-0 ${isSelected ? 'bg-accent border-accent text-white' : 'border-border text-transparent'}`}>
                                                    <CheckCircle2 className="w-3 h-3" />
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })
                            )}
                        </div>
                        <button
                            onClick={handleAddAgents}
                            disabled={assignAgentMutation.isPending}
                            className="w-full mb-6 mt-auto flex items-center justify-center gap-2 bg-accent text-white py-4 rounded-xl font-bold shadow-lg shadow-accent/20 active:scale-[0.98] transition-all hover:bg-accent-hover disabled:opacity-50 shrink-0"
                        >
                            {assignAgentMutation.isPending ? "Adding..." : `Add ${addingIds.size} Agent${addingIds.size !== 1 ? 's' : ''}`}
                        </button>
                    </div>
                ) : (
                    <>
                        <div className="px-6 pt-8 pb-4">
                            <div className="flex items-center justify-between mb-4">
                                <h4 className="text-foreground text-xl font-bold tracking-tight">Agent Roster</h4>
                                <span className="text-xs font-mono bg-accent/10 text-accent px-2 py-1 rounded-md font-bold">{agents.length} ACTIVE</span>
                            </div>

                            <div className="space-y-3">
                                {agents.map((assignment) => {
                                    const fullAgent = allAgents.find(a => a.id === assignment.agent_id) || assignment.agent;
                                    return (
                                        <div key={assignment.id} className="flex items-center gap-4 bg-surface/50 border border-border p-4 rounded-xl shadow-sm">
                                            <div className="text-muted cursor-grab active:cursor-grabbing hover:text-foreground transition-colors">
                                                <GripVertical className="w-5 h-5" />
                                            </div>
                                            <div className="flex items-center justify-center rounded-full h-12 w-12 border-2 border-accent/20 bg-accent/10 text-accent font-bold text-lg">
                                                {fullAgent.name.substring(0, 2).toUpperCase()}
                                            </div>
                                            <div className="flex flex-col flex-1 min-w-0">
                                                <p className="text-foreground text-base font-semibold leading-none truncate">{fullAgent.name}</p>
                                                <p className="text-muted text-xs mt-1 font-medium truncate">{fullAgent.role_prompt || "General AI"}</p>
                                            </div>
                                            <button
                                                onClick={() => removeAgentMutation.mutate(assignment.agent_id)}
                                                disabled={removeAgentMutation.isPending}
                                                className="text-error/70 hover:text-error transition-colors p-1 shrink-0"
                                                title="Remove from Room"
                                            >
                                                <Ban className="w-5 h-5" />
                                            </button>
                                        </div>
                                    );
                                })}

                                <button
                                    onClick={() => setIsAddingExpert(true)}
                                    className="w-full mt-6 flex items-center justify-center gap-2 bg-accent text-white py-4 rounded-xl font-bold shadow-lg shadow-accent/20 active:scale-[0.98] transition-all hover:bg-accent-hover"
                                >
                                    <PlusCircle className="w-5 h-5" />
                                    <span>Add New Expert</span>
                                </button>
                            </div>
                        </div>

                        <div className="px-6 py-8 border-t border-border">
                            <h4 className="text-foreground text-lg font-bold mb-6">Council Settings</h4>

                            <div className="pt-2">
                                <p className="text-foreground font-semibold mb-3">Operational Mode</p>
                                <div className="grid grid-cols-3 gap-2">
                                    <button
                                        onClick={() => modeMutation.mutate("manual")}
                                        className={`flex flex-col items-center flex-1 justify-center p-3 rounded-xl border-2 transition-all ${room.current_mode === "manual" ? "border-accent bg-accent/5 text-accent" : "border-border/50 bg-surface/50 text-muted hover:border-border"}`}
                                    >
                                        <Touchpad className="w-5 h-5 mb-1" />
                                        <span className="text-[10px] font-bold uppercase tracking-wider">Manual</span>
                                    </button>
                                    <button
                                        onClick={() => modeMutation.mutate("roundtable")}
                                        className={`flex flex-col items-center flex-1 justify-center p-3 rounded-xl border-2 transition-all ${room.current_mode === "roundtable" ? "border-mode-team bg-mode-team/5 text-mode-team" : "border-border/50 bg-surface/50 text-muted hover:border-border"}`}
                                    >
                                        <Users className="w-5 h-5 mb-1" />
                                        <span className="text-[10px] font-bold uppercase tracking-wider">Round Table</span>
                                    </button>
                                    <button
                                        onClick={() => modeMutation.mutate("orchestrator")}
                                        className={`flex flex-col items-center flex-1 justify-center p-3 rounded-xl border-2 transition-all ${room.current_mode === "orchestrator" ? "border-mode-auto bg-mode-auto/5 text-mode-auto" : "border-border/50 bg-surface/50 text-muted hover:border-border"}`}
                                    >
                                        <Zap className="w-5 h-5 mb-1" />
                                        <span className="text-[10px] font-bold uppercase tracking-wider">Auto-Pilot</span>
                                    </button>
                                </div>
                                <p className="text-xs text-muted mt-3 h-10">
                                    {room.current_mode === "manual" ? "Solo mode: tag agents individually to reply." :
                                        room.current_mode === "roundtable" ? "Team mode: agents respond in sequential rounds." :
                                            "Auto-pilot: orchestrator manages the team automatically."}
                                </p>
                            </div>
                        </div>

                        <div className="px-6 py-10 flex flex-col items-center border-t border-border bg-surface/30 mt-auto">
                            <button
                                onClick={() => setDeleteConfOpen(true)}
                                className="text-error/80 hover:text-error transition-colors flex items-center gap-2 py-2 px-4 rounded-lg hover:bg-error/10"
                            >
                                <Trash2 className="w-5 h-5" />
                                <span className="text-sm font-bold tracking-wide uppercase">Delete Council</span>
                            </button>
                            <p className="mt-4 text-[10px] text-muted font-mono uppercase tracking-[0.2em]">{room.id}</p>
                        </div>
                    </>
                )}
            </div>

            <ConfirmDialog
                open={deleteConfOpen}
                title="Delete Council?"
                description="Are you sure you want to delete this council? This will permanently delete all sessions, messages, and files associated with it. This action cannot be undone."
                onConfirm={() => deleteRoomMutation.mutate()}
                onClose={() => setDeleteConfOpen(false)}
                confirmLabel="Delete Council"
                loading={deleteRoomMutation.isPending}
            />
        </div>
    );
}
