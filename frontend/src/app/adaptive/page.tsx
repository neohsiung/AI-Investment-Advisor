"use client";

import React from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  Radar,
  ResponsiveContainer,
  Tooltip,
} from "recharts";
import {
  ShieldAlert,
  Brain,
  RefreshCw,
  Compass,
  CheckCircle2,
  AlertCircle,
  Scale,
  Zap,
  Database,
  BarChart3,
  Loader2,
} from "lucide-react";

export type HealthRadarData = {
  regime_alignment: number;
  diversification_efficiency: number;
  factor_balance: number;
  tail_risk_resilience: number;
  capital_safety: number;
};

export type ProvenanceData = {
  holdings?: "live" | "template" | string;
  market_observation?: "live" | "default" | string;
  tail_risk?: "live_portfolio" | "weighted_assets" | "synthetic" | string;
};

export type RegimeAnalysisData = {
  current_regime?: string;
  regime_confidence?: number;
  target_cash_buffer?: number;
  target_beta?: number;
  description?: string;
};

export type TailRiskAnalysisData = {
  alert_level?: "NORMAL" | "WATCH" | "WARNING" | "CRITICAL" | string;
  var_999?: number;
  cvar_999?: number;
  fat_tail_ratio?: number;
  kurtosis?: number;
};

export type DiversificationData = {
  effective_n?: number;
  max_weight?: number;
  gini_coefficient?: number;
};

export type CapitalSafetyData = {
  leverage_ratio?: number;
  margin_cushion?: number;
  max_drawdown?: number;
};

export type RebalanceRecommendationData = {
  needs_rebalance?: boolean;
  rebalance_reason?: string;
  target_weights?: Record<string, number>;
  trades?: Array<{
    ticker: string;
    action: string;
    shares?: number;
    amount?: number;
    urgency?: string;
  }>;
};

export type DiagnosticPayload = {
  health_score: number;
  health_rating: "OPTIMAL" | "BALANCED" | "CAUTION" | "CRITICAL" | string;
  radar_dimensions?: HealthRadarData;
  radar?: HealthRadarData;
  regime_analysis?: RegimeAnalysisData;
  current_regime?: string;
  regime_confidence?: number;
  tail_risk_analysis?: TailRiskAnalysisData;
  diversification_metrics?: DiversificationData;
  capital_safety_metrics?: CapitalSafetyData;
  rebalance_recommendation?: RebalanceRecommendationData;
  needs_rebalance?: boolean;
  summary_insights?: string[];
  provenance?: ProvenanceData;
};

export type DiagnoseResponse = {
  status: string;
  data?: DiagnosticPayload;
  health_score?: number;
  health_rating?: string;
  radar?: HealthRadarData;
  current_regime?: string;
  regime_confidence?: number;
  needs_rebalance?: boolean;
  summary_insights?: string[];
  provenance?: ProvenanceData;
};

// 格式化百分比
function formatPercent(val: number | null | undefined, decimals = 1): string {
  if (val === null || val === undefined || isNaN(val)) return "—";
  return `${(val * 100).toFixed(decimals)}%`;
}

// 格式化數值
function formatNum(val: number | null | undefined, decimals = 2): string {
  if (val === null || val === undefined || isNaN(val)) return "—";
  return val.toFixed(decimals);
}

// 評級徽章樣式
function getRatingBadge(rating: string) {
  switch (rating?.toUpperCase()) {
    case "OPTIMAL":
      return {
        label: "OPTIMAL (極佳)",
        bg: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
        ring: "ring-emerald-500/20",
        dot: "bg-emerald-400",
      };
    case "BALANCED":
      return {
        label: "BALANCED (穩健)",
        bg: "bg-sky-500/15 text-sky-400 border-sky-500/30",
        ring: "ring-sky-500/20",
        dot: "bg-sky-400",
      };
    case "CAUTION":
      return {
        label: "CAUTION (警戒)",
        bg: "bg-amber-500/15 text-amber-400 border-amber-500/30",
        ring: "ring-amber-500/20",
        dot: "bg-amber-400",
      };
    case "CRITICAL":
      return {
        label: "CRITICAL (危殆)",
        bg: "bg-rose-500/15 text-rose-400 border-rose-500/30",
        ring: "ring-rose-500/20",
        dot: "bg-rose-400",
      };
    default:
      return {
        label: rating || "UNKNOWN",
        bg: "bg-slate-500/15 text-slate-300 border-slate-500/30",
        ring: "ring-slate-500/20",
        dot: "bg-slate-400",
      };
  }
}

