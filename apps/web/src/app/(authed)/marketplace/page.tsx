"use client";

import { Search, Star, Download, Sparkles } from "lucide-react";
import { useState } from "react";

const MOCK_AGENTS = [
  { id: "1", name: "Research Analyst", category: "Research", description: "Deep-dives into topics, summarizes findings, and cites sources. Ideal for investigative tasks.", stars: 4.9, uses: "12.4k", model: "Premium", featured: true },
  { id: "2", name: "Code Reviewer", category: "Engineering", description: "Reviews pull requests, suggests refactors, and identifies bugs. Speaks fluent TypeScript and Python.", stars: 4.8, uses: "9.1k", model: "DeepSeek" },
  { id: "3", name: "Strategy Advisor", category: "Business", description: "Frameworks-driven consultant for GTM, pricing, and competitive analysis.", stars: 4.7, uses: "7.8k", model: "Premium" },
  { id: "4", name: "Data Scientist", category: "Analytics", description: "Interprets datasets, proposes experiments, and translates results into actionable insights.", stars: 4.6, uses: "5.2k", model: "Qwen" },
  { id: "5", name: "Content Writer", category: "Marketing", description: "Brand-voice-matched copy for blogs, social, and long-form content.", stars: 4.5, uses: "15.3k", model: "DeepSeek", featured: true },
  { id: "6", name: "Legal Summarizer", category: "Legal", description: "Distills contracts and regulatory docs into plain-English summaries.", stars: 4.4, uses: "3.7k", model: "Premium" },
  { id: "7", name: "UX Critic", category: "Design", description: "Audits interfaces for usability, accessibility, and conversion patterns.", stars: 4.7, uses: "6.9k", model: "Llama" },
  { id: "8", name: "Financial Modeler", category: "Finance", description: "Builds projections, runs sensitivity analysis, and stress-tests assumptions.", stars: 4.6, uses: "4.1k", model: "Premium" },
  { id: "9", name: "Customer Support", category: "Support", description: "Handles tier-1 queries, escalations, and FAQs with empathy and precision.", stars: 4.3, uses: "22.1k", model: "Free Tier" },
];

const CATEGORIES = ["All", "Research", "Engineering", "Business", "Analytics", "Marketing", "Legal", "Design", "Finance", "Support"];

function agentHue(name: string): number {
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = name.charCodeAt(i) + ((hash << 5) - hash);
  return Math.abs(hash) % 360;
}

function initials(name: string): string {
  return name.split(/\s+/).map(w => w[0] ?? "").join("").toUpperCase().slice(0, 2);
}

