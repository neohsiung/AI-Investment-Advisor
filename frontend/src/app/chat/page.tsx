"use client";

import React, { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import { Send, User, Loader2, Sparkles, MessageSquare, Trash2, ShieldCheck, TrendingUp, Cpu } from "lucide-react";
import { cn } from "@/lib/utils";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [activity, setActivity] = useState<string | null>(null);
  const [detectedTicker, setDetectedTicker] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isLoading, activity]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userPrompt = input.trim();
    setMessages((prev) => [...prev, { role: "user", content: userPrompt }]);
    setInput("");
    setIsLoading(true);
    setActivity("Initializing...");
    setDetectedTicker(null);

    // Prepare for streaming
    let assistantContent = "";
    const updateAssistantMessage = (content: string) => {
      setMessages((prev) => {
        const last = prev[prev.length - 1];
        if (last && last.role === "assistant") {
          return [...prev.slice(0, -1), { role: "assistant", content }];
        }
        return [...prev, { role: "assistant", content }];
      });
    };

    try {
      const response = await fetch("/api/dashboard/chat/stream", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userPrompt,
          history: messages.slice(-10)
        }),
      });

      if (!response.ok) throw new Error("Network response was not ok");
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        
        // SSE lines are separated by \n\n
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || ""; // Keep the last partial line in buffer

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const dataStr = line.slice(6).trim();
            if (dataStr === "[DONE]") {
              setActivity(null);
              continue;
            }

            try {
              const data = JSON.parse(dataStr);
              
              // Handle metadata (agent state)
              if (data.metadata) {
                if (data.metadata.type === "tool_call") {
                  setActivity(data.metadata.name);
                }
              } 
              // Handle content chunks
              else if (data.chunk) {
                assistantContent += data.chunk;
                updateAssistantMessage(assistantContent);
                // Hide activity once text starts flowing
                if (activity) setActivity(null); 
              }
              // Handle errors
              else if (data.error) {
                console.error("Stream error packet:", data.error);
              }
            } catch (e) {
              console.error("Error parsing stream JSON:", e, "Line:", line);
            }
          }
        }
      }
    } catch (error: any) {
      console.error("Chat error:", error);
      setMessages((prev) => [...prev, { role: "assistant", content: "抱歉，系統連線異常。請檢查後端服務狀態。" }]);
    } finally {
      setIsLoading(false);
      setActivity(null);
    }
  };

  const clearChat = () => {
    if (window.confirm("確定要清除所有對話紀錄嗎？")) {
      setMessages([]);
      setDetectedTicker(null);
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-background pt-16 overflow-hidden">
      {/* Header / Context Bar */}
      <div className="h-14 px-8 border-b border-outline-variant/10 flex items-center justify-between bg-surface/30 backdrop-blur-md z-10 sticky top-0">
        <div className="flex items-center gap-3">
          <div className="h-2 w-2 rounded-full bg-secondary animate-pulse" />
          <h2 className="text-sm font-black uppercase tracking-[0.2em] text-on-surface-variant">即時諮詢顧問 <span className="text-primary/50 text-[10px] ml-2 font-mono uppercase">V10_Traceable_Stream</span></h2>
        </div>
        <div className="flex items-center gap-6">
          {detectedTicker && (
            <div className="flex items-center gap-2 px-3 py-1 bg-primary/10 rounded-full border border-primary/20 animate-fade-in">
              <TrendingUp size={12} className="text-primary" />
              <span className="text-[10px] font-black text-primary uppercase tracking-widest">標的識别: {detectedTicker}</span>
            </div>
          )}
          <button 
            onClick={clearChat}
            className="p-2 text-on-surface-variant hover:text-error hover:bg-error/10 rounded-full transition-all"
            title="Clear Chat"
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {/* Message List */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-8 space-y-8 scroll-smooth">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center opacity-20 gap-12 py-24">
             <div className="relative">
                <div className="absolute inset-0 bg-primary/20 blur-[100px] scale-150 animate-pulse rounded-full" />
                <Sparkles size={120} className="text-primary relative z-10" />
             </div>
             <div className="max-w-md text-center space-y-4">
                <h3 className="text-3xl font-bold font-headline tracking-tighter text-on-surface">我是您的專屬 AI 投資顧問</h3>
                <p className="text-xs font-bold uppercase tracking-widest leading-relaxed">
                  您可以詢問市場行情、公司基本面分析、或是投資組合的建議。
                  <br />
                  <span className="text-secondary mt-2 block font-mono">L4 AUTONOMY / TRACEABLE_SSE READY</span>
                </p>
             </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div 
              key={idx} 
              className={cn(
                "flex gap-6 max-w-4xl mx-auto group animate-fade-in",
                msg.role === "user" ? "flex-row-reverse" : "flex-row"
              )}
            >
              <div className={cn(
                "h-10 w-10 rounded-2xl flex items-center justify-center flex-shrink-0 shadow-lg border border-outline-variant/10",
                msg.role === "assistant" ? "bg-primary text-on-primary" : "bg-surface-container-highest text-on-surface"
              )}>
                {msg.role === "assistant" ? <Sparkles size={20} /> : <User size={20} />}
              </div>
              <div className={cn(
                "flex-1 px-8 py-6 rounded-3xl text-sm leading-relaxed shadow-sm",
                msg.role === "assistant" 
                  ? "bg-surface-container-low border border-outline-variant/10" 
                  : "bg-surface-container-highest/50 border border-outline-variant/5 ml-12"
              )}>
                <div className="prose prose-invert prose-slate max-w-none prose-p:leading-8 prose-p:mb-4">
                  <ReactMarkdown
                    components={{
                      h1: ({ node, ...props }) => <h1 className="text-xl font-bold mb-4 text-primary" {...props} />,
                      h2: ({ node, ...props }) => <h2 className="text-lg font-bold mb-3 text-on-surface" {...props} />,
                      p: ({ node, ...props }) => <p className="mb-4" {...props} />,
                      ul: ({ node, ...props }) => <ul className="list-disc pl-5 mb-4 space-y-1" {...props} />,
                      code: ({ node, ...props }) => <code className="bg-surface-container-highest px-1 py-0.5 rounded font-mono text-xs text-secondary" {...props} />,
                    }}
                  >
                    {msg.content}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          ))
        )}
        
        {(isLoading || activity) && (
          <div className="flex gap-6 max-w-4xl mx-auto animate-fade-in">
            <div className="h-10 w-10 rounded-2xl bg-primary text-on-primary flex items-center justify-center shadow-lg animate-pulse">
              {activity ? <Cpu size={20} className="animate-spin" /> : <Loader2 size={20} className="animate-spin" />}
            </div>
            <div className="flex-1 px-8 py-6 rounded-3xl bg-surface-container-low border border-outline-variant/10 shadow-sm flex flex-col gap-2">
              <div className="flex items-center gap-3">
                <div className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce [animation-delay:-0.3s]" />
                <div className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce [animation-delay:-0.15s]" />
                <div className="h-1.5 w-1.5 rounded-full bg-primary animate-bounce" />
                <span className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant italic">
                  {activity ? `AGENT ACTION: ${activity}` : "正在分析市場數據與策略模型..."}
                </span>
              </div>
              {activity && (
                <div className="mt-2 h-1 w-full bg-surface-variant rounded-full overflow-hidden">
                  <div className="h-full bg-primary animate-progress-indeterminate w-1/3" />
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Input Area */}
      <div className="h-32 px-12 pb-12 bg-gradient-to-t from-background via-background to-transparent z-10">
        <div className="max-w-4xl mx-auto relative group">
          <div className="absolute -inset-1 bg-gradient-to-r from-primary/20 to-secondary/20 rounded-2xl blur opacity-30 group-hover:opacity-100 transition duration-1000 group-hover:duration-200" />
          <div className="relative bg-surface-container p-2 rounded-2xl border border-outline-variant/10 flex items-center gap-2 shadow-2xl">
            <input 
              type="text" 
              placeholder="輸入您的理財提問..."
              className="flex-1 bg-transparent border-none focus:ring-0 px-6 py-4 text-sm font-label tracking-wide"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
            />
            <button 
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
              className={cn(
                "h-12 w-12 rounded-xl flex items-center justify-center transition-all duration-300 active:scale-95 shadow-lg",
                input.trim() ? "bg-primary text-on-primary hover:shadow-primary/20" : "bg-surface-variant text-on-surface-variant/30"
              )}
            >
              <Send size={18} />
            </button>
          </div>
          <div className="flex justify-between items-center mt-3 px-2">
            <div className="flex items-center gap-4 text-[9px] font-black uppercase tracking-widest text-on-surface-variant/40">
              <div className="flex items-center gap-1.5">
                <ShieldCheck size={10} />
                L4 TRACEABLE MODE
              </div>
              <div className="flex items-center gap-1.5">
                <MessageSquare size={10} />
                REAL-TIME PULSE
              </div>
            </div>
            <p className="text-[9px] font-medium text-on-surface-variant/40">Quantum AI Agent System v10.0</p>
          </div>
        </div>
      </div>
    </div>
  );
}
