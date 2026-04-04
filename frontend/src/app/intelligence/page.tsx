"use client";

import React from "react";
import useSWR, { mutate } from "swr";
import BriefingCard from "@/components/ui/BriefingCard";
import { useIntelligenceBriefing } from "@/hooks/useDashboard";
import { useRequireAuth } from "@/hooks/useAuth";
import { Loader2, RefreshCw, Zap } from "lucide-react";
import { cn, formatCurrency } from "@/lib/utils";

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
          <h1 className="text-5xl font-black font-headline tracking-tighter text-on-surface">市場情報簡報</h1>
          <p className="mt-4 text-on-surface-variant font-light text-lg max-w-2xl leading-relaxed">
            整合即時市場數據與 AI 分析的機構級投資情報，為您的資產配置提供戰略指引。
          </p>
        </div>
        <div className="text-right flex flex-col items-end gap-3">
          <button 
            onClick={() => mutate("/api/dashboard/intelligence")}
            className="flex items-center gap-2 px-4 py-2 bg-surface-container-high rounded-lg text-[10px] font-black uppercase hover:bg-primary hover:text-on-primary transition-all group"
          >
            <RefreshCw size={12} className="group-active:rotate-180 transition-transform" />
            重新生成情報
          </button>
          <div>
            <p className="font-label text-[10px] uppercase font-bold text-on-surface-variant mb-1">觀測狀態</p>
            <p className="font-headline font-bold text-xl text-primary">{briefing.observation_window || "ACTIVE SESSION"}</p>
          </div>
        </div>
      </div>

      {/* Primary Insights Grid */}
      <div className="grid grid-cols-12 gap-8">
        <div className="col-span-12 lg:col-span-8">
          <BriefingCard 
            title="核心摘要：戰略判斷與市場解構"
            tags={["High Priority", "Strategic Intelligence"]}
          >
            <div className="prose prose-sm max-w-none text-on-surface leading-loose">
              <p className="text-lg font-light">{briefing.executive_summary}</p>
              
              <div className="mt-8 p-8 bg-primary/5 rounded-[2rem] border-l-4 border-primary shadow-sm">
                <div className="flex items-center gap-2 mb-4">
                  <Zap size={18} className="text-primary" />
                  <h4 className="font-black font-label text-[10px] uppercase tracking-widest text-primary italic">CIO 行動指引 (Actionable Recommendation)</h4>
                </div>
                <p className="font-headline font-bold text-xl text-on-surface leading-snug">
                  {briefing.recommendation}
                </p>
              </div>
            </div>
          </BriefingCard>
        </div>

        <div className="col-span-12 lg:col-span-4 space-y-8">
          <BriefingCard title="市場情緒動能 (Sentiment)">
            <div className="space-y-6">
              {briefing.sentiment_metrics && briefing.sentiment_metrics.length > 0 ? briefing.sentiment_metrics.map((item: any) => (
                <div key={item.label}>
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-[10px] font-label uppercase font-bold text-on-surface-variant tracking-widest">{item.label}</span>
                    <span className="text-sm font-bold text-on-surface">{item.value}%</span>
                  </div>
                  <div className="h-2 w-full bg-surface-container-highest rounded-full overflow-hidden">
                    <div className={cn("h-full transition-all duration-1000", item.color)} style={{ width: `${item.value}%` }}></div>
                   </div>
                </div>
              )) : (
                <p className="text-[10px] text-center opacity-30 py-8">正在生成情緒指標...</p>
              )}
            </div>
          </BriefingCard>

          <div className="p-8 bg-surface-container-high rounded-[2rem] border border-outline-variant/10 relative group hover:shadow-lg transition-all">
            <span className="material-symbols-outlined absolute right-8 top-8 text-primary/20 text-5xl transform group-hover:rotate-12 transition-transform">
              psychology
            </span>
            <p className="font-label text-[10px] uppercase font-black tracking-[0.2em] text-primary mb-4">Alpha AI 觀察筆記</p>
            <p className="text-sm text-on-surface font-light leading-relaxed italic">
              「{briefing.ai_note}」
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
