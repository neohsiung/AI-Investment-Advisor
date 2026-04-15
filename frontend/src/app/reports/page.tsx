"use client";

import React, { useState } from "react";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import ReactMarkdown from "react-markdown";
import { FileText, Calendar, Search, ChevronRight, Download, Share2, Filter, Loader2 } from "lucide-react";
import { format } from "date-fns";
import { cn } from "@/lib/utils";

export default function ReportsPage() {
  const { data: reportsData, isLoading } = useSWR("/api/v1/dashboard/reports", fetcher);
  const [selectedReport, setSelectedReport] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState("");

  const reports = reportsData?.data || [];
  const filteredReports = reports.filter((r: any) => 
    r.summary.toLowerCase().includes(searchQuery.toLowerCase()) || 
    r.content.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <div className="flex-1 flex overflow-hidden bg-background pt-16">
      {/* Sidebar - Report List */}
      <div className="w-96 border-r border-outline-variant/10 flex flex-col bg-surface-container-low">
        <div className="p-6 border-b border-outline-variant/10">
          <h1 className="text-2xl font-bold font-headline tracking-tight mb-4">分析報告 <span className="text-primary/40 text-sm italic">Reports</span></h1>
          <div className="relative">
            <input 
              type="text" 
              placeholder="搜尋報告內容..."
              className="w-full bg-surface-container-high border-none rounded-xl py-2 pl-10 pr-4 text-sm focus:ring-1 focus:ring-primary/30 transition-all font-label"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
            />
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant h-4 w-4" />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center h-64 opacity-50">
              <Loader2 className="animate-spin mb-2" />
              <p className="text-[10px] font-black uppercase tracking-widest">載入報告庫...</p>
            </div>
          ) : filteredReports.length > 0 ? (
            <div className="divide-y divide-outline-variant/5">
              {filteredReports.map((report: any, idx: number) => {
                const isSelected = selectedReport?.date === report.date;
                return (
                  <button 
                    key={idx}
                    onClick={() => setSelectedReport(report)}
                    className={cn(
                      "w-full text-left p-6 transition-all duration-200 group relative",
                      isSelected ? "bg-primary/5" : "hover:bg-surface-variant/50"
                    )}
                  >
                    {isSelected && <div className="absolute left-0 top-0 bottom-0 w-1 bg-primary" />}
                    <div className="flex justify-between items-start mb-2">
                      <div className="flex items-center gap-2 text-[10px] font-black text-on-surface-variant/60 uppercase tracking-widest">
                        <Calendar size={12} />
                        {report.date ? format(new Date(report.date), "yyyy/MM/dd") : "Unknown Date"}
                      </div>
                      <ChevronRight size={14} className={cn("transition-transform", isSelected ? "rotate-90 text-primary" : "group-hover:translate-x-1")} />
                    </div>
                    <h3 className={cn("font-bold text-sm mb-2 line-clamp-2 leading-relaxed", isSelected ? "text-primary" : "text-on-surface")}>
                      {report.summary}
                    </h3>
                    <p className="text-[10px] text-on-surface-variant line-clamp-2 leading-relaxed opacity-70">
                      {report.content}
                    </p>
                  </button>
                );
              })}
            </div>
          ) : (
            <div className="p-12 text-center opacity-30 flex flex-col items-center gap-4">
              <FileText size={48} />
              <p className="text-xs font-bold uppercase tracking-widest leading-relaxed">未找到相關報告</p>
            </div>
          )}
        </div>
      </div>

      {/* Main Content - Report Viewer */}
      <div className="flex-1 flex flex-col bg-background overflow-hidden relative">
        {selectedReport ? (
          <>
            {/* Toolbar */}
            <div className="h-16 px-8 border-b border-outline-variant/10 flex items-center justify-between bg-surface/50 backdrop-blur-sm z-10 sticky top-0">
               <div className="flex items-center gap-4">
                  <div className="p-2 bg-primary/10 rounded-lg text-primary">
                    <FileText size={20} />
                  </div>
                  <h2 className="font-bold font-headline text-on-surface tracking-tight truncate max-w-md">
                    {selectedReport.summary}
                  </h2>
               </div>
               <div className="flex gap-2">
                 <button className="p-2 text-on-surface-variant hover:bg-surface-variant rounded-full transition-all" title="Download PDF">
                   <Download size={18} />
                 </button>
                 <button className="p-2 text-on-surface-variant hover:bg-surface-variant rounded-full transition-all" title="Share Report">
                   <Share2 size={18} />
                 </button>
               </div>
            </div>

            {/* Markdown Viewer */}
            <div className="flex-1 overflow-y-auto p-12 lg:px-24 xl:px-32">
              <div className="prose prose-invert prose-slate max-w-none">
                <div className="mb-12 border-b border-outline-variant/20 pb-12">
                   <p className="text-[10px] font-black text-primary uppercase tracking-[0.3em] mb-4">Investment Insight Report</p>
                   <h1 className="text-5xl font-bold font-headline tracking-tighter text-on-surface mb-8 leading-tight">
                     {selectedReport.summary}
                   </h1>
                   <div className="flex gap-8 items-center text-xs font-bold text-on-surface-variant/60">
                     <div className="flex items-center gap-2 uppercase tracking-widest">
                       <Calendar size={14} />
                       {format(new Date(selectedReport.date), "PPP")}
                     </div>
                     <div className="flex items-center gap-2 uppercase tracking-widest">
                       <div className="h-1.5 w-1.5 rounded-full bg-secondary" />
                       SYSTEM GENERATED
                     </div>
                   </div>
                </div>

                <div className="prose-content text-on-surface/80 leading-relaxed text-lg font-body">
                  <ReactMarkdown
                    components={{
                      h1: ({ ...props }) => <h1 className="text-3xl font-bold mt-12 mb-6 text-primary" {...props} />,
                      h2: ({ ...props }) => <h2 className="text-2xl font-bold mt-10 mb-4 text-on-surface border-l-4 border-primary pl-4" {...props} />,
                      p: ({ ...props }) => <p className="mb-6 leading-8" {...props} />,
                      ul: ({ ...props }) => <ul className="list-disc pl-6 mb-6 space-y-2" {...props} />,
                      code: ({ ...props }) => <code className="bg-surface-container-highest px-1.5 py-0.5 rounded font-mono text-sm text-secondary" {...props} />,
                    }}
                  >
                    {selectedReport.content}
                  </ReactMarkdown>
                </div>
              </div>
              
              <div className="mt-24 pt-12 border-t border-outline-variant/10 text-center opacity-30">
                 <p className="text-[10px] font-black uppercase tracking-widest mb-2">© 2026 ANTIGRAVITY INVESTMENT GROUP</p>
                 <p className="text-[9px] font-bold">Confidential. For authorized users only.</p>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center gap-8 p-12 text-center opacity-20 group">
             <div className="relative">
                <FileText size={180} className="text-on-surface-variant group-hover:scale-105 transition-transform duration-700" />
                <div className="absolute inset-0 bg-primary/20 blur-3xl rounded-full" />
             </div>
             <div>
                <h3 className="text-2xl font-bold font-headline tracking-tight mb-2">請選擇一份報告</h3>
                <p className="text-xs font-bold uppercase tracking-widest">點擊左側列表以查看詳細投資分析與建議。</p>
             </div>
          </div>
        )}
      </div>
    </div>
  );
}
