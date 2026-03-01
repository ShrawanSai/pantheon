"use client";

import { useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Users, Activity, Settings, DollarSign } from "lucide-react";

const TABS = [
    { id: "usage", label: "Usage", icon: Activity },
    { id: "users", label: "Users", icon: Users },
    { id: "pricing", label: "Pricing", icon: DollarSign },
    { id: "settings", label: "Settings", icon: Settings },
];

const mockChartData = Array.from({ length: 30 }).map((_, i) => ({
    date: new Date(Date.now() - (29 - i) * 86400000).toLocaleDateString("en-US", { month: "short", day: "numeric" }),
    tokens: Math.floor(Math.random() * 50000) + 10000,
}));

export default function AdminDashboardPage() {
    const [activeTab, setActiveTab] = useState("usage");

    return (
        <div className="flex h-full flex-col bg-background p-6">
            <div className="mx-auto w-full max-w-6xl">
                <header className="mb-8">
                    <h1 className="text-[24px] font-bold text-foreground tracking-tight">Admin Dashboard</h1>
                    <p className="mt-1 text-sm text-muted">Manage platform usage, billing, and global settings.</p>
                </header>

                {/* Tab Navigation */}
                <div className="mb-6 flex gap-2 border-b border-border pb-px">
                    {TABS.map((tab) => {
                        const Icon = tab.icon;
                        const active = activeTab === tab.id;
                        return (
                            <button
                                key={tab.id}
                                onClick={() => setActiveTab(tab.id)}
                                className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium transition-colors border-b-2 ${active
                                        ? "border-accent text-accent"
                                        : "border-transparent text-muted hover:border-border hover:text-foreground"
                                    }`}
                            >
                                <Icon className="h-4 w-4" />
                                {tab.label}
                            </button>
                        );
                    })}
                </div>

                {/* Tab Content */}
                <div className="rounded-2xl border border-border bg-white dark:bg-surface p-6 shadow-sm">
                    {activeTab === "usage" && (
                        <div className="animate-in fade-in duration-300">
                            <h2 className="text-lg font-semibold mb-6">API Token Usage (30 Days)</h2>
                            <div className="h-[300px] w-full">
                                <ResponsiveContainer width="100%" height="100%">
                                    <LineChart data={mockChartData} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="hsl(var(--border))" />
                                        <XAxis dataKey="date" axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "hsl(var(--muted))" }} dy={10} />
                                        <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 12, fill: "hsl(var(--muted))" }} width={60} tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`} />
                                        <Tooltip
                                            contentStyle={{ backgroundColor: "hsl(var(--surface))", borderRadius: "8px", border: "1px solid hsl(var(--border))", boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1)" }}
                                            itemStyle={{ color: "hsl(var(--foreground))", fontSize: "14px", fontWeight: 500 }}
                                        />
                                        <Line type="monotone" dataKey="tokens" stroke="hsl(var(--accent))" strokeWidth={3} dot={false} activeDot={{ r: 6, fill: "hsl(var(--accent))", stroke: "white", strokeWidth: 2 }} />
                                    </LineChart>
                                </ResponsiveContainer>
                            </div>
                        </div>
                    )}

                    {activeTab === "users" && (
                        <div className="animate-in fade-in duration-300">
                            <h2 className="text-lg font-semibold mb-6">Registered Users</h2>
                            <table className="w-full text-left text-sm">
                                <thead className="bg-elevated/50 text-muted">
                                    <tr>
                                        <th className="px-6 py-3 font-medium rounded-tl-lg">User ID</th>
                                        <th className="px-6 py-3 font-medium">Email</th>
                                        <th className="px-6 py-3 font-medium">Role</th>
                                        <th className="px-6 py-3 font-medium rounded-tr-lg">Status</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-border">
                                    <tr className="hover:bg-elevated/30 transition-colors">
                                        <td className="px-6 py-4 font-mono text-xs">usr_example123</td>
                                        <td className="px-6 py-4">admin@pantheon.ai</td>
                                        <td className="px-6 py-4"><span className="rounded-full bg-accent/10 px-2 py-0.5 text-[10px] font-medium tracking-wide text-accent uppercase">Admin</span></td>
                                        <td className="px-6 py-4"><span className="text-success text-xs font-medium">Active</span></td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    )}

                    {activeTab === "pricing" && (
                        <div className="animate-in fade-in duration-300">
                            <h2 className="text-lg font-semibold mb-6">Model Pricing</h2>
                            <table className="w-full text-left text-sm">
                                <thead className="bg-elevated/50 text-muted">
                                    <tr>
                                        <th className="px-6 py-3 font-medium rounded-tl-lg">Model</th>
                                        <th className="px-6 py-3 font-medium">Provider</th>
                                        <th className="px-6 py-3 font-medium">Input/1M</th>
                                        <th className="px-6 py-3 font-medium rounded-tr-lg">Output/1M</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-border">
                                    <tr className="hover:bg-elevated/30 transition-colors">
                                        <td className="px-6 py-4 font-medium">DeepSeek Chat</td>
                                        <td className="px-6 py-4 text-muted">DeepSeek</td>
                                        <td className="px-6 py-4 text-muted">$0.14</td>
                                        <td className="px-6 py-4 text-muted">$0.28</td>
                                    </tr>
                                </tbody>
                            </table>
                        </div>
                    )}

                    {activeTab === "settings" && (
                        <div className="animate-in fade-in duration-300 max-w-md">
                            <h2 className="text-lg font-semibold mb-6">System Settings</h2>
                            <div className="space-y-4">
                                <div className="flex items-center justify-between">
                                    <div>
                                        <div className="font-medium text-sm text-foreground">Open Registration</div>
                                        <div className="text-xs text-muted">Allow new users to create accounts</div>
                                    </div>
                                    <input type="checkbox" className="accent-accent w-4 h-4" defaultChecked />
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
