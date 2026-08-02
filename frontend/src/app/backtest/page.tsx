"use client";

import React, { useState } from "react";
import useSWR from "swr";
import api, { fetcher } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { PlayCircle, TrendingUp, TrendingDown, Percent, Target, History, Loader2 } from "lucide-react";

type BacktestRun = {
  id: string;
  ticker: string;
  strategy_name: string;
  initial_cash: number;
  final_cash: number;
  metrics: Record<string, number | null>;
  created_at: string;
};

type BacktestRunDetail = BacktestRun & {
  trades: Array<{
    entry_date: string; entry_price: number; exit_date: string | null;
    exit_price: number | null; exit_reason: string | null; pnl: number | null; pnl_pct: number | null;
  }>;
  equity_curve: Array<{ seq: number; date: string | null; equity: number }>;
};

function MetricTile({ label, value, suffix = "", positiveGood = true }: { label: string; value: number | null | undefined; suffix?: string; positiveGood?: boolean }) {
  const has = value !== null && value !== undefined && !Number.isNaN(value);
  const isGood = has ? (positiveGood ? (value as number) >= 0 : (value as number) < 0) : null;
  return (
    <div className="bg-surface-container-low p-4 rounded-xl border border-outline-variant/10">
      <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest mb-1">{label}</p>
      <p className={cn("text-lg font-bold font-mono", has ? (isGood ? "text-secondary" : "text-red-400") : "text-on-surface-variant")}>
        {has ? `${(value as number).toFixed(2)}${suffix}` : "—"}
      </p>
    </div>
  );
}

