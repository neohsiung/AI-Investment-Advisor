"use client";

import React, { useState, useEffect, useRef } from "react";
import { useWebSocket } from "@/context/WebSocketContext";
import { cn, formatCurrency } from "@/lib/utils";
import { Terminal as TerminalIcon, Send, ShieldAlert, Cpu, ChevronRight, X } from "lucide-react";

interface LogEntry {
  id: string;
  timestamp: string;
  type: "system" | "agent" | "trade" | "error";
  message: string;
  payload?: any;
}

export default function Terminal() {
  const { lastMessage, sendMessage, status } = useWebSocket();
  const [logs, setLogs] = useState<LogEntry[]>([
    {
      id: "initial",
      timestamp: new Date().toLocaleTimeString(),
      type: "system",
      message: "QUANTUM SENTINEL v5.0.1 - 指令終端機已就緒。"
    }
  ]);
  const [autoScroll, setAutoScroll] = useState(true);
  const logEndRef = useRef<HTMLDivElement>(null);
  
  // Trade Form State
  const [ticker, setTicker] = useState("");
  const [action, setAction] = useState<"BUY" | "SELL">("BUY");
  const [quantity, setQuantity] = useState("");
  const [isExecuting, setIsExecuting] = useState(false);

  // Handle incoming messages
  useEffect(() => {
    if (lastMessage) {
      let newLog: LogEntry | null = null;

      if (lastMessage.type === "TRADE_RESULT") {
        newLog = {
          id: Math.random().toString(36).substr(2, 9),
          timestamp: new Date().toLocaleTimeString(),
          type: "trade",
          message: `交易執行：${lastMessage.payload.status === 'success' ? '成功' : '失敗'} - ${lastMessage.payload.reason || "完成"}`,

          payload: lastMessage.payload
        };
        setIsExecuting(false);
      } else if (lastMessage.type === "AGENT_THOUGHT") {
        newLog = {
          id: Math.random().toString(36).substr(2, 9),
          timestamp: new Date().toLocaleTimeString(),
          type: "agent",
          message: `[代理人]: ${lastMessage.payload.thought}`

        };
      }

      if (newLog) {
        setLogs(prev => [...prev.slice(-49), newLog!]);
      }
    }
  }, [lastMessage]);

  useEffect(() => {
    if (autoScroll && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [logs, autoScroll]);

  const handleExecute = () => {
    if (!ticker || !quantity || isExecuting) return;

    setIsExecuting(true);
    const command = {
      type: "EXECUTE_ORDER",
      payload: {
        ticker: ticker.trim().toUpperCase(),
        action,
        quantity: parseFloat(quantity)
      }
    };

    sendMessage(JSON.stringify(command));
    
    setLogs(prev => [...prev.slice(-49), {
      id: Math.random().toString(36).substr(2, 9),
      timestamp: new Date().toLocaleTimeString(),
      type: "system",
      message: `指令已發送：執行訂單 ${action === 'BUY' ? '買入' : '賣出'} ${quantity} 單位 ${ticker.toUpperCase()}`

    }]);
  };

  return (
    <div className="flex flex-col h-[500px] bg-surface-container-lowest border border-outline-variant/30 rounded-xl overflow-hidden shadow-2xl">
      {/* Terminal Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface-container-highest/50 border-b border-outline-variant/20">
        <div className="flex items-center gap-2">
          <TerminalIcon className="w-4 h-4 text-primary" />
          <span className="font-label text-[10px] uppercase tracking-widest font-bold">指令中心 (Command Hub)</span>

        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <div className={cn("w-1.5 h-1.5 rounded-full animate-pulse", 
              status === "CONNECTED" ? "bg-secondary" : "bg-error"
            )} />
            <span className="font-label text-[9px] uppercase tracking-tighter opacity-70">{status === 'CONNECTED' ? '連線中' : '中斷'}</span>

          </div>
          <button onClick={() => setLogs([])} className="text-on-surface-variant hover:text-on-surface transition-colors">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Logs Area */}
        <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] space-y-1.5 scrollbar-hide bg-black/40">
          {logs.map((log) => (
            <div key={log.id} className={cn(
              "flex gap-3 animate-in slide-in-from-left-2 duration-300",
              log.type === "error" ? "text-error" : 
              log.type === "trade" ? "text-secondary" : 
              log.type === "agent" ? "text-tertiary" : "text-on-surface-variant"
            )}>
              <span className="opacity-40 shrink-0">{log.timestamp}</span>
              <span className="flex-1 break-all select-all">
                {log.type === "system" && <span className="text-primary mr-2">»</span>}
                {log.type === "agent" && <Cpu className="inline w-3 h-3 mr-2 -mt-0.5" />}
                {log.message}
              </span>
            </div>
          ))}
          <div ref={logEndRef} />
        </div>

        {/* Quick Actions Sidebar */}
        <div className="w-64 bg-surface-container-low/30 border-l border-outline-variant/20 p-4 flex flex-col gap-4">
          <div className="space-y-3">
            <h3 className="font-label text-[10px] uppercase tracking-widest text-primary font-bold">快速執行</h3>

            
            {/* Ticker */}
            <div className="space-y-1">
              <label className="font-label text-[9px] uppercase tracking-tighter opacity-50 block ml-1">資產代碼 (Ticker)</label>

              <input 
                type="text" 
                value={ticker}
                onChange={(e) => setTicker(e.target.value)}
                placeholder="GOOG, TSLA..."
                className="w-full bg-surface-container px-3 py-2 rounded font-label text-xs uppercase border border-outline-variant/20 focus:border-primary outline-none transition-all"
              />
            </div>

            {/* Action Toggles */}
            <div className="flex gap-1 p-1 bg-surface-container rounded border border-outline-variant/10">
              <button 
                onClick={() => setAction("BUY")}
                className={cn(
                  "flex-1 py-1.5 rounded font-label text-[10px] uppercase tracking-wider transition-all",
                  action === "BUY" ? "bg-secondary text-on-secondary shadow-sm" : "hover:bg-surface-variant/50 opacity-60"
                )}
              >
                買入
              </button>
              <button 
                onClick={() => setAction("SELL")}
                className={cn(
                  "flex-1 py-1.5 rounded font-label text-[10px] uppercase tracking-wider transition-all",
                  action === "SELL" ? "bg-error text-on-error shadow-sm" : "hover:bg-surface-variant/50 opacity-60"
                )}
              >
                賣出
              </button>

            </div>

            {/* Quantity */}
            <div className="space-y-1">
              <label className="font-label text-[9px] uppercase tracking-tighter opacity-50 block ml-1">數量 (單位/金額)</label>

              <input 
                type="number" 
                value={quantity}
                onChange={(e) => setQuantity(e.target.value)}
                placeholder="0.00"
                className="w-full bg-surface-container px-3 py-2 rounded font-label text-xs border border-outline-variant/20 focus:border-primary outline-none transition-all"
              />
            </div>

            {/* Execute Button */}
            <button 
              onClick={handleExecute}
              disabled={!ticker || !quantity || isExecuting || status !== "CONNECTED"}
              className={cn(
                "w-full py-3 rounded-md flex items-center justify-center gap-2 font-label text-xs uppercase tracking-widest transition-all active:scale-95",
                isExecuting ? "bg-surface-variant opacity-50 pointer-events-none" :
                action === "BUY" ? "bg-secondary text-on-secondary" : "bg-error text-on-error"
              )}
            >
              {isExecuting ? (
                <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              ) : (
                <>
                  <Send className="w-3.5 h-3.5" />
                  執行交易
                </>
              )}
            </button>
          </div>

          <div className="mt-auto border-t border-outline-variant/10 pt-4">
             <div className="flex items-start gap-2 p-2 bg-tertiary-container/10 rounded border border-tertiary/20">
               <ShieldAlert className="w-3.5 h-3.5 text-tertiary shrink-0 mt-0.5" />
               <p className="text-[9px] text-on-surface-variant font-label leading-relaxed uppercase opacity-70">
                 市價單將繼承所有 Sentinel 監控守則，包含持倉上限與現金水位。
               </p>
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}
