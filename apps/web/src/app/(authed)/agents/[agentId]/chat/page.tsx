"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Send, Loader2 } from "lucide-react";
import Link from "next/link";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { listAgents, createAgentSession, type AgentRead } from "@/lib/api/agents";
import { ApiError } from "@/lib/api/client";
import {
    listSessionMessages,
    submitTurnStream,
    type SessionMessageRead,
    type StreamEvent,
} from "@/lib/api/sessions";

type AgentChatPageProps = {
    params: {
        agentId: string;
    };
};

type ChatMessage = {
    id: string;
    role: "user" | "assistant";
    content: string;
    agentName?: string;
    createdAt?: string;
};

export default function AgentChatPage({ params }: AgentChatPageProps) {
    const { agentId } = params;
    const router = useRouter();
    const searchParams = useSearchParams();
    const sessionIdParam = searchParams.get("session");

    const [sessionId, setSessionId] = useState(sessionIdParam || "");
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState("");
    const [isStreaming, setIsStreaming] = useState(false);
    const [streamDraft, setStreamDraft] = useState("");
    const [error, setError] = useState("");
    const [initializing, setInitializing] = useState(!sessionIdParam);
    const messagesEndRef = useRef<HTMLDivElement>(null);

    // Fetch agent info
    const agentsQuery = useQuery({
        queryKey: ["agents"],
        queryFn: listAgents,
    });
    const agent = agentsQuery.data?.agents?.find((a: AgentRead) => a.id === agentId) || null;

    // Create session if none provided
    useEffect(() => {
        if (sessionIdParam) {
            setSessionId(sessionIdParam);
            setInitializing(false);
            return;
        }
        let cancelled = false;
        (async () => {
            try {
                const session = await createAgentSession(agentId);
                if (!cancelled) {
                    setSessionId(session.id);
                    setInitializing(false);
                    router.replace(`/agents/${agentId}/chat?session=${session.id}`);
                }
            } catch (err) {
                if (!cancelled) {
                    setError(err instanceof ApiError ? err.detail : "Failed to create session.");
                    setInitializing(false);
                }
            }
        })();
        return () => { cancelled = true; };
    }, [agentId, sessionIdParam, router]);

    // Load existing messages
    useEffect(() => {
        if (!sessionId) return;
        (async () => {
            try {
                const result = await listSessionMessages(sessionId, 200, 0);
                const mapped: ChatMessage[] = result.messages.map((m: SessionMessageRead) => ({
                    id: m.id,
                    role: m.role === "user" ? "user" as const : "assistant" as const,
                    content: m.content,
                    agentName: m.agent_name || undefined,
                    createdAt: m.created_at,
                }));
                setMessages(mapped);
            } catch {
                // Ignore - might be empty session
            }
        })();
    }, [sessionId]);

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }, [messages, streamDraft]);

    async function handleSend() {
        const trimmed = input.trim();
        if (!trimmed || isStreaming || !sessionId) return;

        setError("");
        setInput("");
        const userMsg: ChatMessage = {
            id: `user-${Date.now()}`,
            role: "user",
            content: trimmed,
        };
        setMessages((prev) => [...prev, userMsg]);
        setIsStreaming(true);
        setStreamDraft("");

        try {
            let accumulated = "";
            await submitTurnStream(sessionId, { message: trimmed }, (event: StreamEvent) => {
                if (event && typeof event === "object" && event.type === "chunk" && "delta" in event && typeof event.delta === "string") {
                    accumulated += event.delta;
                    setStreamDraft(accumulated);
                }
            });

            const assistantMsg: ChatMessage = {
                id: `assistant-${Date.now()}`,
                role: "assistant",
                content: accumulated || "(No response)",
                agentName: agent?.name || "Agent",
            };
            setMessages((prev) => [...prev, assistantMsg]);
            setStreamDraft("");
        } catch (err) {
            setError(err instanceof ApiError ? err.detail : err instanceof Error ? err.message : "Failed to get response.");
        } finally {
            setIsStreaming(false);
        }
    }

    function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSend();
        }
    }

    if (initializing) {
        return (
            <div className="flex h-full items-center justify-center bg-background">
                <div className="flex items-center gap-3 text-muted">
                    <Loader2 className="h-5 w-5 animate-spin" />
                    <span>Starting conversation...</span>
                </div>
            </div>
        );
    }

    return (
        <div className="flex h-full flex-col bg-background">
            {/* Header */}
            <header className="flex items-center gap-3 border-b border-border px-6 py-4 bg-sidebar">
                <Link href="/agents" className="text-muted hover:text-foreground transition-colors">
                    <ArrowLeft className="h-5 w-5" />
                </Link>
                <div className="flex-1 min-w-0">
                    <h1 className="text-lg font-bold text-foreground truncate">
                        {agent?.name || "Agent Chat"}
                    </h1>
                    <p className="text-xs text-muted truncate">
                        {agent?.model_alias || ""}
                        {agent?.role_prompt ? ` · ${agent.role_prompt.slice(0, 60)}${agent.role_prompt.length > 60 ? "…" : ""}` : ""}
                    </p>
                </div>
                <span className="text-[10px] text-muted bg-elevated px-2 py-1 rounded-full border border-border">
                    1-on-1 Chat
                </span>
            </header>

            {/* Messages area */}
            <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
                {messages.length === 0 && !isStreaming && (
                    <div className="flex flex-col items-center justify-center h-full text-center gap-3">
                        <div className="w-16 h-16 rounded-full bg-accent/10 flex items-center justify-center text-accent text-2xl font-bold">
                            {(agent?.name || "A").charAt(0).toUpperCase()}
                        </div>
                        <h2 className="text-lg font-semibold text-foreground">Chat with {agent?.name || "Agent"}</h2>
                        <p className="text-sm text-muted max-w-md">
                            Start a 1-on-1 conversation. This agent will respond using its configured model and system prompt.
                        </p>
                    </div>
                )}

                {messages.map((msg) => (
                    <div
                        key={msg.id}
                        className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
                    >
                        <div
                            className={[
                                "max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
                                msg.role === "user"
                                    ? "bg-userMessage text-foreground rounded-br-md"
                                    : "bg-surface border border-border text-foreground rounded-bl-md"
                            ].join(" ")}
                        >
                            {msg.role === "assistant" && msg.agentName && (
                                <div className="text-[10px] font-semibold text-accent mb-1 uppercase tracking-wider">
                                    {msg.agentName}
                                </div>
                            )}
                            <div className="prose prose-sm dark:prose-invert max-w-none [&>p]:m-0">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                            </div>
                        </div>
                    </div>
                ))}

                {/* Streaming draft */}
                {isStreaming && streamDraft && (
                    <div className="flex justify-start">
                        <div className="max-w-[75%] rounded-2xl rounded-bl-md px-4 py-3 text-sm bg-surface border border-border text-foreground leading-relaxed">
                            <div className="text-[10px] font-semibold text-accent mb-1 uppercase tracking-wider">
                                {agent?.name || "Agent"}
                            </div>
                            <div className="prose prose-sm dark:prose-invert max-w-none [&>p]:m-0">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamDraft}</ReactMarkdown>
                            </div>
                        </div>
                    </div>
                )}

                {isStreaming && !streamDraft && (
                    <div className="flex justify-start">
                        <div className="flex items-center gap-2 text-muted text-sm px-4 py-3 bg-surface border border-border rounded-2xl rounded-bl-md">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            Thinking...
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Error */}
            {error && (
                <div className="mx-6 mb-2 rounded-lg bg-error/10 border border-error/20 px-4 py-2 text-sm text-error">
                    {error}
                </div>
            )}

            {/* Input area */}
            <div className="border-t border-border bg-sidebar px-6 py-4">
                <div className="mx-auto max-w-4xl flex gap-3 items-end">
                    <textarea
                        className="flex-1 min-h-[44px] max-h-[160px] resize-none rounded-xl border border-border bg-input px-4 py-3 text-sm text-foreground placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent transition-colors"
                        rows={1}
                        placeholder={`Message ${agent?.name || "Agent"}...`}
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={handleKeyDown}
                        disabled={isStreaming}
                    />
                    <Button
                        onClick={handleSend}
                        disabled={isStreaming || !input.trim()}
                        className="h-11 w-11 rounded-xl bg-accent hover:bg-accent-hover text-white flex-shrink-0 p-0"
                    >
                        {isStreaming ? (
                            <Loader2 className="h-5 w-5 animate-spin" />
                        ) : (
                            <Send className="h-5 w-5" />
                        )}
                    </Button>
                </div>
            </div>
        </div>
    );
}
