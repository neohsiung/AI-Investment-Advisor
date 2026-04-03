"use client";

import React, { createContext, useContext, useEffect, useRef, useState, ReactNode } from "react";
import { useAuth } from "@/hooks/useAuth";

type ConnectionStatus = "CONNECTING" | "CONNECTED" | "DISCONNECTED" | "ERROR";

interface WebSocketContextType {
  status: ConnectionStatus;
  lastMessage: any;
  sendMessage: (msg: string) => void;
}

const WebSocketContext = createContext<WebSocketContextType | undefined>(undefined);

export const WebSocketProvider = ({ children }: { children: ReactNode }) => {
  const { user } = useAuth();
  const [status, setStatus] = useState<ConnectionStatus>("DISCONNECTED");
  const [lastMessage, setLastMessage] = useState<any>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const connect = () => {
    if (!user) return;
    
    // Using relative URL for proxy support or absolute for dev
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.hostname === "localhost" ? "localhost:8000" : window.location.host;
    const wsUrl = `${protocol}//${host}/api/dashboard/ws`;

    console.log(`[WS] Connecting to ${wsUrl}...`);
    setStatus("CONNECTING");

    const socket = new WebSocket(wsUrl);

    socket.onopen = () => {
      console.log("[WS] Connected");
      setStatus("CONNECTED");
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
    };

    socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLastMessage(data);
      } catch (err) {
        console.error("[WS] Message parse error:", err);
      }
    };

    socket.onclose = (event) => {
      console.log(`[WS] Disconnected: ${event.code}`);
      setStatus("DISCONNECTED");
      
      // Auto reconnect after 5 seconds if not a normal closure
      if (event.code !== 1000 && user) {
        reconnectTimeoutRef.current = setTimeout(() => {
          connect();
        }, 5000);
      }
    };

    socket.onerror = (error) => {
      console.error("[WS] Socket error:", error);
      setStatus("ERROR");
    };

    socketRef.current = socket;
  };

  useEffect(() => {
    if (user) {
      connect();
    } else {
      if (socketRef.current) {
        socketRef.current.close(1000); // Normal closure
      }
    }

    return () => {
      if (socketRef.current) {
        socketRef.current.close(1000);
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [user]);

  const sendMessage = (msg: string) => {
    if (socketRef.current && socketRef.current.readyState === WebSocket.OPEN) {
      socketRef.current.send(msg);
    }
  };

  return (
    <WebSocketContext.Provider value={{ status, lastMessage, sendMessage }}>
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