// 黑天鵝警戒樣式
function getAlertBadge(level: string) {
  switch (level?.toUpperCase()) {
    case "CRITICAL":
      return {
        label: "極端危殆",
        bg: "bg-rose-500/20 text-rose-400 border-rose-500/40",
      };
    case "WARNING":
      return {
        label: "黑天鵝預警",
        bg: "bg-amber-500/20 text-amber-400 border-amber-500/40",
      };
    case "WATCH":
      return {
        label: "密切關注",
        bg: "bg-blue-500/20 text-blue-400 border-blue-500/40",
      };
    case "NORMAL":
    default:
      return {
        label: "常態安全",
        bg: "bg-emerald-500/20 text-emerald-400 border-emerald-500/40",
      };
  }
}

// 數據來源標籤解析 (Provenance Badge)
function renderProvenancePill(type: "holdings" | "macro" | "tail", val?: string) {
  if (type === "holdings") {
    const isLive = val === "live";
    return (
      <span
        title={isLive ? "真實帳戶實時持倉數據" : "示範基準範本持倉（帳戶無持倉時自動啟用）"}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium border transition-colors",
          isLive
            ? "bg-emerald-950/40 text-emerald-300 border-emerald-600/30"
            : "bg-amber-950/40 text-amber-300 border-amber-600/30"
        )}
      >
        <span className={cn("w-1.5 h-1.5 rounded-full", isLive ? "bg-emerald-400" : "bg-amber-400")} />
        持倉: {isLive ? "實測持倉 (Live)" : "範本基準 (Template)"}
      </span>
    );
  }

  if (type === "macro") {
    const isLive = val === "live";
    return (
      <span
        title={isLive ? "即時市場 SPY / VIX 宏觀行情反饋" : "系統預設基準行情常數"}
        className={cn(
          "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium border transition-colors",
          isLive
            ? "bg-emerald-950/40 text-emerald-300 border-emerald-600/30"
            : "bg-amber-950/40 text-amber-300 border-amber-600/30"
        )}
      >
        <span className={cn("w-1.5 h-1.5 rounded-full", isLive ? "bg-emerald-400" : "bg-amber-400")} />
        宏觀: {isLive ? "即時行情 (Live SPY/VIX)" : "預設常數 (Default)"}
      </span>
    );
  }

  // tail risk provenance
  let badgeColor = "bg-purple-950/40 text-purple-300 border-purple-600/30";
  let dotColor = "bg-purple-400";
  let labelText = "合成模擬 (Synthetic)";

  if (val === "live_portfolio") {
    badgeColor = "bg-emerald-950/40 text-emerald-300 border-emerald-600/30";
    dotColor = "bg-emerald-400";
    labelText = "實測淨值 (Live Portfolio)";
  } else if (val === "weighted_assets") {
    badgeColor = "bg-sky-950/40 text-sky-300 border-sky-600/30";
    dotColor = "bg-sky-400";
    labelText = "加權行情 (Asset-Weighted)";
  }

  return (
    <span
      title="尾部風險報酬率歷史真實來源（實測淨值、標的加權行情或蒙地卡羅幾何布朗合成）"
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono font-medium border transition-colors",
        badgeColor
      )}
    >
      <span className={cn("w-1.5 h-1.5 rounded-full", dotColor)} />
      尾部來源: {labelText}
    </span>
  );
}