export default function MarketplacePage() {
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState("All");

  const filtered = MOCK_AGENTS.filter(a => {
    const matchesSearch = !search || a.name.toLowerCase().includes(search.toLowerCase()) || a.description.toLowerCase().includes(search.toLowerCase());
    const matchesCategory = activeCategory === "All" || a.category === activeCategory;
    return matchesSearch && matchesCategory;
  });

  const featured = filtered.filter(a => a.featured);
  const rest = filtered.filter(a => !a.featured);

  return (
    <div className="flex h-full flex-col bg-background overflow-y-auto">
      {/* Hero */}
      <div className="bg-gradient-to-br from-accent/10 via-background to-background border-b border-border px-6 md:px-10 pt-10 pb-8">
        <div className="max-w-3xl">
          <div className="flex items-center gap-2 mb-3">
            <Sparkles className="w-5 h-5 text-accent" />
            <span className="text-xs font-bold uppercase tracking-widest text-accent">Agent Marketplace</span>
          </div>
          <h1 className="text-3xl font-bold font-serif text-foreground mb-2">Discover & Deploy Agents</h1>
          <p className="text-muted text-sm leading-relaxed max-w-xl">
            Browse pre-built agent templates crafted for specific roles. Add them to any room and start collaborating instantly.
          </p>
        </div>

        {/* Search */}
        <div className="relative mt-6 max-w-lg">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-muted pointer-events-none" />
          <input
            className="w-full bg-white dark:bg-surface border border-border rounded-xl py-3 pl-11 pr-4 text-sm placeholder:text-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent transition-all shadow-sm text-foreground"
            placeholder="Search agents by name or skill…"
            value={search}
            onChange={e => setSearch(e.target.value)}
          />
        </div>
      </div>

      <div className="px-6 md:px-10 py-6 space-y-8 max-w-6xl w-full mx-auto">
        {/* Category pills */}
        <div className="flex gap-2 flex-wrap">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setActiveCategory(cat)}
              className={`px-4 py-1.5 rounded-full text-xs font-semibold border transition-all ${activeCategory === cat
                ? "bg-accent text-white border-accent"
                : "bg-elevated text-muted border-border hover:border-accent hover:text-accent"
                }`}
            >
              {cat}
            </button>
          ))}
        </div>

        {/* Featured */}
        {featured.length > 0 && (
          <section>
            <h2 className="text-lg font-bold font-serif text-foreground mb-4">⭐ Featured</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {featured.map(agent => {
                const hue = agentHue(agent.name);
                return (
                  <div key={agent.id} className="relative bg-white dark:bg-surface rounded-2xl border border-accent/30 p-5 shadow-sm hover:shadow-md hover:border-accent transition-all group">
                    <div className="absolute top-4 right-4">
                      <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-accent/10 text-accent uppercase tracking-wide">Featured</span>
                    </div>
                    <div className="flex items-start gap-4 mb-3">
                      <div
                        className="w-12 h-12 rounded-xl flex items-center justify-center text-white text-sm font-bold shadow-sm shrink-0"
                        style={{ background: `hsl(${hue},55%,50%)` }}
                      >
                        {initials(agent.name)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-bold text-foreground">{agent.name}</h3>
                        <p className="text-xs text-muted mt-0.5">{agent.category} · {agent.model}</p>
                      </div>
                    </div>
                    <p className="text-sm text-muted leading-relaxed mb-4">{agent.description}</p>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 text-xs text-muted">
                        <span className="flex items-center gap-1"><Star className="w-3 h-3 text-yellow-400 fill-yellow-400" />{agent.stars}</span>
                        <span className="flex items-center gap-1"><Download className="w-3 h-3" />{agent.uses}</span>
                      </div>
                      <button className="px-4 py-1.5 rounded-full bg-accent text-white text-xs font-bold hover:bg-accent-hover transition-colors opacity-0 group-hover:opacity-100">
                        Add to Room
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {/* All agents */}
        {rest.length > 0 && (
          <section>
            <h2 className="text-lg font-bold font-serif text-foreground mb-4">All Agents</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {rest.map(agent => {
                const hue = agentHue(agent.name);
                return (
                  <div key={agent.id} className="bg-white dark:bg-surface rounded-2xl border border-border p-5 shadow-sm hover:shadow-md hover:border-accent transition-all group cursor-default">
                    <div className="flex items-start gap-3 mb-3">
                      <div
                        className="w-10 h-10 rounded-xl flex items-center justify-center text-white text-xs font-bold shadow-sm shrink-0"
                        style={{ background: `hsl(${hue},55%,50%)` }}
                      >
                        {initials(agent.name)}
                      </div>
                      <div className="flex-1 min-w-0">
                        <h3 className="font-bold text-sm text-foreground truncate">{agent.name}</h3>
                        <p className="text-[11px] text-muted">{agent.category} · {agent.model}</p>
                      </div>
                    </div>
                    <p className="text-xs text-muted leading-relaxed mb-4 line-clamp-2">{agent.description}</p>
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-3 text-xs text-muted">
                        <span className="flex items-center gap-1"><Star className="w-3 h-3 text-yellow-400 fill-yellow-400" />{agent.stars}</span>
                        <span className="flex items-center gap-1"><Download className="w-3 h-3" />{agent.uses}</span>
                      </div>
                      <button className="px-3 py-1 rounded-full border border-border text-xs font-semibold text-muted hover:border-accent hover:text-accent transition-colors">
                        Add
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}

        {filtered.length === 0 && (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div className="text-4xl mb-4">🔍</div>
            <h3 className="font-semibold text-foreground">No agents found</h3>
            <p className="text-sm text-muted mt-1">Try a different search or category.</p>
          </div>
        )}
      </div>
    </div>
  );
}
