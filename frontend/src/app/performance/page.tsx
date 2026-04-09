"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";
import { 
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, AreaChart, Area,
  BarChart, Bar, Cell, Legend
} from 'recharts';
import { TrendingUp, TrendingDown, Target, Zap, ShieldAlert, BarChart3, Clock } from "lucide-react";

export default function PerformancePage() {
  const { data: summaryData } = useSWR("/api/dashboard/summary", fetcher);
  const { data: historyData, isLoading: historyLoading } = useSWR("/api/dashboard/performance/history", fetcher);
  const { data: agentData } = useSWR("/api/dashboard/performance/agents", fetcher);

  const summary = summaryData?.data || {};
  const history = historyData?.data || [];
  const agents = agentData?.data || [];

  return (
    <div className="flex-1 flex flex-col p-8 pt-24 overflow-y-auto bg-background">
      {/* Header */}
      <div className="flex justify-between items-end mb-8">
        <div>
          <h1 className="text-4xl font-bold font-headline tracking-tighter mb-2">績效追蹤 <span className="text-primary/50 text-2xl">Performance</span></h1>
          <p className="text-on-surface-variant font-label text-xs uppercase tracking-[0.3em]">歷史數據重建與策略歸因分析</p>
        </div>
        <div className="flex gap-4">
          <div className="bg-surface-container-high px-4 py-2 rounded-lg border border-outline-variant/10 text-right">
            <p className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest mb-1">24H 變化</p>
            <p className="text-sm font-bold text-secondary font-mono">{summary.performance_change || "+0.00%"}</p>
          </div>
        </div>
      </div>

      {/* Metric Grid */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div className="bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10 group hover:border-primary/30 transition-all duration-300 shadow-sm relative overflow-hidden">
          <div className="absolute -right-4 -top-4 opacity-5 group-hover:opacity-10 transition-opacity">
            <TrendingUp size={100} />
          </div>
          <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest mb-1">資產淨值 (NLV)</p>
          <p className="text-2xl font-bold font-headline tracking-tight">{formatCurrency(summary.total_valuation || 0)}</p>
          <div className="flex items-center gap-2 mt-4 text-[10px] font-bold text-secondary">
             <Clock size={12} />
             <span>REAL-TIME FEED</span>
          </div>
        </div>

        <div className="bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10 group hover:border-secondary/30 transition-all duration-300 shadow-sm relative overflow-hidden">
          <div className="absolute -right-4 -top-4 opacity-5 group-hover:opacity-10 transition-opacity">
            <Zap size={100} />
          </div>
          <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest mb-1">目前槓桿 (Lev)</p>
          <p className="text-2xl font-bold font-headline tracking-tight text-secondary">{(summary.leverage_ratio || 0).toFixed(2)}x</p>
          <div className="mt-4 h-1 w-full bg-outline-variant/20 rounded-full overflow-hidden">
            <div className="h-full bg-secondary" style={{ width: `${Math.min((summary.leverage_ratio || 0) * 40, 100)}%` }}></div>
          </div>
        </div>

        <div className="bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10 group hover:border-tertiary/30 transition-all duration-300 shadow-sm relative overflow-hidden">
          <div className="absolute -right-4 -top-4 opacity-5 group-hover:opacity-10 transition-opacity">
            <BarChart3 size={100} />
          </div>
          <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest mb-1">總投報率 (ROI)</p>
          <p className="text-2xl font-bold font-headline tracking-tight text-primary">{(summary.roi_percentage || 0).toFixed(2)}%</p>
          <p className={cn("text-[10px] font-bold mt-4", (summary.total_pnl || 0) >= 0 ? "text-secondary" : "text-error")}>
             {formatCurrency(summary.total_pnl || 0)} P/L
          </p>
        </div>

        <div className="bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10 group shadow-sm relative overflow-hidden">
          <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest mb-1">風險狀態</p>
          <p className="text-2xl font-bold font-headline tracking-tight text-tertiary uppercase">{summary.risk_exposure || "MODERATE"}</p>
          <div className="flex items-center gap-2 mt-4 text-[10px] font-bold text-tertiary">
             <ShieldAlert size={12} />
             <span>SYSTEM GUARD ACTIVE</span>
          </div>
        </div>
      </div>

      {/* Charts Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 mb-8">
        {/* Main Growth Chart */}
        <div className="lg:col-span-2 bg-surface-container-low p-8 rounded-3xl border border-outline-variant/10 shadow-sm">
          <div className="flex justify-between items-center mb-8">
            <h3 className="font-headline font-bold text-lg tracking-tight">資產成長曲線 <span className="text-xs text-on-surface-variant font-label uppercase tracking-widest ml-4">Historical NLV Reconstructed</span></h3>
            <div className="flex gap-2">
               <button className="px-3 py-1 rounded-md bg-primary-container text-primary text-[10px] font-black uppercase tracking-widest">ALL</button>
               <button className="px-3 py-1 rounded-md hover:bg-surface-variant text-on-surface-variant text-[10px] font-black uppercase tracking-widest">30D</button>
               <button className="px-3 py-1 rounded-md hover:bg-surface-variant text-on-surface-variant text-[10px] font-black uppercase tracking-widest">7D</button>
            </div>
          </div>
          <div className="h-[350px] w-full">
            {historyLoading ? (
              <div className="h-full w-full flex items-center justify-center bg-surface-variant/10 rounded-xl animate-pulse">
                <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest">Reconstructing Ledger Data...</p>
              </div>
            ) : history.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={history}>
                  <defs>
                    <linearGradient id="colorNlv" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--md-sys-color-primary)" stopOpacity={0.1}/>
                      <stop offset="95%" stopColor="var(--md-sys-color-primary)" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(var(--md-sys-color-outline-variant-rgb), 0.1)" />
                  <XAxis 
                    dataKey="date" 
                    hide 
                  />
                  <YAxis 
                    tickFormatter={(val: number) => `$${val >= 1000 ? (val/1000).toFixed(1) + 'k' : val}`}
                    tick={{ fontSize: 10, fill: 'var(--md-sys-color-on-surface-variant)', fontWeight: 'bold' }}
                    axisLine={false}
                    tickLine={false}
                    domain={['auto', 'auto']}
                  />
                  <Tooltip 
                    contentStyle={{ backgroundColor: 'var(--md-sys-color-surface-container-highest)', border: 'none', borderRadius: '12px', fontSize: '10px', boxShadow: '0 4px 20px rgba(0,0,0,0.2)' }}
                    itemStyle={{ color: 'var(--md-sys-color-primary)', fontWeight: 'bold' }}
                    labelStyle={{ marginBottom: '4px', opacity: 0.6 }}
                  />
                  <Area type="monotone" dataKey="total_nlv" name="資產淨值" stroke="var(--md-sys-color-primary)" strokeWidth={3} fillOpacity={1} fill="url(#colorNlv)" />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full w-full flex items-center justify-center border-2 border-dashed border-outline-variant/20 rounded-xl bg-surface-variant/5">
                <p className="text-[10px] font-black uppercase text-on-surface-variant/30 tracking-widest">尚無歷史數據</p>
              </div>
            )}
          </div>
        </div>

        {/* Agent Leaderboard */}
        <div className="bg-surface-container-low p-8 rounded-3xl border border-outline-variant/10 shadow-sm flex flex-col">
          <h3 className="font-headline font-bold text-lg tracking-tight mb-8">Agent 歸因準確度</h3>
          <div className="flex-1 overflow-y-auto pr-2 space-y-6">
            {agents.length > 0 ? agents.map((agent: any) => (
              <div key={agent.agent} className="group">
                <div className="flex justify-between items-end mb-2">
                  <div>
                    <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest">{agent.agent}</p>
                    <p className="text-xs font-bold text-on-surface">{agent.recommendation_count} 個建議</p>
                  </div>
                  <p className={cn("text-lg font-bold font-mono tracking-tighter", agent.accuracy >= 70 ? "text-secondary" : agent.accuracy >= 50 ? "text-primary" : "text-error")}>
                    {agent.accuracy.toFixed(1)}%
                  </p>
                </div>
                <div className="h-1.5 w-full bg-surface-variant rounded-full overflow-hidden">
                   <div 
                    className={cn("h-full transition-all duration-1000", agent.accuracy >= 70 ? "bg-secondary" : agent.accuracy >= 50 ? "bg-primary" : "bg-error")} 
                    style={{ width: `${agent.accuracy}%` }}
                   ></div>
                </div>
              </div>
            )) : (
              <div className="h-full flex flex-col items-center justify-center opacity-30 gap-2">
                <Target size={32} />
                <p className="text-[10px] font-black uppercase tracking-widest">等待歸因數據...</p>
              </div>
            )}
          </div>
          <div className="mt-8 pt-6 border-t border-outline-variant/10">
             <p className="text-[9px] font-bold text-on-surface-variant uppercase tracking-widest leading-relaxed">
               歸因邏輯基於 72 小時建議視窗內的價格變動。
             </p>
          </div>
        </div>
      </div>

      {/* Secondary Chart Section */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <div className="bg-surface-container-low p-8 rounded-3xl border border-outline-variant/10 shadow-sm">
          <h3 className="font-headline font-bold text-lg tracking-tight mb-8">槓桿趨勢 <span className="text-[10px] font-label uppercase tracking-widest text-on-surface-variant ml-4">Exposure Ratio</span></h3>
          <div className="h-[200px] w-full">
             {history.length > 0 ? (
               <ResponsiveContainer width="100%" height="100%">
                 <BarChart data={history}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgba(var(--md-sys-color-outline-variant-rgb), 0.05)" />
                    <XAxis dataKey="date" hide />
                    <Tooltip 
                      contentStyle={{ backgroundColor: 'var(--md-sys-color-surface-container-highest)', border: 'none', borderRadius: '12px', fontSize: '10px' }}
                      cursor={{ fill: 'var(--md-sys-color-surface-variant)', opacity: 0.3 }}
                    />
                    <Bar dataKey="pnl" name="損益變化" fill="var(--md-sys-color-secondary)" radius={[2, 2, 0, 0]} />
                 </BarChart>
               </ResponsiveContainer>
             ) : (
               <div className="h-full w-full flex items-center justify-center bg-surface-variant/5 rounded-xl border border-dashed border-outline-variant/20 italic text-[10px] text-on-surface-variant/20">
                 Awaiting Data...
               </div>
             )}
          </div>
        </div>

        <div className="bg-surface-container-low p-8 rounded-3xl border border-outline-variant/10 shadow-sm">
          <h3 className="font-headline font-bold text-lg tracking-tight mb-8">累積報酬統計</h3>
          <div className="grid grid-cols-2 gap-4 h-[200px]">
            <div className="bg-surface-container px-4 py-8 rounded-2xl flex flex-col justify-center items-center">
                <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest mb-2">已實現損益</p>
                <p className="text-xl font-bold font-mono text-secondary">{formatCurrency(summary.realized_pnl || 0)}</p>
             </div>
             <div className="bg-surface-container px-4 py-8 rounded-2xl flex flex-col justify-center items-center">
                <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest mb-2">未實現損益</p>
                <p className="text-xl font-bold font-mono text-primary">{formatCurrency(summary.unrealized_pnl || 0)}</p>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}
