"use client";

import React, { useState } from "react";
import { useEventBiases } from "@/hooks/useDashboard";
import { apiClient } from "@/lib/api-client";
import { AlertTriangle, TrendingDown, TrendingUp, ShieldAlert, Clock, XCircle, CheckCircle2, RefreshCw } from "lucide-react";
import { cn } from "@/lib/utils";

export default function ActiveEventBiasesCard() {
  const { biases, isLoading, mutate } = useEventBiases();
  const [dismissingId, setDismissingId] = useState<string | null>(null);

  const handleDismiss = async (id: string) => {
    try {
      setDismissingId(id);
      await apiClient.post(`/api/v1/dashboard/event-biases/${id}/dismiss`, {});
      await mutate();
    } catch (err) {
      console.error("Failed to dismiss event bias:", err);
    } finally {
      setDismissingId(null);
    }
  };

  const macro = biases?.macro || { stress_index: 0, extra_cash_reserve_ratio: 0, events: [] };
  const micro = biases?.micro || {};
  const microTickers = Object.keys(micro);
  const totalActive = biases?.total_active_events || 0;

  return (
    <div className="bg-surface-container-low rounded-[2rem] shadow-lg border border-outline-variant/10 overflow-hidden flex flex-col transition-all hover:shadow-xl p-6 sm:p-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-6 border-b border-outline-variant/10 gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
            <ShieldAlert size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-headline font-bold text-xl text-on-surface">即時事件量化偏置監控</h3>
              <span className={cn(
                "text-[10px] font-mono font-bold px-2 py-0.5 rounded-full uppercase tracking-wider",
                totalActive > 0 ? "bg-amber-500/10 text-amber-500 border border-amber-500/20" : "bg-emerald-500/10 text-emerald-500 border border-emerald-500/20"
              )}>
                {totalActive > 0 ? `${totalActive} 項偏置生效中` : "中性常態運作"}
              </span>
            </div>
            <p className="text-xs text-on-surface-variant font-light mt-0.5">
              個經標的與總經系統性事件時間衰減閉環，即時微調買賣信心分與現金防禦率。
            </p>
          </div>
        </div>

        <button
          onClick={() => mutate()}
          disabled={isLoading}
          className="self-start sm:self-auto flex items-center gap-1.5 px-3 py-1.5 bg-surface-container-high hover:bg-surface-container-highest text-on-surface rounded-lg text-xs font-mono transition-all disabled:opacity-50"
          title="重新整理偏置狀態"
        >
          <RefreshCw size={12} className={cn(isLoading && "animate-spin")} />
          <span>刷新</span>
        </button>
      </div>

      {/* Content */}
      <div className="pt-6 space-y-6">
        {/* 總經軌道 (Macro Section) */}
        <div className="p-4 sm:p-5 rounded-2xl bg-surface-container border border-outline-variant/10">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-3">
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold uppercase tracking-wider text-secondary">
                🌐 總經軌道 (Macroeconomic Systemic Guard)
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs font-mono">
              <div className="flex items-center gap-1.5">
                <span className="text-on-surface-variant">壓力指數:</span>
                <span className={cn(
                  "font-bold px-2 py-0.5 rounded",
                  macro.stress_index < 0 ? "bg-red-500/10 text-red-500" : macro.stress_index > 0 ? "bg-emerald-500/10 text-emerald-500" : "bg-surface-container-highest text-on-surface-variant"
                )}>
                  {macro.stress_index > 0 ? `+${macro.stress_index.toFixed(2)}` : macro.stress_index.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="text-on-surface-variant">額外現金防禦:</span>
                <span className="font-bold text-primary font-mono">
                  +{(macro.extra_cash_reserve_ratio * 100).toFixed(1)}%
                </span>
              </div>
            </div>
          </div>

          {macro.events && macro.events.length > 0 ? (
            <div className="space-y-2 mt-3">
              {macro.events.map((evt: any) => (
                <div key={evt.id} className="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-xl bg-surface-container-high/60 border border-outline-variant/10 text-xs gap-2">
                  <div className="flex items-start sm:items-center gap-2">
                    <span className="text-amber-500 shrink-0 mt-0.5 sm:mt-0">⚡</span>
                    <span className="font-medium text-on-surface">{evt.headline}</span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-surface-container-highest text-on-surface-variant font-mono">
                      {evt.category}
                    </span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 self-end sm:self-auto font-mono text-[11px]">
                    <span className="flex items-center gap-1 text-on-surface-variant">
                      <Clock size={11} />
                      剩餘 ~{evt.remaining_hours}h
                    </span>
                    <span className="text-red-500 font-bold">
                      {evt.current_impact > 0 ? `+${evt.current_impact.toFixed(2)}` : evt.current_impact.toFixed(2)}
                    </span>
                    <button
                      onClick={() => handleDismiss(evt.id)}
                      disabled={dismissingId === evt.id}
                      className="text-on-surface-variant hover:text-red-500 transition-colors p-1"
                      title="手動撤銷此總經偏置"
                    >
                      <XCircle size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs text-on-surface-variant/70 italic mt-1 font-light">
              無系統性總經壓力事件，未觸發額外現金保留。
            </p>
          )}
        </div>

        {/* 個經軌道 (Micro Section) */}
        <div className="p-4 sm:p-5 rounded-2xl bg-surface-container border border-outline-variant/10">
          <div className="flex items-center justify-between mb-3">
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-primary">
              📈 個經軌道 (Microeconomic Ticker-Specific Biases)
            </span>
            <span className="text-xs text-on-surface-variant font-mono">
              影響上限: ±1.5 pt
            </span>
          </div>

          {microTickers.length > 0 ? (
            <div className="space-y-3 mt-2">
              {microTickers.map((ticker) => {
                const events = micro[ticker] || [];
                const netBias = events.reduce((sum: number, e: any) => sum + (e.current_impact || 0), 0);
                return (
                  <div key={ticker} className="p-3.5 rounded-xl bg-surface-container-high/60 border border-outline-variant/10 space-y-2">
                    <div className="flex items-center justify-between border-b border-outline-variant/10 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-on-surface font-mono">{ticker}</span>
                        <span className={cn(
                          "text-[10px] font-mono font-bold px-2 py-0.5 rounded",
                          netBias < 0 ? "bg-red-500/10 text-red-500" : "bg-emerald-500/10 text-emerald-500"
                        )}>
                          淨偏置: {netBias > 0 ? `+${netBias.toFixed(2)}` : netBias.toFixed(2)} pt
                        </span>
                      </div>
                      <span className="text-[11px] text-on-surface-variant font-mono">
                        {events.length} 則事件作用中
                      </span>
                    </div>

                    <div className="space-y-1.5 pt-1">
                      {events.map((evt: any) => (
                        <div key={evt.id} className="flex flex-col sm:flex-row sm:items-center justify-between text-xs gap-2 py-1">
                          <div className="flex items-center gap-2">
                            {evt.current_impact < 0 ? (
                              <TrendingDown size={13} className="text-red-500 shrink-0" />
                            ) : (
                              <TrendingUp size={13} className="text-emerald-500 shrink-0" />
                            )}
                            <span className="text-on-surface font-light">{evt.headline}</span>
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-surface-container-highest text-on-surface-variant font-mono">
                              {evt.category}
                            </span>
                          </div>
                          <div className="flex items-center gap-3 shrink-0 self-end sm:self-auto font-mono text-[11px]">
                            <span className="flex items-center gap-1 text-on-surface-variant">
                              <Clock size={11} />
                              ~{evt.remaining_hours}h
                            </span>
                            <span className={cn("font-bold", evt.current_impact < 0 ? "text-red-500" : "text-emerald-500")}>
                              {evt.current_impact > 0 ? `+${evt.current_impact.toFixed(2)}` : evt.current_impact.toFixed(2)}
                            </span>
                            <button
                              onClick={() => handleDismiss(evt.id)}
                              disabled={dismissingId === evt.id}
                              className="text-on-surface-variant hover:text-red-500 transition-colors p-1"
                              title={`手動撤銷 ${ticker} 此項偏置`}
                            >
                              <XCircle size={14} />
                            </button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="py-4 flex items-center gap-2 text-xs text-on-surface-variant/70 italic font-light">
              <CheckCircle2 size={14} className="text-emerald-500/80" />
              <span>所有持有與觀察標的均無負面/正面事件偏置，評分完全依據基本面與量化技術因子中性評估。</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
