"use client";

import React from "react";
import BriefingCard from "@/components/ui/BriefingCard";
import { useIntelligenceBriefing } from "@/hooks/useDashboard";
import { useRequireAuth } from "@/hooks/useAuth";
import { Loader2 } from "lucide-react";

export default function IntelligenceBriefing() {
  const { briefing, isLoading } = useIntelligenceBriefing();
  const { isLoading: isAuthLoading } = useRequireAuth();

  if (isAuthLoading || isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-10 w-10 text-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto space-y-12 py-12 animate-in slide-in-from-bottom duration-700">
      {/* Header */}
      <div className="border-b border-outline-variant/10 pb-8 flex justify-between items-end">
        <div>
          <p className="text-secondary font-bold font-label text-xs uppercase tracking-[0.3em] mb-2">Alpha Intelligence Report</p>
          <h1 className="text-5xl font-black font-headline tracking-tighter text-on-surface">Intelligence Briefing</h1>
          <p className="mt-4 text-on-surface-variant font-light text-lg max-w-2xl leading-relaxed">
            Market-wide sentiment synthesis and strategic positioning for institutional-grade portfolio management.
          </p>
        </div>
        <div className="text-right">
          <p className="font-label text-[10px] uppercase font-bold text-on-surface-variant mb-1">Observation Window</p>
          <p className="font-headline font-bold text-xl">{briefing.observation_window || "ACTIVE SESSION"}</p>
        </div>
      </div>

      {/* Primary Insights Grid */}
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-8">
          <BriefingCard 
            title="Executive Summary: Tactical Pivot"
            tags={["High Priority", "Strategic"]}
          >
            <div className="prose prose-sm max-w-none text-on-surface leading-loose">
              <p>{briefing.executive_summary}</p>
              
              <div className="mt-8 p-6 bg-primary-container/10 rounded-lg border-l-4 border-primary">
                <h4 className="font-bold font-label text-[10px] uppercase tracking-widest text-primary mb-2 italic">Recommendation</h4>
                <p className="font-headline font-bold text-lg text-primary-container">
                  {briefing.recommendation}
                </p>
              </div>
            </div>
          </BriefingCard>
        </div>

        <div className="col-span-12 lg:col-span-4 space-y-8">
          <BriefingCard title="Strategic Sentiment">
            <div className="space-y-6">
              {(briefing.sentiment_metrics || []).map((item: any) => (
                <div key={item.label}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-[10px] font-label uppercase font-bold text-on-surface-variant">{item.label}</span>
                    <span className="text-sm font-bold text-on-surface">{item.value}%</span>
                  </div>
                  <div className="h-1.5 w-full bg-outline-variant/10 rounded-full overflow-hidden">
                    <div className={cn("h-full", item.color)} style={{ width: `${item.value}%` }}></div>
                   </div>
                </div>
              ))}
            </div>
          </BriefingCard>

          <div className="p-6 bg-surface-container-high rounded-xl border border-outline-variant/10 relative group hover:shadow-lg transition-all">
            <span className="material-symbols-outlined absolute right-6 top-6 text-primary/30 text-4xl transform group-hover:rotate-12 transition-transform">
              auto_awesome
            </span>
            <p className="font-label text-[10px] uppercase font-black tracking-widest text-primary mb-2">Alpha AI Note</p>
            <p className="text-sm text-on-surface font-light leading-relaxed">
              {briefing.ai_note}
            </p>
          </div>
        </div>
      </div>

      {/* Comparative Data Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
        {(briefing.stats || []).map((stat: any) => (
          <div key={stat.title} className="p-8 bg-surface-container-low border border-outline-variant/10 rounded-xl shadow-sm hover:shadow-md transition-shadow">
            <div className="flex justify-between items-start mb-4">
              <div className="p-3 bg-secondary-container/10 rounded-lg text-secondary">
                <span className="material-symbols-outlined text-2xl">{stat.icon}</span>
              </div>
              <span className={`text-xs font-bold ${stat.change.startsWith('+') ? 'text-secondary' : 'text-error'}`}>
                {stat.change}
              </span>
            </div>
            <p className="text-on-surface-variant font-label text-[10px] uppercase font-bold tracking-widest">{stat.title}</p>
            <p className="text-3xl font-black font-headline tracking-tighter mt-1 text-on-surface">{stat.value}</p>
          </div>
        ))}
      </div>
      
      {/* Footer Disclaimer/Signoff */}
      <div className="pt-12 border-t border-outline-variant/10 flex flex-col items-center">
        <div className="w-12 h-1 bg-primary/20 rounded-full mb-6"></div>
        <p className="text-[10px] font-label uppercase text-on-surface-variant text-center max-w-xl leading-relaxed opacity-50">
          Intelligence generated by the Sovereign Multi-Agent Swarm. This report is for architectural oversight and decision support only. Past performance does not guarantee future results.
        </p>
      </div>
    </div>
  );
}

// Helper function for conditional classes if not imported
function cn(...classes: any[]) {
  return classes.filter(Boolean).join(" ");
}