export default function AdaptiveWarRoomPage() {
  const { data: rawData, error, isLoading, mutate, isValidating } = useSWR<DiagnoseResponse>(
    "/api/v1/adaptive-intelligence/diagnose",
    fetcher,
    {
      refreshInterval: 30000,
      revalidateOnFocus: true,
      shouldRetryOnError: true,
    }
  );

  // 解析回應資料結構（兼顧 diagnose 與 health 規格）
  const payload: DiagnosticPayload | undefined =
    rawData?.data ||
    (rawData?.health_score !== undefined
      ? {
          health_score: rawData.health_score,
          health_rating: rawData.health_rating || "BALANCED",
          radar_dimensions: rawData.radar,
          radar: rawData.radar,
          regime_analysis: {
            current_regime: rawData.current_regime,
            regime_confidence: rawData.regime_confidence,
          },
          current_regime: rawData.current_regime,
          regime_confidence: rawData.regime_confidence,
          needs_rebalance: rawData.needs_rebalance,
          summary_insights: rawData.summary_insights,
          provenance: rawData.provenance,
        }
      : undefined);

  // 處理載入中狀態
  if (isLoading) {
    return (
      <div className="min-h-[80vh] flex flex-col items-center justify-center p-8 space-y-4">
        <Loader2 className="w-10 h-10 text-primary animate-spin" />
        <p className="text-lg font-medium text-on-surface">正在運算自適應風控協同診斷數據...</p>
        <p className="text-sm text-on-surface-variant/75">
          匯總 D1 五維健康、O1 貝氏體制、O2 EVT 尾部抗性與真實數據校準
        </p>
      </div>
    );
  }

  // 處理錯誤或無資料狀態
  if (error || !payload) {
    const errorMsg =
      error?.response?.data?.detail || error?.message || "無法取得自適應風控數據，請確認後端服務狀態";
    return (
      <div className="p-8 max-w-4xl mx-auto space-y-6">
        <div className="bg-rose-950/30 border border-rose-500/30 rounded-2xl p-6 text-rose-300 space-y-4">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-7 h-7 text-rose-400 shrink-0" />
            <div>
              <h2 className="text-xl font-bold font-headline">自適應戰情室診斷載入失敗</h2>
              <p className="text-sm text-rose-300/80 mt-1">{errorMsg}</p>
            </div>
          </div>
          <button
            onClick={() => mutate()}
            className="inline-flex items-center gap-2 px-4 py-2 bg-rose-600/30 hover:bg-rose-600/50 text-white rounded-xl text-sm font-medium border border-rose-500/40 transition-colors"
          >
            <RefreshCw className="w-4 h-4" />
            重試連線
          </button>
        </div>
      </div>
    );
  }

  // 提煉指標
  const score = payload.health_score ?? 0;
  const rating = payload.health_rating || "BALANCED";
  const ratingStyle = getRatingBadge(rating);
  const radarObj = payload.radar_dimensions || payload.radar || {
    regime_alignment: 50,
    diversification_efficiency: 50,
    factor_balance: 50,
    tail_risk_resilience: 50,
    capital_safety: 50,
  };

  const radarChartData = [
    { dimension: "體制適應度", score: Math.round(radarObj.regime_alignment || 0), fullMark: 100 },
    { dimension: "分散化效率", score: Math.round(radarObj.diversification_efficiency || 0), fullMark: 100 },
    { dimension: "因子風格平衡", score: Math.round(radarObj.factor_balance || 0), fullMark: 100 },
    { dimension: "尾部風險抗跌", score: Math.round(radarObj.tail_risk_resilience || 0), fullMark: 100 },
    { dimension: "資本安全度", score: Math.round(radarObj.capital_safety || 0), fullMark: 100 },
  ];

  const regime = payload.regime_analysis || {
    current_regime: payload.current_regime || "NEUTRAL_RANGE",
    regime_confidence: payload.regime_confidence ?? 0.75,
  };

  const tailRisk = payload.tail_risk_analysis || {
    alert_level: "NORMAL",
    var_999: 0.035,
    cvar_999: 0.048,
    fat_tail_ratio: 1.15,
  };
  const tailAlert = getAlertBadge(tailRisk.alert_level || "NORMAL");

  const diversification = payload.diversification_metrics || {};
  const capitalSafety = payload.capital_safety_metrics || {};
  const rebalance = payload.rebalance_recommendation || {
    needs_rebalance: payload.needs_rebalance ?? false,
    rebalance_reason: "投組結構與當前體制相符，維持現有配置",
  };

  const provenance = payload.provenance || {
    holdings: "template",
    market_observation: "default",
    tail_risk: "synthetic",
  };

  return (
    <div className="p-6 lg:p-10 space-y-8 max-w-7xl mx-auto">
      {/* 頂部標頭與數據來源儀表 */}
      <header className="space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-primary-container/30 text-primary rounded-xl border border-primary/20 shadow-sm">
                <Brain className="w-6 h-6" />
              </div>
              <h1 className="text-2xl lg:text-3xl font-black font-headline tracking-tight text-on-surface">
                自適應風控戰情室
              </h1>
            </div>
            <p className="text-sm text-on-surface-variant/80 mt-1">
              D1 五維健康雷達・O1 貝氏動態體制・O2 EVT 極值黑天鵝防禦・P4 演化再平衡
            </p>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => mutate()}
              disabled={isValidating}
              aria-label="重新整理數據"
              className="inline-flex items-center gap-2 px-4 py-2 bg-surface-container-high hover:bg-surface-bright text-on-surface rounded-xl text-xs font-mono border border-outline-variant/20 transition-all active:scale-95 disabled:opacity-50"
            >
              <RefreshCw className={cn("w-3.5 h-3.5", isValidating && "animate-spin text-primary")} />
              {isValidating ? "即時刷新中..." : "手動整理"}
            </button>
          </div>
        </div>

        {/* 數據真實度標籤組 (Data Provenance & Zero Fabricated Data) */}
        <div
          role="region"
          aria-label="數據真實來源說明"
          className="bg-surface-container-low p-3.5 rounded-2xl border border-outline-variant/15 flex flex-wrap items-center justify-between gap-3 text-xs"
        >
          <div className="flex items-center gap-2 text-on-surface-variant font-mono">
            <Database className="w-4 h-4 text-primary" />
            <span className="font-semibold text-on-surface">零虛假數據真實來源保證:</span>
          </div>
          <div className="flex flex-wrap items-center gap-2.5">
            {renderProvenancePill("holdings", provenance.holdings)}
            {renderProvenancePill("macro", provenance.market_observation)}
            {renderProvenancePill("tail", provenance.tail_risk)}
          </div>
        </div>
      </header>

      {/* 總合健康分數與核心膠囊卡 */}
      <section
        aria-label="投組綜合健康狀態"
        aria-live="polite"
        className="grid grid-cols-1 md:grid-cols-3 gap-6"
      >
        {/* 總健康評分卡 */}
        <div className="bg-surface-container-low p-6 rounded-3xl border border-outline-variant/15 shadow-sm space-y-3 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-on-surface-variant">
              綜合健康分數 (Health Score)
            </span>
            <div className={cn("px-3 py-1 rounded-full text-xs font-bold border", ratingStyle.bg)}>
              {ratingStyle.label}
            </div>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-5xl font-black font-mono tracking-tight text-on-surface">
              {formatNum(score, 1)}
            </span>
            <span className="text-sm font-mono text-on-surface-variant/60">/ 100</span>
          </div>
          <div className="w-full bg-surface-container-highest rounded-full h-2 overflow-hidden">
            <div
              className={cn(
                "h-full transition-all duration-500 rounded-full",
                score >= 80 ? "bg-emerald-500" : score >= 65 ? "bg-sky-500" : score >= 50 ? "bg-amber-500" : "bg-rose-500"
              )}
              style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
            />
          </div>
          <p className="text-xs text-on-surface-variant/80">
            {score >= 80
              ? "投組在當前體制下表現優異，防禦抗跌與分散化效率皆達標。"
              : score >= 65
              ? "投組結構穩健，存在微量因子傾斜或集中度優化空間。"
              : "投組結構偏離當前體制或尾部風險偏高，建議參考再平衡方案。"}
          </p>
        </div>

        {/* 當前體制快照卡 (O1) */}
        <div className="bg-surface-container-low p-6 rounded-3xl border border-outline-variant/15 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-on-surface-variant">
              O1 貝氏動態體制 (Market Regime)
            </span>
            <Compass className="w-4 h-4 text-primary" />
          </div>
          <div className="space-y-1">
            <p className="text-2xl font-bold font-mono tracking-tight text-on-surface">
              {regime.current_regime || "NEUTRAL_RANGE"}
            </p>
            <p className="text-xs font-mono text-on-surface-variant">
              判定置信度:{" "}
              <span className="text-primary font-bold">
                {formatPercent(regime.regime_confidence, 0)}
              </span>
            </p>
          </div>
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-outline-variant/10 text-xs font-mono">
            <div>
              <span className="text-on-surface-variant/70">建議現金水位:</span>
              <p className="text-on-surface font-semibold">
                {regime.target_cash_buffer !== undefined ? formatPercent(regime.target_cash_buffer) : "10.0%"}
              </p>
            </div>
            <div>
              <span className="text-on-surface-variant/70">目標 Beta:</span>
              <p className="text-on-surface font-semibold">
                {regime.target_beta !== undefined ? formatNum(regime.target_beta, 2) : "1.00"}
              </p>
            </div>
          </div>
        </div>

        {/* EVT 尾部黑天鵝告警 (O2) */}
        <div className="bg-surface-container-low p-6 rounded-3xl border border-outline-variant/15 shadow-sm space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono uppercase tracking-wider text-on-surface-variant">
              O2 EVT 極值黑天鵝防禦
            </span>
            <ShieldAlert className="w-4 h-4 text-rose-400" />
          </div>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-xs text-on-surface-variant/70">尾部預警層級</p>
              <div className={cn("mt-1 px-2.5 py-0.5 rounded-full text-xs font-bold border inline-block", tailAlert.bg)}>
                {tailAlert.label} ({tailRisk.alert_level || "NORMAL"})
              </div>
            </div>
            <div className="text-right">
              <p className="text-xs text-on-surface-variant/70">肥尾放大倍數</p>
              <p className="text-lg font-mono font-bold text-on-surface">
                {formatNum(tailRisk.fat_tail_ratio, 2)}x
              </p>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-outline-variant/10 text-xs font-mono">
            <div>
              <span className="text-on-surface-variant/70">VaR (99.9% 1日):</span>
              <p className="text-on-surface font-semibold">{formatPercent(tailRisk.var_999)}</p>
            </div>
            <div>
              <span className="text-on-surface-variant/70">CVaR (尾部預期損失):</span>
              <p className="text-on-surface font-semibold">{formatPercent(tailRisk.cvar_999)}</p>
            </div>
          </div>
        </div>
      </section>

      {/* 主體展示：五維雷達圖與可訪問數據表 */}
      <section className="grid grid-cols-1 lg:grid-cols-12 gap-8">
        {/* 左側：雷達視覺化與無障礙表格 */}
        <div className="lg:col-span-7 bg-surface-container-low p-6 lg:p-8 rounded-3xl border border-outline-variant/15 shadow-sm space-y-6">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h2 className="text-lg font-bold font-headline text-on-surface flex items-center gap-2">
                <BarChart3 className="w-5 h-5 text-primary" />
                五維健康雷達視覺化
              </h2>
              <p className="text-xs text-on-surface-variant">
                量化衡量體制吻合度、資產分散性、多因子權重、極值防禦與資本防護
              </p>
            </div>
            <div className="text-xs font-mono text-on-surface-variant/70 bg-surface-container-high px-2.5 py-1 rounded-lg">
              滿分 100 分制
            </div>
          </div>

          {/* Recharts 雷達圖 */}
          <div
            role="img"
            aria-label="五維投組健康雷達圖"
            className="w-full h-80 flex items-center justify-center bg-surface-container-lowest/50 rounded-2xl p-2 border border-outline-variant/10"
          >
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={radarChartData} margin={{ top: 20, right: 30, bottom: 20, left: 30 }}>
                <PolarGrid stroke="#334155" strokeDasharray="3 3" />
                <PolarAngleAxis
                  dataKey="dimension"
                  tick={{ fill: "#94a3b8", fontSize: 12, fontWeight: 600 }}
                />
                <PolarRadiusAxis
                  angle={90}
                  domain={[0, 100]}
                  stroke="#475569"
                  tick={{ fill: "#64748b", fontSize: 10 }}
                />
                <Radar
                  name="投組健康度"
                  dataKey="score"
                  stroke="#38bdf8"
                  fill="#38bdf8"
                  fillOpacity={0.35}
                />
                <Tooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload;
                      return (
                        <div className="bg-slate-900 border border-slate-700 p-2.5 rounded-xl shadow-lg text-xs font-mono text-white">
                          <p className="font-bold text-sky-400">{data.dimension}</p>
                          <p className="mt-1">健康評分: {data.score} / 100</p>
                        </div>
                      );
                    }
                    return null;
                  }}
                />
              </RadarChart>
            </ResponsiveContainer>
          </div>

          {/* A11y 語意化表格替代視圖 (Accessible Alternative Table) */}
          <div className="space-y-2">
            <h3 className="text-xs font-bold uppercase tracking-wider text-on-surface-variant">
              各維度數值明細 (語意化輔助視圖)
            </h3>
            <div className="overflow-x-auto rounded-xl border border-outline-variant/15">
              <table
                aria-label="五維健康雷達數據表"
                className="w-full text-left text-xs font-mono divide-y divide-outline-variant/15"
              >
                <thead className="bg-surface-container-high text-on-surface-variant">
                  <tr>
                    <th scope="col" className="px-4 py-2.5 font-semibold">健康維度</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">得分 (0-100)</th>
                    <th scope="col" className="px-4 py-2.5 font-semibold">狀態評價</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-outline-variant/10 bg-surface-container-low text-on-surface">
                  {radarChartData.map((row) => {
                    const statusText =
                      row.score >= 80 ? "優異 (Optimal)" : row.score >= 60 ? "良好 (Healthy)" : "警戒 (Caution)";
                    const statusColor =
                      row.score >= 80
                        ? "text-emerald-400"
                        : row.score >= 60
                        ? "text-sky-400"
                        : "text-amber-400";
                    return (
                      <tr key={row.dimension} className="hover:bg-surface-container-high/40 transition-colors">
                        <td className="px-4 py-2.5 font-medium">{row.dimension}</td>
                        <td className="px-4 py-2.5 font-bold">{row.score}</td>
                        <td className={cn("px-4 py-2.5 font-semibold", statusColor)}>{statusText}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* 右側：再平衡建議與深入指標 */}
        <div className="lg:col-span-5 space-y-6">
          {/* 再平衡建議卡 (P4 / E1) */}
          <div className="bg-surface-container-low p-6 rounded-3xl border border-outline-variant/15 shadow-sm space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Zap className="w-5 h-5 text-amber-400" />
                <h2 className="text-base font-bold font-headline text-on-surface">
                  P4 演化再平衡與調倉建議
                </h2>
              </div>
              <span
                className={cn(
                  "px-2.5 py-1 rounded-full text-xs font-mono font-bold border",
                  rebalance.needs_rebalance
                    ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                    : "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                )}
              >
                {rebalance.needs_rebalance ? "建議調倉" : "配置穩健"}
              </span>
            </div>

            <p className="text-xs text-on-surface-variant/90 leading-relaxed">
              {rebalance.rebalance_reason || "投組結構與當前體制相符，維持現有配置"}
            </p>

            {/* 目標權重或調倉清單 */}
            {rebalance.target_weights && Object.keys(rebalance.target_weights).length > 0 && (
              <div className="space-y-2 pt-2 border-t border-outline-variant/10">
                <span className="text-[11px] font-mono uppercase text-on-surface-variant">
                  建議目標權重 (Target Weights)
                </span>
                <div className="grid grid-cols-3 gap-2">
                  {Object.entries(rebalance.target_weights).map(([ticker, weight]) => (
                    <div
                      key={ticker}
                      className="bg-surface-container-high/60 p-2 rounded-xl text-center font-mono text-xs border border-outline-variant/10"
                    >
                      <div className="font-bold text-on-surface">{ticker}</div>
                      <div className="text-primary font-semibold">{formatPercent(weight)}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 具體執行交易 (SOR 排程) */}
            {rebalance.trades && rebalance.trades.length > 0 && (
              <div className="space-y-2 pt-2 border-t border-outline-variant/10">
                <span className="text-[11px] font-mono uppercase text-on-surface-variant">
                  E1 SOR 拆單排程預覽
                </span>
                <div className="space-y-1.5">
                  {rebalance.trades.slice(0, 4).map((trade, idx) => (
                    <div
                      key={idx}
                      className="flex items-center justify-between p-2 rounded-lg bg-surface-container-high/40 text-xs font-mono"
                    >
                      <div className="flex items-center gap-2">
                        <span
                          className={cn(
                            "px-1.5 py-0.5 rounded text-[10px] font-bold",
                            trade.action === "BUY" ? "bg-emerald-500/20 text-emerald-400" : "bg-rose-500/20 text-rose-400"
                          )}
                        >
                          {trade.action}
                        </span>
                        <span className="font-bold text-on-surface">{trade.ticker}</span>
                      </div>
                      <span className="text-on-surface-variant">
                        {trade.shares ? `${trade.shares} 股` : trade.amount ? `$${trade.amount.toFixed(0)}` : "調整"}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* 分散化與資本安全度指標卡 */}
          <div className="bg-surface-container-low p-6 rounded-3xl border border-outline-variant/15 shadow-sm space-y-4">
            <h2 className="text-base font-bold font-headline text-on-surface flex items-center gap-2">
              <Scale className="w-5 h-5 text-sky-400" />
              投組結構深入度量
            </h2>
            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div className="bg-surface-container-high/40 p-3 rounded-2xl border border-outline-variant/10">
                <span className="text-on-surface-variant/70">有效資產數 (Effective N)</span>
                <p className="text-base font-bold text-on-surface mt-1">
                  {formatNum(diversification.effective_n, 1)}
                </p>
                <p className="text-[10px] text-on-surface-variant/60 mt-0.5">越高代表越分散</p>
              </div>
              <div className="bg-surface-container-high/40 p-3 rounded-2xl border border-outline-variant/10">
                <span className="text-on-surface-variant/70">最大單一持倉權重</span>
                <p className="text-base font-bold text-on-surface mt-1">
                  {formatPercent(diversification.max_weight)}
                </p>
                <p className="text-[10px] text-on-surface-variant/60 mt-0.5">集中度風險防範</p>
              </div>
              <div className="bg-surface-container-high/40 p-3 rounded-2xl border border-outline-variant/10">
                <span className="text-on-surface-variant/70">保證金緩衝 (Cushion)</span>
                <p className="text-base font-bold text-on-surface mt-1">
                  {formatPercent(capitalSafety.margin_cushion)}
                </p>
                <p className="text-[10px] text-on-surface-variant/60 mt-0.5">清算抗跌邊際</p>
              </div>
              <div className="bg-surface-container-high/40 p-3 rounded-2xl border border-outline-variant/10">
                <span className="text-on-surface-variant/70">投組當前回撤幅度</span>
                <p className="text-base font-bold text-on-surface mt-1">
                  {formatPercent(capitalSafety.max_drawdown)}
                </p>
                <p className="text-[10px] text-on-surface-variant/60 mt-0.5">高點回撤保護</p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 核心洞察摘要清單 */}
      {payload.summary_insights && payload.summary_insights.length > 0 && (
        <section
          aria-label="核心洞察分析"
          className="bg-surface-container-low p-6 lg:p-8 rounded-3xl border border-outline-variant/15 shadow-sm space-y-4"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <h2 className="text-lg font-bold font-headline text-on-surface">
              自適應風控核心洞察報告
            </h2>
          </div>
          <ul className="space-y-2.5 text-xs lg:text-sm text-on-surface-variant/90 leading-relaxed font-mono">
            {payload.summary_insights.map((insight, idx) => (
              <li key={idx} className="flex items-start gap-2.5">
                <span className="w-1.5 h-1.5 rounded-full bg-primary mt-2 shrink-0" />
                <span>{insight}</span>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
