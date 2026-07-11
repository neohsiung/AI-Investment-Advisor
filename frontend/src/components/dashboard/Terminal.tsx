import React, { useState, useEffect, useRef } from "react";
import { useWebSocket } from "@/context/WebSocketContext";
import { apiClient } from "@/lib/api-client";
import { cn, formatCurrency } from "@/lib/utils";
import { Terminal as TerminalIcon, Send, ShieldAlert, Cpu, ChevronRight, X, Sparkles, Loader2 } from "lucide-react";

interface LogEntry {
  id: string;
  timestamp: string;
  type: "system" | "agent" | "trade" | "error" | "ai_advisor";
  message: string;
  payload?: any;
  isStreaming?: boolean;
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
  const [isTradePanelOpen, setIsTradePanelOpen] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);
  
  // Chat & Stream State
  const [inputMessage, setInputMessage] = useState("");
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [ticker, setTicker] = useState("");
  const [quantity, setQuantity] = useState("");
  const [action, setAction] = useState<"BUY" | "SELL">("BUY");

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
      } else if (lastMessage.type === "AGENT_STATUS") {
        newLog = {
          id: Math.random().toString(36).substr(2, 9),
          timestamp: new Date().toLocaleTimeString(),
          type: "system",
          message: `[狀態] ${lastMessage.payload.agent}: ${lastMessage.payload.message}`
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

  const handleSendChat = async () => {
    if (!inputMessage.trim() || isAiLoading) return;

    const userMsg: LogEntry = {
      id: Date.now().toString(),
      timestamp: new Date().toLocaleTimeString(),
      type: "system",
      message: `User: ${inputMessage}`
    };
    
    setLogs(prev => [...prev.slice(-49), userMsg]);
    const currentInput = inputMessage;
    setInputMessage("");
    setIsAiLoading(true);
    setActiveTool(null);

    // Initial placeholder for assistant response
    const assistantId = "ai-" + Date.now();
    let accumulatedResponse = "";

    apiClient.subscribeToStream(
      "/chat/stream",
      { message: currentInput, history: [] },
      (data) => {
        if (data.metadata?.type === "tool_call") {
          setActiveTool(data.metadata.name);
          setLogs(prev => {
             const existing = prev.find(l => l.id === assistantId);
             if (!existing) {
                return [...prev, {
                   id: assistantId,
                   timestamp: new Date().toLocaleTimeString(),
                   type: "ai_advisor",
                   message: `[Thinking: ${data.metadata.name}]...`,
                   isStreaming: true
                }];
             }
             return prev.map(l => l.id === assistantId ? { ...l, message: `[Thinking: ${data.metadata.name}]...` } : l);
          });
        }

        if (data.chunk) {
          setActiveTool(null);
          accumulatedResponse += data.chunk;
          setLogs(prev => {
             const existing = prev.find(l => l.id === assistantId);
             if (!existing) {
                return [...prev, {
                   id: assistantId,
                   timestamp: new Date().toLocaleTimeString(),
                   type: "ai_advisor",
                   message: accumulatedResponse,
                   isStreaming: true
                }];
             }
             return prev.map(l => l.id === assistantId ? { ...l, message: accumulatedResponse } : l);
          });
        }
      },
      (err) => {
        console.error("Chat Stream error", err);
        setIsAiLoading(false);
        setActiveTool(null);
        setLogs(prev => [...prev, {
          id: "err-" + Date.now(),
          timestamp: new Date().toLocaleTimeString(),
          type: "error",
          message: "無法與 AI 顧問建立連線。"
        }]);
      }
    );
    
    // Note: We don't await because it's a stream handler
    setIsAiLoading(false);
  };

  const handleExecute = async () => {
    if (!ticker || !quantity || isExecuting) return;

    setIsExecuting(true);
    try {
      const response = await apiClient.post<any>("/transactions", {
        ticker: ticker.trim().toUpperCase(),
        action,
        quantity: parseFloat(quantity),
        price: 0, // Market price
        fees: 0,
        date: new Date().toISOString()
      });
      
      setLogs(prev => [...prev.slice(-49), {
        id: Math.random().toString(36).substr(2, 9),
        timestamp: new Date().toLocaleTimeString(),
        type: "trade",
        message: `交易指令成功：${response.message || "已送入隊列"}`
      }]);
    } catch (e: any) {
      setLogs(prev => [...prev.slice(-49), {
        id: Math.random().toString(36).substr(2, 9),
        timestamp: new Date().toLocaleTimeString(),
        type: "error",
        message: `交易執行失敗：${e.message}`
      }]);
    } finally {
      setIsExecuting(false);
    }
  };

  return (
    <div className="flex flex-col h-[500px] bg-surface-container-lowest border border-outline-variant/30 rounded-xl overflow-hidden shadow-2xl relative">
      {/* Terminal Header */}
      <div className="flex items-center justify-between px-4 py-2 bg-surface-container-highest/50 border-b border-outline-variant/20 flex-shrink-0">
        <div className="flex items-center gap-2">
          <TerminalIcon className="w-4 h-4 text-primary" />
          <span className="font-label text-[10px] uppercase tracking-widest font-bold">指令中心 (Command Hub)</span>
        </div>
        <div className="flex items-center gap-3">
          {/* 行動端快速交易面板切換 */}
          <button
            onClick={() => setIsTradePanelOpen(!isTradePanelOpen)}
            className="md:hidden flex items-center gap-1 px-2 py-0.5 bg-surface-container border border-outline-variant/10 rounded text-[9px] font-label font-bold uppercase text-on-surface-variant hover:text-on-surface hover:bg-surface-variant transition-all active:scale-95"
          >
            <span className="material-symbols-outlined text-[10px]">tune</span>
            {isTradePanelOpen ? "關閉交易" : "快速交易"}
          </button>

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

      <div className="flex flex-col md:flex-row flex-1 overflow-hidden">
        {/* Left Column: Logs Area & Input */}
        <div className="flex-1 flex flex-col min-w-0 bg-black/60 relative">
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_center,rgba(0,102,214,0.05)_0%,transparent_70%)]" />
          
          {/* Logs Area */}
          <div className="flex-1 overflow-y-auto p-4 space-y-2 scrollbar-hide">
            {logs.map((log) => (
              <div key={log.id} className={cn(
                 "flex gap-3 animate-in fade-in slide-in-from-left-2 duration-500",
                 log.type === "error" ? "text-error drop-shadow-[0_0_8px_rgba(255,180,171,0.3)]" : 
                 log.type === "trade" ? "text-secondary font-bold" : 
                 log.type === "agent" ? "text-tertiary" : 
                 log.type === "ai_advisor" ? "text-primary brightness-150 leading-relaxed" : "text-on-surface-variant opacity-80"
              )}>
                <span className="opacity-30 shrink-0 select-none">[{log.timestamp}]</span>
                <span className="flex-1 break-all select-all">
                  {log.type === "system" && <span className="text-primary mr-2 font-black">»</span>}
                  {log.type === "agent" && <Cpu className="inline w-3 h-3 mr-2 -mt-0.5" />}
                  {log.type === "ai_advisor" && <Sparkles className="inline w-3 h-3 mr-2 -mt-0.5 text-primary animate-pulse" />}
                  {log.message}
                  {log.isStreaming && <span className="inline-block w-1.5 h-3.5 bg-primary ml-1.5 animate-pulse shadow-[0_0_10px_var(--primary)]" />}
                </span>
              </div>
            ))}
            {activeTool && (
              <div className="flex gap-3 text-tertiary/70 animate-pulse">
                 <span className="opacity-40 shrink-0">--:--:--</span>
                 <span className="flex-1 italic">
                   <Loader2 className="inline w-3 h-3 mr-2 animate-spin" />
                   Sentinel 正在執行工具: {activeTool}...
                 </span>
              </div>
            )}
            <div ref={logEndRef} />
          </div>

          {/* Command Input Area */}
          <div className="p-4 border-t border-outline-variant/10 bg-surface-container-lowest/80 backdrop-blur-md flex-shrink-0">
             <div className="relative flex items-center group">
                <div className="absolute -inset-0.5 bg-gradient-to-r from-primary/20 to-secondary/20 rounded-full blur opacity-30 group-focus-within:opacity-100 transition duration-1000 group-hover:duration-200"></div>
                <ChevronRight className="absolute left-4 w-4 h-4 text-primary z-10" />
                <input 
                   type="text"
                   value={inputMessage}
                   onChange={(e) => setInputMessage(e.target.value)}
                   onKeyDown={(e) => e.key === "Enter" && handleSendChat()}
                   placeholder="COMMAND INPUT > DISPATCH REQUEST TO SENTINEL..."
                   className="relative w-full bg-surface-container-low/40 backdrop-blur-2xl border border-outline-variant/30 rounded-full py-2.5 pl-11 pr-14 text-[11px] font-mono tracking-wider focus:border-primary/50 focus:bg-surface-container-low/60 outline-none transition-all shadow-2xl placeholder:opacity-30"
                />
                <button 
                   onClick={handleSendChat}
                   disabled={isAiLoading || !inputMessage.trim()}
                   className="absolute right-2 p-1.5 bg-primary text-on-primary rounded-full hover:scale-105 active:scale-95 transition-all disabled:opacity-30 shadow-lg shadow-primary/20 z-10"
                >
                   {isAiLoading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                </button>
             </div>
          </div>
        </div>

        {/* Right Column: Quick Actions Sidebar */}
        <div className={cn(
          "bg-surface-container-low/30 border-t md:border-t-0 md:border-l border-outline-variant/20 p-4 flex flex-col gap-4 transition-all duration-300",
          "w-full md:w-64 flex-shrink-0",
          isTradePanelOpen ? "flex h-[250px] md:h-auto overflow-y-auto" : "hidden md:flex"
        )}>
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

          <div className="mt-auto border-t border-outline-variant/10 pt-4 hidden md:block">
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
