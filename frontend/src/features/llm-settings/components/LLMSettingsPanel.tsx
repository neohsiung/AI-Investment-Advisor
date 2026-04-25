"use client";

import React, { useState } from "react";
import { Server, Database, Layers, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { ProvidersTab } from "./tabs/ProvidersTab";
import { ModelsTab } from "./tabs/ModelsTab";
import { TierBindingsTab } from "./tabs/TierBindingsTab";
import { AgentOverridesTab } from "./tabs/AgentOverridesTab";

// ─── Tab definitions ──────────────────────────────────────────────────────────

type LLMTabId = "providers" | "models" | "tiers" | "agents";

interface LLMTab {
    id: LLMTabId;
    label: string;
    icon: React.ElementType;
    badge?: string;
}

const LLM_TABS: LLMTab[] = [
    { id: "providers", label: "Providers", icon: Server },
    { id: "models", label: "Models", icon: Database },
    { id: "tiers", label: "Tier Bindings", icon: Layers, badge: "Phase B" },
    { id: "agents", label: "Agent Overrides", icon: Bot, badge: "Phase C" },
];

// ─── Panel ────────────────────────────────────────────────────────────────────

export function LLMSettingsPanel() {
    const [activeTab, setActiveTab] = useState<LLMTabId>("providers");

    return (
        <div className="space-y-6">
            {/* Inner tab bar */}
            <div className="flex items-center gap-1 bg-surface-container rounded-2xl p-1.5 border border-outline-variant/10">
                {LLM_TABS.map((tab) => {
                    const Icon = tab.icon;
                    const isActive = activeTab === tab.id;
                    return (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={cn(
                                "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold transition-all flex-1 justify-center relative",
                                isActive
                                    ? "bg-surface-container-high shadow-sm text-on-surface border border-outline-variant/10"
                                    : "text-on-surface-variant/60 hover:text-on-surface-variant hover:bg-surface-container-high/50"
                            )}
                        >
                            <Icon size={15} />
                            <span className="hidden sm:inline">{tab.label}</span>
                            {tab.badge && (
                                <span className="hidden md:inline text-[9px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded-md bg-surface-container-highest text-on-surface-variant/40 border border-outline-variant/20 ml-1">
                                    {tab.badge}
                                </span>
                            )}
                        </button>
                    );
                })}
            </div>

            {/* Tab content */}
            <div className="animate-in fade-in slide-in-from-bottom-2 duration-300">
                {activeTab === "providers" && <ProvidersTab />}
                {activeTab === "models" && <ModelsTab />}
                {activeTab === "tiers" && <TierBindingsTab />}
                {activeTab === "agents" && <AgentOverridesTab />}
            </div>
        </div>
    );
}
