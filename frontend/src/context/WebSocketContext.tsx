"use client";

import React, { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { useAuth } from "@/hooks/useAuth";

type ConnectionStatus = "CONNECTING" | "CONNECTED" | "DISCONNECTED" | "ERROR";

interface WebSocketContextType {
  status: ConnectionStatus;
  stableStatus: "LIVE" | "POLLING"; // Debounced status for UI display
  lastMessage: any;
  missedMessages: any[]; // v7.2: Buffer for reconciled messages
  sendMessage: (msg: any) => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export const WebSocketProvider = ({ children }: { children: ReactNode }) => {
  const { user, isLoading: authLoading } = useAuth();
  const [status, setStatus] = useState<ConnectionStatus>("DISCONNECTED");
  const [stableStatus, setStableStatus] = useState<"LIVE" | "POLLING">("POLLING");
  const [lastMessage, setLastMessage] = useState<any>(null);
  const [missedMessages, setMissedMessages] = useState<any[]>([]);
  const [reconnectCount, setReconnectCount] = useState(0); // v5.2: Track retries for backoff
  
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const stabilizeTimerRef = useRef<any>(null);
  const lastTimestampRef = useRef<string | null>(null); // v7.2: Persistent last received timestamp

  const connect = (isRetry = false) => {
    if (!user) return;
    
    // Using relative URL for proxy support or absolute for dev
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.hostname === "localhost" ? "localhost:8000" : window.location.host;
    const wsUrl = `${protocol}//${host}/api/dashboard/ws`;

    console.log(`[WS] Connecting to ${wsUrl} (Attempt ${reconnectCount + 1})...`);
    setStatus("CONNECTING");

    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log("[WS] Connected");
      setStatus("CONNECTED");
      setReconnectCount(0); // Reset backoff on successful connection
      
      // v7.2: Trigger State Reconciliation if we have a previous timestamp
      if (lastTimestampRef.current) {
        console.log(`[WS] Reconciling state since ${lastTimestampRef.current}`);
        socket.send(JSON.stringify({
          type: "SYNC_STATE",
          payload: { last_received_at: lastTimestampRef.current }
        }));
      }

      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        
        // v7.2: Handle special SYNC_COMPLETE message
        if (data.type === "SYNC_COMPLETE") {
          console.log(`[WS] Reconciliation complete: ${data.payload.count} events recovered.`);
          setMissedMessages(data.payload.events);
          return;
        }

        // Track timestamp for future reconciliation
        if (data.payload?.timestamp) {
          lastTimestampRef.current = data.payload.timestamp;
        }
        
        setLastMessage(data);
      } catch (err) {
        console.error("[WS] Message parse error:", err);
      }
    };

    socket.onclose = (event) => {
      console.log(`[WS] Disconnected: ${event.code}`);
      setStatus("DISCONNECTED");
      
      // Auto reconnect with Exponential Backoff
      if (event.code !== 1000 && user) {
        const nextCount = reconnectCount + 1;
        setReconnectCount(nextCount);
        
        // v5.2: Exponential Backoff Calculation
        // base 1s * 2^attempts, capped at 30s
        const delay = Math.min(1000 * Math.pow(2, reconnectCount), 30000);
        console.log(`[WS] Retrying in ${delay}ms...`);
        
        reconnectTimeoutRef.current = setTimeout(() => {
          connect(true);
        }, delay);
      }
    };

    socket.onerror = (error) => {
      console.error("[WS] Socket error:", error);
      setStatus("ERROR");
    };

    socketRef.current = socket;
  };

  useEffect(() => {
    // Only attempt websocket after auth has resolved + user is logged in
    if (authLoading) return;
    
    if (user) {
      connect();
    } else {
      if (socketRef.current) {
        socketRef.current.close(1000); // Normal closure
      }
      setStatus("DISCONNECTED");
      setReconnectCount(0);
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.close(1000);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (stabilizeTimerRef.current) {
        clearTimeout(stabilizeTimerRef.current);
      }
    };
  }, [user, authLoading]);

  // Debounce stableStatus: only flip to POLLING after 2s of non-CONNECTED state
  // This prevents flickering during brief reconnects
  useEffect(() => {
    if (stabilizeTimerRef.current) {
      clearTimeout(stabilizeTimerRef.current);
    }
    if (status === "CONNECTED") {
      setStableStatus("LIVE");
    } else {
      stabilizeTimerRef.current = setTimeout(() => {
        setStableStatus("POLLING");
      }, 2000); // 2s grace period before showing POLLING
    }
  }, [status]);

  const sendMessage = (msg: any) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      const payload = typeof msg === "string" ? msg : JSON.stringify(msg);
      socketRef.current.send(payload);
    }
  };

  return (
    <WebSocketContext.Provider value={{ status, stableStatus, lastMessage, missedMessages, sendMessage }}>
      {children}
    </WebSocketContext.Provider>
  );
};

export const useWebSocket = () => {
  const context = useContext(WebSocketContext);
  if (context === undefined) {
    throw new Error("useWebSocket must be used within a WebSocketProvider");
  }
  return context;
};
