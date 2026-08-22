"use client";

import React from "react";
import useSWR from "swr";
import api, { fetcher } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  Legend
} from "recharts";
import { 
  Activity, 
  Brain, 
  ShieldAlert, 
  ThumbsUp, 
  DollarSign, 
  Cpu, 
  Award,
  AlertCircle,
  Loader2
} from "lucide-react";

type LearningMetrics = {
  decisions_total: number;
  decisions_resolved: number;
  resolution_rate: number | null;
  rules_by_status: Record<string, number>;
  avg_active_rule_score: number | null;
};

type SelfOpsMetrics = {
  breaches_this_week: number;
  remediation_by_tier: Record<string, number>;
  weekly_cost_usd: number;
  weekly_budget_usd: number;
};

type FeedbackMetrics = {
  approval_rate: number | null;
  by_decision: Record<string, number>;
  rejection_reason_capture_rate: number | null;
  preference_sample_size: number;
  risk_appetite_score: number | null;
};

type CachingMetrics = {
  total_workflow_runs: number;
  cache_hits: number;
  cache_misses: number;
  saved_cost_usd: number;
};

type LoopHealthResponse = {
  status: string;
  learning: LearningMetrics;
  self_ops: SelfOpsMetrics;
  feedback: FeedbackMetrics;
  caching?: CachingMetrics;
};

function MetricTile({
  label,
  value,
  subtitle,
  icon: Icon,
  className
}: {
  label: string;
  value: string | number | null | undefined;
  subtitle?: string;
  icon: React.ComponentType<any>;
  className?: string;
}) {
  return (
    <div className={cn("bg-surface-container-low p-5 rounded-2xl border border-outline-variant/10 shadow-sm hover:shadow transition-all group", className)}>
      <div className="flex justify-between items-start mb-3">
        <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest">{label}</p>
        <div className="p-2 bg-surface-container-high rounded-xl text-primary group-hover:scale-110 transition-transform duration-200">
          <Icon className="h-4 w-4" />
        </div>
      </div>
      <p className="text-2xl font-bold font-mono tracking-tight text-on-surface">
        {value !== null && value !== undefined ? value : "—"}
      </p>
      {subtitle && (
        <p className="text-[10px] text-on-surface-variant/75 mt-1 font-medium">{subtitle}</p>
      )}
    </div>
  );
}

