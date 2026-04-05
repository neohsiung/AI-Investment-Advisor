import React from "react";
import { ISentimentMetric } from "@/features/intelligence/domain/types";

interface BriefingCardProps {
  summary: string;
  recommendation: string;
  note: string;
  status: string;
  metrics: ISentimentMetric[];
  className?: string;
}

export default function BriefingCard({ 
  summary, 
  recommendation, 
  note, 
  status, 
  metrics,
  className = "" 
}: BriefingCardProps) {
  return (
    <div className={`bg-surface-container-low rounded-xl shadow-lg border border-outline-variant/10 overflow-hidden flex flex-col transition-all hover:shadow-xl ${className}`}>
      <div className="p-6 border-b border-outline-variant/10 flex justify-between items-center bg-surface-container">
        <div className="flex flex-col">
          <h3 className="text-lg font-black font-headline text-on-surface tracking-tighter uppercase">
            AI 市場報告
          </h3>
          <span className="text-[10px] font-mono text-secondary-container bg-secondary/10 px-1.5 py-0.5 rounded w-fit mt-1 uppercase tracking-widest font-black">
            {status}
          </span>
        </div>
        <div className="h-8 w-8 rounded-full bg-primary/10 flex items-center justify-center">
           <span className="material-symbols-outlined text-sm text-primary animate-pulse">analytics</span>
        </div>
      </div>
      
      <div className="p-6 space-y-6 flex-1">
        <div>
          <h4 className="text-[10px] font-label font-black uppercase tracking-[0.2em] text-on-surface-variant mb-3 flex items-center gap-2">
            <span className="h-1 w-4 bg-primary rounded-full"></span>
            執行摘要 (Executive Summary)
          </h4>
          <p className="text-sm font-light text-on-surface leading-loose">
            {summary}
          </p>
        </div>

        <div className="bg-surface-container-high p-4 rounded-lg border border-outline-variant/5">
          <h4 className="text-[10px] font-label font-black uppercase tracking-[0.2em] text-primary mb-2">核心操作建議</h4>
          <p className="text-sm font-bold text-on-surface">{recommendation}</p>
          <div className="mt-3 pt-3 border-t border-outline-variant/10">
            <p className="text-[10px] italic text-on-surface-variant leading-relaxed">
              <span className="font-bold uppercase not-italic mr-1 text-secondary">AI NOTE:</span> 
              {note}
            </p>
          </div>
        </div>

        <div className="space-y-4">
          <h4 className="text-[10px] font-label font-black uppercase tracking-[0.2em] text-on-surface-variant">情緒多維度指標 (Sentiment)</h4>
          {metrics.map((metric, i) => (
            <div key={i} className="space-y-1.5">
              <div className="flex justify-between text-[10px] font-bold uppercase tracking-widest">
                <span className="text-on-surface-variant">{metric.label}</span>
                <span className="text-on-surface">{metric.value}%</span>
              </div>
              <div className="h-1.5 w-full bg-surface-container-highest rounded-full overflow-hidden">
                <div 
                  className={`h-full ${metric.color} transition-all duration-1000 ease-out`}
                  style={{ width: `${metric.value}%` }}
                ></div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
