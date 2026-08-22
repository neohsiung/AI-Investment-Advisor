"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { cn } from "@/lib/utils";
import { MessageSquare, ShieldAlert, Sparkles, Search } from "lucide-react";

type SessionSummary = {
  id: string;
  session_id: string;
  topic: string;
  consensus_preview: string;
  created_at: string;
};

type SessionDetail = SessionSummary & {
  consensus: string;
  transcript: string;
  transcript_entries: string[];
};

function parseEntry(entry: string): { agent: string; content: string; kind: "stance" | "risk_challenge" } {
  const match = entry.match(/^\[([^\]]+)\]:\s*([\s\S]*)$/);
  if (!match) return { agent: "?", content: entry, kind: "stance" };
  const agent = match[1];
  const kind = agent.toLowerCase().includes("risk challenge") ? "risk_challenge" : "stance";
  return { agent, content: match[2], kind };
}

export default function DecisionsPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const { data: listData } = useSWR("/api/v1/council/sessions?limit=30", fetcher);
  const sessions: SessionSummary[] = listData?.sessions || [];

  const { data: detailData, isLoading } = useSWR(
    selectedId ? `/api/v1/council/sessions/${selectedId}` : null,
    fetcher
  );
  const detail: SessionDetail | undefined = detailData?.session;

  return (
    <div className="flex-1 overflow-y-auto pt-16 sm:pt-20 lg:pt-24 px-4 sm:px-6 lg:px-8 pb-8 bg-background">
      <div className="mb-6 lg:mb-8">
        <h1 className="text-2xl lg:text-4xl font-bold font-headline tracking-tighter mb-2">
          議會辯論 <span className="text-primary/50 text-xl lg:text-2xl">Decisions</span>
        </h1>
        <p className="text-on-surface-variant font-label text-xs uppercase tracking-[0.3em]">
          每個 Agent 的立場、風險挑戰回合、最終共識 — 完整決策透明度
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Session list */}
        <div className="lg:col-span-1">
          <h2 className="text-sm font-bold uppercase tracking-widest text-on-surface-variant mb-3 flex items-center gap-2">
            <MessageSquare size={14} /> 近期議程
          </h2>
          <div className="space-y-2">
            {sessions.length === 0 && (
              <p className="text-xs text-on-surface-variant">尚無議會紀錄</p>
            )}
            {sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => setSelectedId(s.id)}
                className={cn(
                  "w-full text-left p-3 rounded-xl border transition-colors",
                  selectedId === s.id
                    ? "border-primary/50 bg-surface-container-high"
                    : "border-outline-variant/10 bg-surface-container-low hover:border-primary/30"
                )}
              >
                <p className="font-bold text-sm">{s.topic}</p>
                <p className="text-[10px] text-on-surface-variant mt-1 line-clamp-2">{s.consensus_preview}</p>
                <p className="text-[10px] text-on-surface-variant/60 mt-1">{new Date(s.created_at).toLocaleString()}</p>
              </button>
            ))}
          </div>
        </div>

        {/* Debate detail */}
        <div className="lg:col-span-2">
          {isLoading && <p className="text-xs text-on-surface-variant">載入中...</p>}
          {!detail && !isLoading && (
            <div className="h-64 flex items-center justify-center text-on-surface-variant text-sm border border-dashed border-outline-variant/20 rounded-2xl">
              選擇左側議程以檢視完整辯論過程
            </div>
          )}
          {detail && (
            <>
              <div className="bg-surface-container-low p-5 rounded-2xl border border-primary/20 mb-6">
                <p className="text-[10px] font-black uppercase text-primary tracking-widest mb-2 flex items-center gap-2">
                  <Sparkles size={12} /> 最終共識
                </p>
                <div className="text-sm whitespace-pre-wrap leading-relaxed">{detail.consensus}</div>
              </div>

              <h3 className="text-sm font-bold uppercase tracking-widest text-on-surface-variant mb-3">
                辯論過程 ({detail.transcript_entries.length} 則發言)
              </h3>
              <div className="space-y-3">
                {detail.transcript_entries.map((entry, i) => {
                  const { agent, content, kind } = parseEntry(entry);
                  const isRisk = kind === "risk_challenge";
                  return (
                    <div
                      key={i}
                      className={cn(
                        "p-4 rounded-xl border",
                        isRisk
                          ? "border-amber-500/40 bg-amber-500/5"
                          : "border-outline-variant/10 bg-surface-container-low"
                      )}
                    >
                      <p className={cn(
                        "text-[10px] font-black uppercase tracking-widest mb-2 flex items-center gap-1",
                        isRisk ? "text-amber-400" : "text-on-surface-variant"
                      )}>
                        {isRisk && <ShieldAlert size={12} />}
                        {agent}
                      </p>
                      <p className="text-xs whitespace-pre-wrap leading-relaxed text-on-surface">{content}</p>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
