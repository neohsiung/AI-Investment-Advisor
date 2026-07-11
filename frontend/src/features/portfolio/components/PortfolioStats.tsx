import React from "react";
import { Loader2, FileText, RefreshCw } from "lucide-react";
import { formatCurrency, cn } from "@/lib/utils";

interface PortfolioStatsProps {
  summary: any;
  isReporting: boolean;
  isRebalancing: boolean;
  onGenerateReport: () => void;
  onRebalance: () => void;
}

export function PortfolioStats({
  summary,
  isReporting,
  isRebalancing,
  onGenerateReport,
  onRebalance
}: PortfolioStatsProps) {
  return (
    <div className="grid grid-cols-12 gap-4 lg:gap-6 mb-6 lg:mb-8 items-center pt-4">
      <div className="col-span-12 lg:col-span-8">
        <div className="flex items-baseline gap-4 mb-2">
          <h1 className="text-4xl font-black font-headline tracking-tighter text-on-surface">
            核心投資組合
          </h1>
          <div className="flex items-center text-secondary font-label font-bold text-sm bg-secondary-container/20 px-2 py-0.5 rounded">
            <span className="material-symbols-outlined text-xs mr-1">trending_up</span>
            {"+2.4%"}
          </div>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-4">
          <StatItem label="資產淨值 (NLV)" value={formatCurrency(summary?.total_valuation || 0)} />
          <StatItem label="可用現金 (Cash)" value={formatCurrency(summary?.uninvested_cash || 0)} />
          <StatItem
            label="槓桿比率 (Lev)"
            value={`${(summary?.leverage_ratio || 0).toFixed(2)}x`}
            className="text-secondary"
          />
          <StatItem
            label="總投報率 (ROI)"
            value={`${(summary?.roi_percentage || 0).toFixed(2)}%`}
            className="text-primary"
          />
          <StatItem
            label="總損益 (P/L)"
            value={formatCurrency(summary?.total_pnl || 0)}
            className={(summary?.total_pnl || 0) >= 0 ? "text-secondary" : "text-error"}
          />
          <StatItem
            label="風險敞口"
            value={summary?.risk_exposure || "MODERATE"}
            className="text-tertiary uppercase"
          />
        </div>
      </div>
      <div className="col-span-12 lg:col-span-4 flex flex-wrap justify-start lg:justify-end gap-3">
        <button
          onClick={onGenerateReport}
          disabled={isReporting}
          className="flex items-center gap-2 bg-surface-container px-6 py-3 rounded-md font-label text-xs uppercase tracking-widest text-on-surface border border-outline-variant/10 hover:bg-surface-bright transition-all active:scale-95 disabled:opacity-50"
        >
          {isReporting ? <Loader2 className="h-3 w-3 animate-spin" /> : <FileText className="h-3 w-3" />}
          產出報告
        </button>
        <button
          onClick={onRebalance}
          disabled={isRebalancing}
          className="flex items-center gap-2 bg-gradient-to-r from-primary-container to-primary px-6 py-3 rounded-md font-label text-xs uppercase tracking-widest text-white shadow-lg active:scale-95 transition-all disabled:opacity-50"
        >
          {isRebalancing ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
          執行再平衡
        </button>
      </div>
    </div>
  );
}

function StatItem({ label, value, className }: { label: string, value: string, className?: string }) {
  return (
    <div className="flex-1 min-w-[140px]">
      <p className="font-label text-[10px] uppercase tracking-[0.2em] text-on-surface-variant mb-1">{label}</p>
      <p className={cn("text-xl font-bold font-headline tracking-tight", className)}>{value}</p>
    </div>
  );
}
