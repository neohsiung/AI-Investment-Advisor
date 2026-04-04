"use client";

import React from "react";
import TacticalCard from "@/components/ui/TacticalCard";
import Terminal from "@/components/dashboard/Terminal";
import { usePortfolioSummary, useAgentsStatus, usePositions, useDashboardSocket, useAlerts } from "@/hooks/useDashboard";


import { useRequireAuth } from "@/hooks/useAuth";
import { cn, formatCurrency, formatPercentage } from "@/lib/utils";
import { Loader2 } from "lucide-react";

export default function CommandCenter() {
  const { summary, isLoading: isSummaryLoading } = usePortfolioSummary();
  const { agents, isLoading: isAgentsLoading } = useAgentsStatus();
  const { positions, isLoading: isPositionsLoading } = usePositions();
  const { status: socketStatus } = useDashboardSocket();
  const { isLoading: isAuthLoading } = useRequireAuth();
  const { alerts, isLoading: isAlertsLoading } = useAlerts();

  if (isAuthLoading || isSummaryLoading || isAgentsLoading || isPositionsLoading) {

    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-10 w-10 text-primary animate-spin" />
      </div>
    );
  }
  return (
    <div className="space-y-8 animate-in fade-in duration-700">
      {/* Dashboard Header / Overview Area */}
      <div className="grid grid-cols-12 gap-6 mb-8">
        <div className="col-span-12 lg:col-span-8">
          <div className="flex items-baseline gap-4 mb-2">
            <h1 className="text-4xl font-black font-headline tracking-tighter text-on-surface">核心投資組合</h1>
            <div className="flex items-center text-secondary font-label font-bold text-sm bg-secondary-container/20 px-2 py-0.5 rounded">
              <span className="material-symbols-outlined text-xs mr-1">trending_up</span>
              {summary.performance_change || "+0.0%"}
            </div>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-6">
            <div>
              <p className="font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant mb-1">資產淨值 (NLV)</p>
              <p className="text-xl font-bold font-headline tracking-tight">{formatCurrency(summary.total_valuation || 0)}</p>
            </div>
            <div>
              <p className="font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant mb-1">可用現金 (Cash)</p>
              <p className="text-xl font-bold font-headline tracking-tight">{formatCurrency(summary.uninvested_cash || 0)}</p>
            </div>
            <div>
              <p className="font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant mb-1">槓桿比率 (Lev)</p>
              <p className="text-xl font-bold font-headline tracking-tight text-secondary">{(summary.leverage_ratio || 0).toFixed(2)}x</p>
            </div>
            <div>
              <p className="font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant mb-1">總投報率 (ROI)</p>
              <p className="text-xl font-bold font-headline tracking-tight text-primary">{(summary.roi_percentage || 0).toFixed(2)}%</p>
            </div>
            <div>
              <p className="font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant mb-1">總損益 (P/L)</p>
              <p className={cn("text-xl font-bold font-headline tracking-tight", (summary.total_pnl || 0) >= 0 ? "text-secondary" : "text-error")}>
                {formatCurrency(summary.total_pnl || 0)}
              </p>
            </div>
            <div>
              <p className="font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant mb-1">風險敞口</p>
              <p className="text-xl font-bold font-headline tracking-tight text-tertiary uppercase">{summary.risk_exposure || "MODERATE"}</p>
            </div>
          </div>

        </div>
        <div className="col-span-12 lg:col-span-4 flex justify-end items-center gap-3">
          <button className="bg-surface-container px-6 py-3 rounded-md font-label text-xs uppercase tracking-widest text-on-surface border border-outline-variant/10 hover:bg-surface-bright transition-all active:scale-95">
            產出報告
          </button>
          <button className="bg-gradient-to-r from-primary-container to-primary px-6 py-3 rounded-md font-label text-xs uppercase tracking-widest text-white shadow-lg active:scale-95 transition-all">
            執行再平衡
          </button>
        </div>

      </div>

      {/* Bento Grid Layout */}
      <div className="grid grid-cols-12 gap-6">
        {/* Performance Chart */}
        <div className="col-span-12 lg:col-span-9">
          <TacticalCard 
            title="資產績效表現趨勢"
            className="h-full"
          >
            <div className="flex justify-between items-center mb-8 absolute top-6 right-6">
              <div className="flex gap-2">
                {[
                  { key: "1H", label: "1小時" },
                  { key: "24H", label: "24小時" },
                  { key: "7D", label: "7天" },
                  { key: "1M", label: "1月" }
                ].map((item) => (
                  <button 
                    key={item.key}
                    className={`text-[10px] font-label uppercase tracking-widest px-3 py-1 rounded transition-colors ${
                      item.key === "1H" ? "bg-surface-container-highest text-primary" : "text-on-surface-variant hover:text-on-surface"
                    }`}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            
            <div className="h-64 w-full flex items-end gap-1 relative mt-4">
              {/* Mock SVG Chart */}
              <svg className="absolute inset-0 w-full h-full pointer-events-none" preserveAspectRatio="none">
                <defs>
                  <linearGradient id="chartGradient" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--primary)" stopOpacity="0.3"></stop>
                    <stop offset="100%" stopColor="var(--primary)" stopOpacity="0"></stop>
                  </linearGradient>
                </defs>
                <path 
                  d="M0 180 Q 100 160 200 190 T 400 140 T 600 160 T 800 100 T 1000 120" 
                  fill="none" 
                  stroke="var(--primary)" 
                  strokeWidth="2"
                ></path>
                <path 
                  d="M0 180 Q 100 160 200 190 T 400 140 T 600 160 T 800 100 T 1000 120 V 256 H 0 Z" 
                  fill="url(#chartGradient)"
                ></path>
                <circle cx="800" cy="100" fill="var(--primary)" r="4"></circle>
                <circle className="animate-ping" cx="800" cy="100" fill="none" r="12" stroke="var(--primary)" strokeOpacity="0.3"></circle>
              </svg>
              
              {/* Grid Lines */}
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex-1 h-full border-r border-outline-variant/5"></div>
              ))}
            </div>
            
            <div className="flex justify-between mt-4 font-label text-[10px] text-on-surface-variant uppercase tracking-widest">
              <span>08:00 UTC</span>
              <span>10:00 UTC</span>
              <span>12:00 UTC</span>
              <span>14:00 UTC</span>
              <span>16:00 UTC</span>
            </div>
          </TacticalCard>
        </div>

        {/* Real-time Market Sentiment */}
        <div className="col-span-12 lg:col-span-3 space-y-6">
          <TacticalCard title="市場情緒指數" accentColor="var(--secondary)">
            <div className="relative h-4 w-full bg-surface-container-highest rounded-full overflow-hidden mb-3">
              <div className="absolute h-full w-[68%] bg-gradient-to-r from-secondary-container to-secondary rounded-full"></div>
            </div>
            <div className="flex justify-between items-center">
              <span className="font-label text-[10px] uppercase text-on-surface-variant">多頭強度</span>
              <span className="font-headline font-bold text-secondary">68%</span>
            </div>
          </TacticalCard>

          <TacticalCard title="AI 即時決策策略" accentColor="var(--primary)">
            <p className="text-sm font-light text-on-surface leading-relaxed">
              偵測到 <span className="font-mono text-primary bg-primary/10 px-1">USDT-PAIR</span> 波動激增。代理人正在轉向 <span className="italic">Delta-Neutral</span> 對沖狀態。
            </p>
            <div className="mt-4 flex items-center justify-between text-[10px] font-label text-on-surface-variant uppercase tracking-tighter">
              <span>信賴指標</span>
              <span className="text-on-surface font-bold">94.2%</span>
            </div>
          </TacticalCard>
        </div>
      </div>

      {/* Phase 5: Interactive Command Mesh & Agent Status */}
      <div className="grid grid-cols-12 gap-6">
        <div className="col-span-12 lg:col-span-8 space-y-6">
          <div className="animate-in fade-in slide-in-from-bottom-4 duration-1000 delay-300">
            <Terminal />
          </div>

          <TacticalCard title="目前持倉與行動指引 (Positions & Action Guidelines)">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-surface-container-highest/30">
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">資產 (Ticker)</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">數量 (Qty)</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">市價 (Price)</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">槓桿 (Lev)</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">總價值 (Gross)</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">淨權益 (Equity)</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold text-center">損益 (P/L)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/10 text-sm">
                  {positions.length > 0 ? (
                    positions.map((pos: any) => (
                      <tr key={pos.ticker} className="hover:bg-surface-bright/50 transition-colors">
                        <td className="py-4 px-4 font-bold font-mono tracking-tight">{pos.ticker}</td>
                        <td className="py-4 px-4 font-mono">{pos.quantity?.toFixed(4)}</td>
                        <td className="py-4 px-4 font-mono">{formatCurrency(pos.current_price)}</td>
                        <td className="py-4 px-4 font-mono">{pos.leverage?.toFixed(1)}x</td>
                        <td className="py-4 px-4 font-mono">{formatCurrency(pos.gross_mv)}</td>
                        <td className="py-4 px-4 font-mono">{formatCurrency(pos.net_equity)}</td>
                        <td className="py-4 px-4 text-center">
                          <span className={cn(
                            "px-3 py-1 rounded-full text-[10px] font-bold font-label uppercase tracking-wider shadow-sm border",
                            (pos.unrealized_pnl || 0) >= 0 ? 'bg-secondary/10 text-secondary border-secondary/20' : 'bg-error/10 text-error border-error/20'
                          )}>
                            {formatCurrency(pos.unrealized_pnl || 0)}
                          </span>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} className="py-12 text-center text-on-surface-variant font-label text-[10px] uppercase tracking-widest opacity-50 italic">
                        等待數據源掃描中...
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </TacticalCard>

          <TacticalCard title="帳戶代理人營運狀態">
            <div className="overflow-x-auto">
              <table className="w-full text-left">
                <thead>
                  <tr className="bg-surface-container-highest/30">
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">代理人 ID</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">策略</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">24h 績效</th>
                    <th className="py-3 px-4 font-label text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">狀態</th>
                  </tr>
                </thead>

                <tbody className="divide-y divide-outline-variant/10 text-sm">
                  {agents.map((agent: any) => (
                    <tr key={agent.id} className="hover:bg-surface-bright/50 transition-colors group">
                      <td className="py-4 px-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-sm bg-surface-container-highest flex items-center justify-center">
                            <span className="material-symbols-outlined text-sm text-primary">psychology</span>
                          </div>
                          <div>
                            <p className="font-bold text-sm tracking-tight">{agent.id}</p>
                            <p className="text-[10px] text-on-surface-variant font-mono">{agent.name}</p>
                          </div>
                        </div>
                      </td>
                      <td className="py-4 px-4">
                        <span className="text-xs font-label uppercase text-on-surface">{agent.strategy}</span>
                      </td>
                      <td className="py-4 px-4 font-mono text-secondary text-sm font-bold">{agent.performance}</td>
                      <td className="py-4 px-4">
                        <div className="flex items-center gap-2">
                          <span className={`w-2 h-2 rounded-full ${agent.color} ${agent.status === 'Optimizing' ? 'pulse-glow' : ''}`}></span>
                          <span className="text-[10px] font-label uppercase text-on-surface-variant font-bold">{agent.status}</span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </TacticalCard>
        </div>

        {/* System Alerts */}
        <div className="col-span-12 lg:col-span-4">
          <TacticalCard title="系統即時通知" accentColor="var(--tertiary)">
            <div className="space-y-4">
              {alerts.length > 0 ? alerts.map((alert: any, i: number) => (
                <div key={i} className={`p-4 bg-surface-container-low rounded-md border-l-2 border-primary`}>
                  <div className="flex justify-between items-start mb-1">
                    <p className="text-[10px] font-label uppercase tracking-widest text-primary font-bold">{alert.type}</p>
                    <span className="text-[10px] text-on-surface-variant font-mono">{alert.time}</span>
                  </div>
                  <p className="text-xs text-on-surface leading-snug">{alert.msg}</p>
                </div>
              )) : (
                <div className="py-12 text-center opacity-20 italic">
                   <p className="text-[10px] font-label uppercase tracking-widest">暫無系統事件</p>
                </div>
              )}
            </div>
            <button className="w-full mt-6 py-3 font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant hover:text-on-surface transition-all">
              封存所有通知
            </button>
          </TacticalCard>
        </div>
      </div>
    </div>
  );
}
