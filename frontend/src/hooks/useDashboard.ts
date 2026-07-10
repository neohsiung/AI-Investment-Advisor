import useSWR, { mutate } from "swr";
import { apiClient } from "@/lib/api-client";
import { useWebSocket } from "@/context/WebSocketContext";
import { useEffect } from "react";
import { 
  DashboardMetrics, PositionItem, IntelligenceBriefing, AgentStatus, ApiResponse
} from "@/types/unified";

// Generic v1 fetcher for SWR
const v1Fetcher = (url: string) => apiClient.get<any>(url);

// 使用者要求的更新頻率：1 分鐘 (60,000 毫秒)
const REFRESH_INTERVAL = 60000;

export function usePortfolioSummary() {
  const { data, error, isLoading, mutate } = useSWR<ApiResponse<DashboardMetrics>>("/api/v1/dashboard/summary", v1Fetcher, {
    refreshInterval: REFRESH_INTERVAL,
    dedupingInterval: 30000,
  });

  return {
    summary: data?.data || ({} as DashboardMetrics),
    isLoading,
    isError: error,
    mutate,
  };
}

export function usePositions() {
  const { data, error, isLoading, mutate } = useSWR<ApiResponse<PositionItem[]>>("/api/v1/dashboard/positions", v1Fetcher, {
    refreshInterval: REFRESH_INTERVAL,
    dedupingInterval: 30000,
  });

  return {
    positions: data?.data || [],
    isLoading,
    isError: error,
    mutate,
  };
}

export function useAgentsStatus() {
  const { data, error, isLoading, mutate } = useSWR<ApiResponse<AgentStatus[]>>("/api/v1/dashboard/agents", v1Fetcher, {
    refreshInterval: REFRESH_INTERVAL,
    dedupingInterval: 30000,
  });

  return {
    agents: data?.data || [],
    isLoading,
    isError: error,
    mutate,
  };
}

export function useIntelligenceBriefing() {
  const { data, error, isLoading, mutate } = useSWR<ApiResponse<IntelligenceBriefing>>("/api/v1/dashboard/intelligence", v1Fetcher, {
    refreshInterval: REFRESH_INTERVAL,
    dedupingInterval: 30000,
  });

  return {
    briefing: data?.data || ({} as IntelligenceBriefing),
    isLoading,
    isError: error,
    mutate,
  };
}

export function useAlerts() {
  const { data, error, isLoading, mutate } = useSWR<ApiResponse<any[]>>("/dashboard/alerts", v1Fetcher, {
    refreshInterval: REFRESH_INTERVAL,
    dedupingInterval: 30000,
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
  const { lastMessage, missedMessages, status, stableStatus } = useWebSocket();

  // v7.2: Handle missed messages during reconnection
  useEffect(() => {
    if (missedMessages && missedMessages.length > 0) {
      console.log(`[Reconciliation] Processing ${missedMessages.length} missed events.`);
      
      // Update alerts cache with missed events
      mutate("/dashboard/alerts", (current: any) => {
        const existing = current?.data || [];
        // Extract only the payload (the actual alert)
        const newAlerts = missedMessages
          .filter(m => m.type === "SYSTEM_ALERT")
          .map(m => m.payload);
        
        return { 
          ...current, 
          data: [...newAlerts, ...existing].slice(0, 50) 
        };
      }, false);
    }
  }, [missedMessages]);

  useEffect(() => {
    if (!lastMessage) return;

    if (lastMessage.type === "PORTFOLIO_UPDATE") {
      const { payload } = lastMessage;
      if (payload.summary) {
        mutate("/dashboard/summary", { status: 'success', data: payload.summary }, false);
      }
      if (payload.positions) {
        mutate("/dashboard/positions", { status: 'success', data: payload.positions }, false);
      }
    }

    if (lastMessage.type === "SYSTEM_ALERT") {
      mutate("/dashboard/alerts", (current: any) => {
        const existing = current?.data || [];
        const newData = [lastMessage.payload, ...existing].slice(0, 50);
        return { ...current, status: 'success', data: newData };
      }, false);
    }

    if (lastMessage.type === "AGENT_STATUS") {
      mutate("/dashboard/agents", (current: any) => {
        const existing = current?.data || [];
        const payload = lastMessage.payload;
        let newAgents = [...existing];
        const idx = newAgents.findIndex((a: any) => a.name === payload.agent);
        if (idx >= 0) {
          newAgents[idx] = { ...newAgents[idx], current_task: payload.message, last_active: payload.timestamp };
        } else {
          newAgents.push({ name: payload.agent, current_task: payload.message, last_active: payload.timestamp, strategy: "Active Agent" });
        }
        return { ...current, status: 'success', data: newAgents };
      }, false);
    }
  }, [lastMessage]);

  return { status, stableStatus };
}
