"use client";

import React from "react";
import TacticalCard from "@/components/ui/TacticalCard";
import Terminal from "@/components/dashboard/Terminal";
import BriefingCard from "@/components/ui/BriefingCard";
import { PortfolioStats } from "@/features/portfolio/components/PortfolioStats";
import { PositionsTable } from "@/features/portfolio/components/PositionsTable";
import { PerformanceChart } from "@/features/portfolio/components/PerformanceChart";
import { AgentStatusPanel } from "@/features/agents/components/AgentStatusPanel";
import { SystemAlerts } from "@/features/notifications/components/SystemAlerts";
import { ErrorBoundary, ComponentFallback } from "@/core/components/ErrorBoundary";

import { usePortfolioStatus } from "@/features/portfolio/use-cases/usePortfolioStatus";
import { useIntelligenceStatus } from "@/features/intelligence/use-cases/useIntelligenceStatus";
import { useDashboardSocket, useAgentsStatus, usePositions, useAlerts } from "@/hooks/useDashboard";
import { useRequireAuth } from "@/hooks/useAuth";
import { Loader2 } from "lucide-react";

const toast = {
  success: (msg: string) => console.log(`SUCCESS: ${msg}`),
  error: (msg: string) => console.error(`ERROR: ${msg}`),
};

export default function CommandCenter() {
  const { summary, isLoading: isSummaryLoading, rebalance, generateReport } = usePortfolioStatus();
  const { briefing, isLoading: isIntelLoading } = useIntelligenceStatus();
  const { agents, isLoading: isAgentsLoading } = useAgentsStatus();
  const { positions, isLoading: isPositionsLoading } = usePositions();
  const { alerts, isLoading: isAlertsLoading } = useAlerts();

  const { status: socketStatus } = useDashboardSocket();
  const { isLoading: isAuthLoading } = useRequireAuth();

  const [isReporting, setIsReporting] = React.useState(false);
  const [isRebalancing, setIsRebalancing] = React.useState(false);

  const handleGenerateReport = async () => {
    try {
      setIsReporting(true);
      await generateReport();
      toast.success("市場情報報告生成中...");
    } catch (err) {
      toast.error("報告生成失敗，請稍後再試。");
    } finally {
      setIsReporting(false);
    }
  };

  const handleRebalance = async () => {
    try {
      setIsRebalancing(true);
      await rebalance();
      toast.success("資產再平衡指令已發送。");
    } catch (err) {
      toast.error("指令執行失敗。");
    } finally {
      setIsRebalancing(false);
    }
  };

  const isGlobalLoading = isAuthLoading || isSummaryLoading;

  if (isGlobalLoading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="h-10 w-10 text-primary animate-spin" />
          <p className="text-xs font-label uppercase tracking-widest text-on-surface-variant opacity-60">
            資產中心初始化中...
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto pt-16 sm:pt-20 lg:pt-24 px-4 sm:px-6 lg:px-8 pb-8 animate-in fade-in duration-700">
      <div className="max-w-[1600px] mx-auto space-y-4 lg:space-y-8">
        <PortfolioStats
          summary={summary}
          isReporting={isReporting}
          isRebalancing={isRebalancing}
          onGenerateReport={handleGenerateReport}
          onRebalance={handleRebalance}
        />

        <div className="grid grid-cols-12 gap-4 lg:gap-6">
          <div className="col-span-12 lg:col-span-8">
            <TacticalCard title="資產績效表現趨勢" className="h-full">
              <ErrorBoundary fallback={<ComponentFallback name="績效圖表" />}>
                <PerformanceChart />
              </ErrorBoundary>
            </TacticalCard>
          </div>

          <div className="col-span-12 lg:col-span-4">
            <ErrorBoundary fallback={<ComponentFallback name="市場情報" />}>
              <BriefingCard
                summary={briefing?.executive_summary || "正在準備市場摘要..."}
                recommendation={briefing?.recommendation || "分析中"}
                note={briefing?.ai_note || "系統同步中"}
                status={briefing?.observation_window || "INITIALIZING"}
                metrics={briefing?.sentiment_metrics || []}
                isLoading={isIntelLoading}
              />
            </ErrorBoundary>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-4 lg:gap-6">
          <div className="col-span-12 lg:col-span-8">
            <ErrorBoundary fallback={<ComponentFallback name="持倉明細" />}>
              <PositionsTable positions={positions} isLoading={isPositionsLoading} />
            </ErrorBoundary>
          </div>

          <div className="col-span-12 lg:col-span-4">
            <ErrorBoundary fallback={<ComponentFallback name="系統通知" />}>
              <SystemAlerts alerts={alerts} isLoading={isAlertsLoading} />
            </ErrorBoundary>
          </div>
        </div>

        <div className="grid grid-cols-12 gap-4 lg:gap-6">
          <div className="col-span-12 lg:col-span-8">
            <Terminal />
          </div>

          <div className="col-span-12 lg:col-span-4">
            <ErrorBoundary fallback={<ComponentFallback name="代理人監控" />}>
              <AgentStatusPanel />
            </ErrorBoundary>
          </div>
        </div>
      </div>
    </div>
  );
}
