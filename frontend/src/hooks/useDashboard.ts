import useSWR, { mutate } from "swr";
import { fetcher } from "@/lib/api";
import { useWebSocket } from "@/context/WebSocketContext";
import { useEffect } from "react";

// 使用者要求的更新頻率：5 分鐘 (300,000 毫秒)
const REFRESH_INTERVAL = 300000;

export function usePortfolioSummary() {
  const { data, error, isLoading, mutate } = useSWR("/api/dashboard/summary", fetcher, {
    refreshInterval: REFRESH_INTERVAL,
  });

  return {
    summary: data?.data || {},
    isLoading,
    isError: error,
    mutate,
  };
}

export function usePositions() {
  const { data, error, isLoading, mutate } = useSWR("/api/dashboard/positions", fetcher, {
    refreshInterval: REFRESH_INTERVAL,
  });

  return {
    positions: data?.data || [],
    isLoading,
    isError: error,
    mutate,
  };
}

export function useAgentsStatus() {
  const { data, error, isLoading, mutate } = useSWR("/api/dashboard/agents", fetcher, {
    refreshInterval: REFRESH_INTERVAL,
  });

  return {
    agents: data?.data || [],
    isLoading,
    isError: error,
    mutate,
  };
}

export function useIntelligenceBriefing() {
  const { data, error, isLoading, mutate } = useSWR("/api/dashboard/intelligence", fetcher, {
    refreshInterval: REFRESH_INTERVAL,
  });

  return {
    briefing: data?.data || {},
    isLoading,
    isError: error,
    mutate,
  };
}

export function useAlerts() {
  const { data, error, isLoading, mutate } = useSWR("/api/dashboard/alerts", fetcher, {
    refreshInterval: 60000, // 每分鐘更新一次
  });

  return {
    alerts: data?.data || [],
    isLoading,
    isError: error,
    mutate,
  };
}

/**
 * WebSocket 數據同步 Hook
 * 監聽後端推送並即時更新 SWR 快取
 */
export function useDashboardSocket() {
  const { lastMessage, status, stableStatus } = useWebSocket();

  useEffect(() => {
    if (lastMessage && lastMessage.type === "PORTFOLIO_UPDATE") {
      const { payload } = lastMessage;
      
      if (payload.summary) {
        mutate("/api/dashboard/summary", { status: "success", data: payload.summary }, false);
      }
      
      if (payload.positions) {
        mutate("/api/dashboard/positions", { status: "success", data: payload.positions }, false);
      }
    }
  }, [lastMessage]);

  return { status, stableStatus };
}
