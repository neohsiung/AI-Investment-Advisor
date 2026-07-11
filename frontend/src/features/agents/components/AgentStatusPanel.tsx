"use client";

import React from "react";
import TacticalCard from "@/components/ui/TacticalCard";
import { useAgentsStatus } from "@/hooks/useDashboard";
import { cn } from "@/lib/utils";
import { Cpu, Zap, Target, Activity, Loader2 } from "lucide-react";

export function AgentStatusPanel() {
  const { agents, isLoading } = useAgentsStatus();

  if (isLoading) {
    return (
      <TacticalCard title="代理人營運狀態 (Agent Swarm Status)">
        <div className="flex justify-center p-8">
          <Loader2 className="h-6 w-6 animate-spin text-secondary" />
        </div>
      </TacticalCard>
    );
  }

  return (
    <TacticalCard 
      title="代理人營運狀態 (Agent Swarm Status)"
      accentColor="var(--secondary)"
    >
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-2 gap-4">
        {agents.map((agent: any) => (
          <div 
            key={agent.id} 
            className="p-4 rounded-lg bg-surface-container-low border border-outline-variant/10 hover:border-secondary/30 transition-all group"
          >
            <div className="flex justify-between items-start mb-3">
              <div className="flex items-center gap-2">
                <div className={cn("p-2 rounded-md bg-opacity-20", agent.color || "bg-primary")}>
                  <Cpu className="h-3 w-3 text-on-surface" />
                </div>
                <h4 className="font-headline font-bold text-xs tracking-tight text-on-surface group-hover:text-secondary transition-colors">
                  {agent.name}
                </h4>
              </div>
              <span className={cn(
                "px-2 py-0.5 rounded-full text-[9px] font-bold font-label uppercase tracking-wider",
                agent.status === "Active" || agent.status === "Optimizing" || agent.status === "Scanning" 
                  ? "bg-secondary/10 text-secondary" 
                  : "bg-on-surface-variant/10 text-on-surface-variant"
              )}>
                {agent.status}
              </span>
            </div>
            
            <div className="space-y-2 mt-4">
              <div className="flex justify-between items-center text-[10px] font-label uppercase tracking-widest text-on-surface-variant mb-1">
                 <span>算力策略</span>
                 <span className="text-on-surface font-bold opacity-100">{agent.strategy}</span>
              </div>
              
              <div className="space-y-1">
                 <div className="flex justify-between items-center text-[10px] font-label uppercase tracking-widest text-on-surface-variant">
                    <span>信心準確度 (Accuracy)</span>
                    <span className="text-secondary font-black">{agent.performance}</span>
                 </div>
                 <div className="h-1 w-full bg-surface-container rounded-full overflow-hidden">
                    <div 
                      className="h-full bg-secondary transition-all duration-1000" 
                      style={{ width: agent.performance?.includes('%') ? agent.performance.replace('+', '') : '80%' }}
                    ></div>
                 </div>
              </div>
              
              <div className="flex gap-4 pt-2">
                 <div className="flex items-center gap-1 opacity-50">
                    <Zap className="h-2.5 w-2.5" />
                    <span className="text-[8px] font-label font-bold uppercase">{agent.tier || "Standard"}</span>
                 </div>
                 <div className="flex items-center gap-1 opacity-50">
                    <Target className="h-2.5 w-2.5" />
                    <span className="text-[8px] font-label font-bold uppercase">{agent.recommendation_count || 0} 建議</span>
                 </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </TacticalCard>
  );
}
