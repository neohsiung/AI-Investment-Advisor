"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";
import { Target, AlertTriangle } from "lucide-react";

type NetAlpha = {
  lookback_days: number;
  portfolio_return_pct: number;
  spy_return_pct: number;
  gross_alpha_pct: number;
  llm_cost_usd: number;
  saas_subscription_cost_usd: number;
  cost_drag_pct: number;
  net_alpha_pct: number;
  annualized_net_alpha_pct: number;
  target_annual_alpha_pct: number;
  alpha_target_gap_pct: number;
  is_beating_target: boolean;
  return_method: string;
  twr_days_used: number;
  excluded_days: string[];
  annualization_reliable: boolean;
  avg_equity_usd: number;
  data_quality_notes: string[];
};

const pct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`;

// Single success metric: net-of-cost excess return over SPY (target +10%/yr).
// 唯一成功指標：扣除模型與訂閱成本後相對 SPY 的超額報酬（目標年化 +10%）。
export default function NetAlphaCard({ lookbackDays = 30 }: { lookbackDays?: number }) {
  const { data, error } = useSWR(
    `/api/v1/net-alpha?lookback_days=${lookbackDays}`,
    fetcher,
    { refreshInterval: 300_000 },
  );
  const d: NetAlpha | undefined = data?.data;

  if (error) {
    return (
      <div className="bg-surface-container-low p-6 rounded-2xl border border-error/30 mb-6 lg:mb-8">
        <p className="text-[10px] font-black uppercase text-error tracking-widest">淨 Alpha 載入失敗</p>
        <p className="text-xs text-on-surface-variant mt-1">{error?.response?.data?.detail || error?.message}</p>
      </div>
    );
  }
  if (!d) {
    return <div className="h-32 mb-6 lg:mb-8 rounded-2xl bg-surface-variant/10 animate-pulse" />;
  }

  const reliable = d.annualization_reliable;
  return (
    <div className="bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10 shadow-sm mb-6 lg:mb-8">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-headline font-bold text-lg tracking-tight flex items-center gap-2">
          <Target size={18} /> 淨 Alpha <span className="text-xs text-on-surface-variant font-label uppercase tracking-widest">vs SPY · {d.lookback_days}D</span>
        </h3>
        <span className={cn("text-[10px] font-black uppercase tracking-widest px-2 py-1 rounded-md",
          d.is_beating_target ? "bg-secondary/20 text-secondary" : "bg-error/10 text-error")}>
          {d.is_beating_target ? "達標" : reliable ? "未達標" : "資料不足"}
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <Stat label="投組報酬 (TWR)" value={pct(d.portfolio_return_pct)} />
        <Stat label="SPY" value={pct(d.spy_return_pct)} />
        <Stat label="毛 Alpha" value={pct(d.gross_alpha_pct)} />
        <Stat label="成本拖累" value={pct(-d.cost_drag_pct)} sub={`LLM ${formatCurrency(d.llm_cost_usd)} + 訂閱 ${formatCurrency(d.saas_subscription_cost_usd)}`} />
        <Stat label="淨 Alpha" value={pct(d.net_alpha_pct)} sub={reliable ? `年化 ${pct(d.annualized_net_alpha_pct)}（目標 ${d.target_annual_alpha_pct.toFixed(0)}%）` : "年化不可靠"} strong />
      </div>
      {(d.data_quality_notes.length > 0 || d.return_method !== "twr_snapshots") && (
        <div className="mt-4 flex gap-2 text-[11px] text-on-surface-variant">
          <AlertTriangle size={14} className="shrink-0 mt-0.5 text-tertiary" />
          <ul className="space-y-0.5">
            <li>報酬算法：{d.return_method === "twr_snapshots" ? `時間加權 (${d.twr_days_used} 有效日)` : "單點報酬（備援，非 TWR）"}</li>
            {d.data_quality_notes.map((n) => <li key={n}>{n}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

function Stat({ label, value, sub, strong }: { label: string; value: string; sub?: string; strong?: boolean }) {
  return (
    <div>
      <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest mb-1">{label}</p>
      <p className={cn("font-bold font-headline tracking-tight", strong ? "text-2xl text-primary" : "text-xl")}>{value}</p>
      {sub && <p className="text-[10px] text-on-surface-variant/75 mt-1">{sub}</p>}
    </div>
  );
}