export default function HealthPage() {
  const { data, error, isLoading } = useSWR<LoopHealthResponse>(
    "/api/v1/loop-health",
    fetcher,
    { refreshInterval: 30000 } // Auto refresh every 30s
  );

  if (isLoading) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh]">
        <Loader2 className="h-10 w-10 text-primary animate-spin mb-4" />
        <p className="text-sm font-label text-on-surface-variant tracking-widest uppercase">載入系統健康數據中...</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center min-h-[60vh] px-4 text-center">
        <AlertCircle className="h-12 w-12 text-error mb-4" />
        <h2 className="text-xl font-bold font-headline mb-2 text-on-surface">無法載入監控數據</h2>
        <p className="text-sm text-on-surface-variant max-w-md mb-4">
          {error?.response?.data?.detail || error?.message || "後端 API 未回應或連線中斷。"}
        </p>
        <button 
          onClick={() => window.location.reload()}
          className="px-4 py-2 bg-primary text-on-primary rounded-xl font-bold text-sm transition-all hover:brightness-110 active:scale-95 shadow-lg"
        >
          重新整理
        </button>
      </div>
    );
  }

  const { learning, self_ops, feedback, caching } = data;

  // Formulate cost data for chart
  const costData = [
    {
      name: "週預算與支出",
      已花費: self_ops.weekly_cost_usd,
      剩餘預算: Math.max(0, self_ops.weekly_budget_usd - self_ops.weekly_cost_usd)
    }
  ];

  // Colors for cost bar chart
  const costColors = ["#60a5fa", "#34d399"]; // Light blue for spent, green for remaining

  // Decision feedback composition data
  const feedbackTotal = (feedback.by_decision.approved || 0) + (feedback.by_decision.rejected || 0);

  return (
    <div className="flex-1 overflow-y-auto pt-16 sm:pt-20 lg:pt-24 px-4 sm:px-6 lg:px-8 pb-8 bg-background">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-end gap-4 mb-8">
        <div>
          <h1 className="text-2xl lg:text-4xl font-bold font-headline tracking-tighter mb-2">
            健康監控 <span className="text-primary/50 text-xl lg:text-2xl">Loop Health</span>
          </h1>
          <p className="text-on-surface-variant font-label text-xs uppercase tracking-[0.25em]">
            即時監控三個改進迴圈：決策學習、系統維運與使用者偏好
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Loop 1: Learning & Decisions */}
        <div className="lg:col-span-3 space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-widest text-primary flex items-center gap-2 border-b border-outline-variant/10 pb-2">
            <Brain size={16} /> Loop 1: 決策學習與規則演化 (Learning Loop)
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricTile 
              label="總決策數" 
              value={learning.decisions_total} 
              subtitle={`已結算決策: ${learning.decisions_resolved} 筆`} 
              icon={Activity} 
            />
            <MetricTile 
              label="決策解析率" 
              value={learning.resolution_rate !== null ? `${(learning.resolution_rate * 100).toFixed(1)}%` : "N/A"} 
              subtitle="已結算 / 總決策" 
              icon={Award} 
            />
            <MetricTile 
              label="活躍規則平均分" 
              value={learning.avg_active_rule_score !== null ? `${learning.avg_active_rule_score.toFixed(3)}%` : "0.00%"} 
              subtitle="反映規則在實戰中避免的平均 Alpha 虧損" 
              icon={Cpu} 
            />
            <MetricTile 
              label="規則庫狀態" 
              value={learning.rules_by_status.active || 0} 
              subtitle={`候選 (Candidate): ${learning.rules_by_status.candidate || 0} | 歷史 (Superseded): ${learning.rules_by_status.superseded || 0}`} 
              icon={Brain} 
            />
          </div>
        </div>

        {/* Loop 2: Self-Ops & System Health */}
        <div className="lg:col-span-2 space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-widest text-primary flex items-center gap-2 border-b border-outline-variant/10 pb-2">
            <ShieldAlert size={16} /> Loop 2: 自我維運與資源支出 (Self-Ops Loop)
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <MetricTile 
              label="本週異常次數 (Expected Out-of-bounds)" 
              value={self_ops.breaches_this_week} 
              subtitle="由預期排程缺失 / 組態異常觸發" 
              icon={AlertCircle} 
              className={self_ops.breaches_this_week > 0 ? "border-red-500/20 bg-red-950/5" : ""}
            />
            <MetricTile 
              label="修復日誌統計" 
              value={Object.values(self_ops.remediation_by_tier).reduce((a, b) => a + b, 0)} 
              subtitle={Object.entries(self_ops.remediation_by_tier).map(([t, n]) => `${t}: ${n}次`).join(" | ") || "無修復紀錄"} 
              icon={Cpu} 
            />
          </div>

          {/* Recharts Budget Chart */}
          <div className="bg-surface-container-low p-6 rounded-2xl border border-outline-variant/10 shadow-sm mt-4">
            <div className="flex justify-between items-center mb-4">
              <div>
                <h3 className="font-bold text-sm text-on-surface">週預算支出狀況</h3>
                <p className="text-xs text-on-surface-variant mt-0.5">預算限制: ${self_ops.weekly_budget_usd.toFixed(2)} USD / 週</p>
              </div>
              <div className="text-right">
                <p className="text-xs text-on-surface-variant font-label uppercase">本週已花費</p>
                <p className="text-lg font-bold font-mono text-primary">${self_ops.weekly_cost_usd.toFixed(2)}</p>
              </div>
            </div>
            <div className="h-28 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={costData}
                  layout="vertical"
                  barCategoryGap="20%"
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.1} />
                  <XAxis type="number" domain={[0, self_ops.weekly_budget_usd]} hide />
                  <YAxis type="category" dataKey="name" hide />
                  <Tooltip 
                    formatter={(value) => [`$${Number(value).toFixed(2)} USD`, ""]}
                    contentStyle={{ backgroundColor: "#1e293b", border: "none", borderRadius: "8px", color: "#fff" }}
                  />
                  <Bar dataKey="已花費" stackId="a" fill={costColors[0]} radius={[8, 0, 0, 8]}>
                    <Cell fill={self_ops.weekly_cost_usd > self_ops.weekly_budget_usd ? "#f87171" : "#60a5fa"} />
                  </Bar>
                  <Bar dataKey="剩餘預算" stackId="a" fill={costColors[1]} radius={[0, 8, 8, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
            <div className="flex justify-between items-center text-xs text-on-surface-variant border-t border-outline-variant/5 pt-3">
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: self_ops.weekly_cost_usd > self_ops.weekly_budget_usd ? "#f87171" : "#60a5fa" }} />
                <span>已花費: ${(self_ops.weekly_cost_usd).toFixed(2)} ({((self_ops.weekly_cost_usd / self_ops.weekly_budget_usd) * 100).toFixed(1)}%)</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
                <span>剩餘預算: ${(Math.max(0, self_ops.weekly_budget_usd - self_ops.weekly_cost_usd)).toFixed(2)}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Loop 3: User Feedback Loop */}
        <div className="lg:col-span-1 space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-widest text-primary flex items-center gap-2 border-b border-outline-variant/10 pb-2">
            <ThumbsUp size={16} /> Loop 3: 用戶回饋與偏好 (Feedback Loop)
          </h2>
          <div className="space-y-4">
            <MetricTile 
              label="審批核准率" 
              value={feedback.approval_rate !== null ? `${(feedback.approval_rate * 100).toFixed(1)}%` : "N/A"} 
              subtitle={`已做選擇: ${feedbackTotal} 次 (核准 ${feedback.by_decision.approved || 0} | 拒絕 ${feedback.by_decision.rejected || 0})`} 
              icon={ThumbsUp} 
            />
            <MetricTile 
              label="拒絕原因捕捉率" 
              value={feedback.rejection_reason_capture_rate !== null ? `${(feedback.rejection_reason_capture_rate * 100).toFixed(1)}%` : "N/A"} 
              subtitle="已附帶具體拒絕原因的比例" 
              icon={AlertCircle} 
            />
            <MetricTile 
              label="用戶風險偏好" 
              value={feedback.risk_appetite_score !== null ? `${feedback.risk_appetite_score.toFixed(1)}` : "未定義"} 
              subtitle={`樣本大小: ${feedback.preference_sample_size} 筆歷史資料`} 
              icon={Brain} 
            />
          </div>
        </div>

        {/* Caching: Workflow Cache & Cost Savings */}
        <div className="lg:col-span-3 space-y-4">
          <h2 className="text-sm font-bold uppercase tracking-widest text-primary flex items-center gap-2 border-b border-outline-variant/10 pb-2">
            <Cpu size={16} /> 快取統計與 Token 費用節省 (Workflow Cache Telemetry)
          </h2>
          {caching ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <MetricTile 
                label="總工作流執行次數" 
                value={caching.total_workflow_runs} 
                subtitle="工作流 DAG 觸發運行總量" 
                icon={Activity} 
              />
              <MetricTile 
                label="快取命中次數 (Hits)" 
                value={caching.cache_hits} 
                subtitle={`未命中 (Misses): ${caching.cache_misses} 次`} 
                icon={ThumbsUp} 
              />
              <MetricTile 
                label="快取命中率 (Hit Rate)" 
                value={
                  (caching.cache_hits + caching.cache_misses) > 0 
                    ? `${((caching.cache_hits / (caching.cache_hits + caching.cache_misses)) * 100).toFixed(1)}%` 
                    : "0.0%"
                } 
                subtitle="越高代表節省的重複呼叫次數越多" 
                icon={Award} 
              />
              <MetricTile 
                label="累計節省費用 (USD)" 
                value={`$${caching.saved_cost_usd.toFixed(4)}`} 
                subtitle="估計避免重複呼叫 LLM 節省之金額" 
                icon={DollarSign} 
                className="border-emerald-500/20 bg-emerald-950/5 text-emerald-400"
              />
            </div>
          ) : (
            <p className="text-xs text-on-surface-variant italic">無快取統計數據</p>
          )}
        </div>

      </div>
    </div>
  );
}
