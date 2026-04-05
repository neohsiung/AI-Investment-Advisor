import useSWR, { mutate } from "swr";
import { fetcher } from "@/lib/api";
import { useWebSocket } from "@/context/WebSocketContext";
import { useEffect } from "react";

// 使用者要求的更新頻率：10 分鐘 (600,000 毫秒)
const REFRESH_INTERVAL = 600000;

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
  const { lastMessage, missedMessages, status, stableStatus } = useWebSocket();

  // v7.2: Handle missed messages during reconnection
  useEffect(() => {
    if (missedMessages && missedMessages.length > 0) {
      console.log(`[Reconciliation] Processing ${missedMessages.length} missed events.`);
      
      // Update alerts cache with missed events
      mutate("/api/dashboard/alerts", (current: any) => {
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
        mutate("/api/dashboard/summary", { status: "success", data: payload.summary }, false);
      }
      if (payload.positions) {
        mutate("/api/dashboard/positions", { status: "success", data: payload.positions }, false);
      }
    }

    if (lastMessage.type === "SYSTEM_ALERT") {
      mutate("/api/dashboard/alerts", (current: any) => {
        const existing = current?.data || [];
        return { 
          ...current, 
          data: [lastMessage.payload, ...existing].slice(0, 50) 
        };
      }, false);
    }

    if (lastMessage.type === "AGENT_STATUS") {
      mutate("/api/dashboard/agents", (current: any) => {
        const existing = current?.data || [];
        const payload = lastMessage.payload;
        let newAgents = [...existing];
        const idx = newAgents.findIndex((a: any) => a.name === payload.agent);
        if (idx >= 0) {
          newAgents[idx] = { ...newAgents[idx], current_task: payload.message, last_active: payload.timestamp };
        } else {
          newAgents.push({ name: payload.agent, current_task: payload.message, last_active: payload.timestamp, role: "Active Agent", status: "active" });
        }
        return { ...current, data: newAgents };
      }, false);
    }
  }, [lastMessage]);

  return { status, stableStatus };
}