export default function BacktestPage() {
  const [ticker, setTicker] = useState("AAPL");
  const [fastMa, setFastMa] = useState(10);
  const [slowMa, setSlowMa] = useState(30);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);

  const { data: historyData, mutate: refetchHistory } = useSWR("/api/v1/backtest/history?limit=20", fetcher);
  const runs: BacktestRun[] = historyData?.runs || [];

  const { data: detailData, isLoading: detailLoading } = useSWR(
    selectedRunId ? `/api/v1/backtest/history/${selectedRunId}` : null,
    fetcher
  );
  const detail: BacktestRunDetail | undefined = detailData?.run;

  async function runBacktest() {
    setRunning(true);
    setRunError(null);
    try {
      const res = await api.post("/api/v1/backtest/run", {
        ticker: ticker.toUpperCase(),
        fast_ma: fastMa,
        slow_ma: slowMa,
      });
      await refetchHistory();
      setSelectedRunId(res.data.run_id);
    } catch (e: any) {
      setRunError(e?.response?.data?.detail || "回測執行失敗");
    } finally {
      setRunning(false);
    }
  }

  const equityChartData = (detail?.equity_curve || []).map((p) => ({
    date: p.date || `#${p.seq}`,
    equity: p.equity,
  }));

  return (
    <div className="flex-1 overflow-y-auto pt-16 sm:pt-20 lg:pt-24 px-4 sm:px-6 lg:px-8 pb-8 bg-background">
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4 mb-6 lg:mb-8">
        <div>
          <h1 className="text-2xl lg:text-4xl font-bold font-headline tracking-tighter mb-2">
            策略回測 <span className="text-primary/50 text-xl lg:text-2xl">Backtest</span>
          </h1>
          <p className="text-on-surface-variant font-label text-xs uppercase tracking-[0.3em]">
            事件驅動投組模擬（現金/手續費/停損/權益曲線）
          </p>
        </div>
      </div>

      {/* Run form */}
      <div className="bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10 mb-6 lg:mb-8">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <label className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest block mb-1">標的</label>
            <input
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              className="bg-surface-container-high border border-outline-variant/20 rounded-lg px-3 py-2 text-sm font-mono w-28"
              placeholder="AAPL"
            />
          </div>
          <div>
            <label className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest block mb-1">快速 MA</label>
            <input
              type="number" value={fastMa} onChange={(e) => setFastMa(Number(e.target.value))}
              className="bg-surface-container-high border border-outline-variant/20 rounded-lg px-3 py-2 text-sm font-mono w-20"
            />
          </div>
          <div>
            <label className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest block mb-1">慢速 MA</label>
            <input
              type="number" value={slowMa} onChange={(e) => setSlowMa(Number(e.target.value))}
              className="bg-surface-container-high border border-outline-variant/20 rounded-lg px-3 py-2 text-sm font-mono w-20"
            />
          </div>
          <button
            onClick={runBacktest}
            disabled={running || !ticker}
            className="flex items-center gap-2 bg-primary text-on-primary px-4 py-2 rounded-lg text-sm font-bold disabled:opacity-50"
          >
            {running ? <Loader2 size={16} className="animate-spin" /> : <PlayCircle size={16} />}
            {running ? "執行中..." : "執行回測"}
          </button>
        </div>
        {runError && <p className="text-red-400 text-xs mt-3">{runError}</p>}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* History list */}
        <div className="lg:col-span-1">
          <h2 className="text-sm font-bold uppercase tracking-widest text-on-surface-variant mb-3 flex items-center gap-2">
            <History size={14} /> 歷史紀錄
          </h2>
          <div className="space-y-2">
            {runs.length === 0 && (
              <p className="text-xs text-on-surface-variant">尚無回測紀錄，執行第一次回測吧。</p>
            )}
            {runs.map((r) => (
              <button
                key={r.id}
                onClick={() => setSelectedRunId(r.id)}
                className={cn(
                  "w-full text-left p-3 rounded-xl border transition-colors",
                  selectedRunId === r.id
                    ? "border-primary/50 bg-surface-container-high"
                    : "border-outline-variant/10 bg-surface-container-low hover:border-primary/30"
                )}
              >
                <div className="flex justify-between items-center">
                  <span className="font-mono font-bold text-sm">{r.ticker}</span>
                  <span className={cn("text-xs font-mono", r.final_cash >= r.initial_cash ? "text-secondary" : "text-red-400")}>
                    {formatCurrency(r.final_cash)}
                  </span>
                </div>
                <p className="text-[10px] text-on-surface-variant mt-1">{r.strategy_name} · {new Date(r.created_at).toLocaleString()}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Detail view */}
        <div className="lg:col-span-2">
          {detailLoading && <p className="text-xs text-on-surface-variant">載入中...</p>}
          {!detail && !detailLoading && (
            <div className="h-64 flex items-center justify-center text-on-surface-variant text-sm border border-dashed border-outline-variant/20 rounded-2xl">
              選擇左側的回測紀錄以檢視詳情
            </div>
          )}
          {detail && (
            <>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
                <MetricTile label="Sharpe" value={detail.metrics.sharpe} />
                <MetricTile label="Sortino" value={detail.metrics.sortino} />
                <MetricTile label="Calmar" value={detail.metrics.calmar} />
                <MetricTile label="CAGR" value={detail.metrics.cagr_pct} suffix="%" />
                <MetricTile label="最大回撤" value={detail.metrics.max_drawdown_pct} suffix="%" positiveGood={false} />
                <MetricTile label="勝率" value={detail.metrics.win_rate_pct} suffix="%" />
                <MetricTile label="期望值" value={detail.metrics.expectancy} />
                <MetricTile label="獲利因子" value={detail.metrics.profit_factor} />
              </div>

              <div className="bg-surface-container-low p-4 rounded-2xl border border-outline-variant/10 mb-6" style={{ height: 280 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityChartData}>
                    <defs>
                      <linearGradient id="equityGradient" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="var(--secondary)" stopOpacity={0.4} />
                        <stop offset="95%" stopColor="var(--secondary)" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.1} />
                    <XAxis dataKey="date" tick={{ fontSize: 10 }} minTickGap={40} />
                    <YAxis tick={{ fontSize: 10 }} domain={["auto", "auto"]} tickFormatter={(v) => formatCurrency(v)} width={80} />
                    <Tooltip formatter={(v: number) => formatCurrency(v)} />
                    <Area type="monotone" dataKey="equity" stroke="var(--secondary)" fill="url(#equityGradient)" strokeWidth={2} />
                  </AreaChart>
                </ResponsiveContainer>
              </div>

              <h3 className="text-sm font-bold uppercase tracking-widest text-on-surface-variant mb-3">交易紀錄 ({detail.trades.length})</h3>
              <div className="overflow-x-auto rounded-2xl border border-outline-variant/10">
                <table className="w-full text-xs">
                  <thead className="bg-surface-container-high text-on-surface-variant uppercase text-[10px]">
                    <tr>
                      <th className="text-left p-2">進場</th>
                      <th className="text-left p-2">出場</th>
                      <th className="text-right p-2">進場價</th>
                      <th className="text-right p-2">出場價</th>
                      <th className="text-right p-2">損益</th>
                      <th className="text-right p-2">損益 %</th>
                      <th className="text-left p-2">原因</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.trades.map((t, i) => (
                      <tr key={i} className="border-t border-outline-variant/10">
                        <td className="p-2 font-mono">{t.entry_date}</td>
                        <td className="p-2 font-mono">{t.exit_date || "—"}</td>
                        <td className="p-2 text-right font-mono">{t.entry_price?.toFixed(2)}</td>
                        <td className="p-2 text-right font-mono">{t.exit_price?.toFixed(2) ?? "—"}</td>
                        <td className={cn("p-2 text-right font-mono flex items-center justify-end gap-1", (t.pnl ?? 0) >= 0 ? "text-secondary" : "text-red-400")}>
                          {(t.pnl ?? 0) >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                          {t.pnl?.toFixed(2) ?? "—"}
                        </td>
                        <td className="p-2 text-right font-mono">{t.pnl_pct?.toFixed(2) ?? "—"}%</td>
                        <td className="p-2 text-on-surface-variant">{t.exit_reason || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
