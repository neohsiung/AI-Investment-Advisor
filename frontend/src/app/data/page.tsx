"use client";

import React, { useState } from "react";
import useSWR, { mutate } from "swr";
import axios from "axios";
import { fetcher } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";
import { 
  Database, Plus, Upload, History, Search, Trash2, 
  ArrowRightLeft, AlertCircle, CheckCircle2, Loader2, Download
} from "lucide-react";

export default function DataManagementPage() {
  const [activeTab, setActiveTab] = useState("manual");
  const { data: transData, isLoading: transLoading } = useSWR("/api/dashboard/data/transactions", fetcher);
  
  const transactions = transData?.data || [];

  // Form States
  const [form, setForm] = useState({
    ticker: "AAPL",
    action: "BUY",
    quantity: 1,
    price: 150,
    fees: 0,
    date: new Date().toISOString().split('T')[0],
    tradeMode: "qty", // "qty" or "lev"
    principal: 1000,
    leverage: 1
  });

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error', msg: string } | null>(null);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setIsSubmitting(true);
    setFeedback(null);
    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await axios.post("/api/dashboard/data/upload-csv", formData);
      setFeedback({ type: 'success', msg: res.data.message });
      mutate("/api/dashboard/data/transactions");
    } catch (err: any) {
      setFeedback({ type: 'error', msg: err.response?.data?.detail || "上傳失敗" });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setFeedback(null);

    try {
      let finalQty = form.quantity;
      if (form.tradeMode === "lev") {
        finalQty = (form.principal * form.leverage) / form.price;
      }

      await axios.post("/api/dashboard/data/transactions", {
        ticker: form.ticker,
        action: form.action,
        quantity: finalQty,
        price: form.price,
        fees: form.fees,
        date: form.date
      });

      setFeedback({ type: 'success', msg: "交易已成功記錄" });
      mutate("/api/dashboard/data/transactions");
    } catch (err: any) {
      setFeedback({ type: 'error', msg: err.response?.data?.detail || "新增失敗" });
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!window.confirm("確定要刪除此筆交易？這將會影響資產清算與績效統計。")) return;

    try {
      await axios.delete(`/api/dashboard/data/transactions/${id}`);
      mutate("/api/dashboard/data/transactions");
    } catch (err) {
      alert("刪除失敗");
    }
  };

  return (
    <div className="flex-1 flex flex-col bg-background pt-16 overflow-hidden">
      {/* Sidebar-like Tab Header */}
      <div className="px-8 border-b border-outline-variant/10 flex items-center justify-between bg-surface/30 backdrop-blur-md">
        <div className="flex">
          {[
            { id: "manual", label: "手動輸入", icon: Plus },
            { id: "history", label: "交易紀錄", icon: History },
            { id: "import", label: "CSV 匯入", icon: Upload },
            { id: "browser", label: "資料瀏覽", icon: Database },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "px-6 h-14 flex items-center gap-2 text-[10px] font-black uppercase tracking-widest transition-all relative",
                activeTab === tab.id ? "text-primary" : "text-on-surface-variant hover:text-on-surface hover:bg-surface-variant/50"
              )}
            >
              <tab.icon size={14} />
              {tab.label}
              {activeTab === tab.id && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 text-on-surface-variant/40 text-[9px] font-black tracking-widest uppercase">
          <Database size={12} />
          PostgreSQL Engine Connected
        </div>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-6xl mx-auto">
          
          {/* Manual Entry Tab */}
          {activeTab === "manual" && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 animate-fade-in">
              <div className="bg-surface-container-low p-8 rounded-3xl border border-outline-variant/10 shadow-sm self-start">
                <h2 className="text-xl font-bold font-headline tracking-tight mb-8">手動建立交易 <span className="text-primary/40 text-xs ml-2">Manual Transaction</span></h2>
                
                <form onSubmit={handleSubmit} className="space-y-6">
                  {/* Mode Switch */}
                  <div className="flex p-1 bg-surface-container-high rounded-xl gap-1">
                    <button 
                      type="button"
                      onClick={() => setForm({...form, tradeMode: 'qty'})}
                      className={cn("flex-1 py-2 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all", form.tradeMode === 'qty' ? "bg-primary text-on-primary shadow-sm" : "text-on-surface-variant hover:bg-surface-variant")}
                    >固定數量</button>
                    <button 
                      type="button"
                      onClick={() => setForm({...form, tradeMode: 'lev'})}
                      className={cn("flex-1 py-2 rounded-lg text-[9px] font-black uppercase tracking-widest transition-all", form.tradeMode === 'lev' ? "bg-primary text-on-primary shadow-sm" : "text-on-surface-variant hover:bg-surface-variant")}
                    >槓桿換算</button>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                       <label className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest ml-1">標的代號 (Ticker)</label>
                       <input 
                        type="text" value={form.ticker} onChange={(e) => setForm({...form, ticker: e.target.value.toUpperCase()})}
                        className="w-full bg-surface-container-highest border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-primary/30"
                       />
                    </div>
                    <div className="space-y-2">
                       <label className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest ml-1">日期 (Date)</label>
                       <input 
                        type="date" value={form.date} onChange={(e) => setForm({...form, date: e.target.value})}
                        className="w-full bg-surface-container-highest border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-primary/30"
                       />
                    </div>
                  </div>

                  <div className="space-y-2">
                     <label className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest ml-1">交易動作 (Action)</label>
                     <select 
                      value={form.action} onChange={(e) => setForm({...form, action: e.target.value})}
                      className="w-full bg-surface-container-highest border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-primary/30"
                     >
                       <option value="BUY">BUY - 買入</option>
                       <option value="SELL">SELL - 賣出</option>
                       <option value="DIVIDEND">DIVIDEND - 股息</option>
                       <option value="DEPOSIT">DEPOSIT - 資金存入</option>
                       <option value="WITHDRAWAL">WITHDRAWAL - 資金提取</option>
                     </select>
                  </div>

                  {form.tradeMode === 'qty' ? (
                    <div className="space-y-2">
                       <label className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest ml-1">成交數量 (Quantity)</label>
                       <input 
                        type="number" step="0.0001" value={form.quantity} onChange={(e) => setForm({...form, quantity: parseFloat(e.target.value)})}
                        className="w-full bg-surface-container-highest border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-primary/30"
                       />
                    </div>
                  ) : (
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                         <label className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest ml-1">保證金 (Principal)</label>
                         <input 
                          type="number" value={form.principal} onChange={(e) => setForm({...form, principal: parseFloat(e.target.value)})}
                          className="w-full bg-surface-container-highest border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-primary/30"
                         />
                      </div>
                      <div className="space-y-2">
                         <label className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest ml-1">槓桿倍數 (Leverage)</label>
                         <input 
                          type="number" step="0.1" value={form.leverage} onChange={(e) => setForm({...form, leverage: parseFloat(e.target.value)})}
                          className="w-full bg-surface-container-highest border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-primary/30"
                         />
                      </div>
                    </div>
                  )}

                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                       <label className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest ml-1">成交單價 (Price)</label>
                       <input 
                        type="number" step="0.0001" value={form.price} onChange={(e) => setForm({...form, price: parseFloat(e.target.value)})}
                        className="w-full bg-surface-container-highest border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-primary/30"
                       />
                    </div>
                    <div className="space-y-2">
                       <label className="text-[9px] font-black uppercase text-on-surface-variant tracking-widest ml-1">手續費 (Fees)</label>
                       <input 
                        type="number" step="0.01" value={form.fees} onChange={(e) => setForm({...form, fees: parseFloat(e.target.value)})}
                        className="w-full bg-surface-container-highest border-none rounded-xl px-4 py-3 text-sm focus:ring-1 focus:ring-primary/30"
                       />
                    </div>
                  </div>

                  {feedback && (
                    <div className={cn(
                      "p-4 rounded-xl flex gap-3 items-center text-xs font-bold",
                      feedback.type === 'success' ? "bg-secondary/10 text-secondary" : "bg-error/10 text-error"
                    )}>
                      {feedback.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                      {feedback.msg}
                    </div>
                  )}

                  <button 
                    disabled={isSubmitting}
                    className="w-full py-4 bg-primary text-on-primary font-bold rounded-xl shadow-lg shadow-primary/20 hover:scale-[1.02] transition-all active:scale-95 flex items-center justify-center gap-2"
                  >
                    {isSubmitting ? <Loader2 className="animate-spin" size={18} /> : <Plus size={18} />}
                    提交報行成交
                  </button>
                </form>
              </div>

              {/* Calculator Preview */}
              <div className="flex flex-col gap-6">
                 <div className="bg-surface-container-low p-8 rounded-3xl border border-outline-variant/10 shadow-sm">
                   <h3 className="text-xs font-black uppercase tracking-widest text-on-surface-variant mb-6">資產計算摘要 Summary</h3>
                   <div className="space-y-6">
                      <div className="flex justify-between items-end border-b border-outline-variant/5 pb-4">
                         <span className="text-xs text-on-surface-variant">購買力總額 (Nominal)</span>
                         <span className="text-xl font-bold font-mono">
                           {form.tradeMode === 'lev' 
                              ? formatCurrency(form.principal * form.leverage)
                              : formatCurrency(form.quantity * form.price)}
                         </span>
                      </div>
                      <div className="flex justify-between items-end border-b border-outline-variant/5 pb-4">
                         <span className="text-xs text-on-surface-variant">預估股數 (Qty)</span>
                         <span className="text-xl font-bold font-mono text-secondary">
                           {(form.tradeMode === 'lev' 
                              ? (form.principal * form.leverage) / form.price
                              : form.quantity).toFixed(4)}
                         </span>
                      </div>
                      <div className="flex justify-between items-end">
                         <span className="text-xs text-on-surface-variant">現金流變化 (Cash Path)</span>
                         <span className="text-lg font-bold font-mono text-error">
                           -{formatCurrency((form.tradeMode === 'lev' ? form.principal : (form.quantity * form.price / 1)) + form.fees)}
                         </span>
                      </div>
                   </div>
                 </div>

                 <div className="bg-primary/5 p-8 rounded-3xl border border-primary/10">
                   <div className="flex gap-4 items-start">
                     <AlertCircle className="text-primary mt-1" size={20} />
                     <div className="space-y-2">
                        <p className="text-[10px] font-black uppercase tracking-widest text-primary">重要提示</p>
                        <p className="text-xs text-on-surface-variant leading-relaxed">
                          手動輸入的交易將會觸發 <strong>System Snapshot</strong> 重新計算。請確保數據準確，特別是 Ticker 代號須符合 Yahoo Finance 格式。
                        </p>
                     </div>
                   </div>
                 </div>
              </div>
            </div>
          )}

          {/* History Tab */}
          {activeTab === "history" && (
            <div className="animate-fade-in bg-surface-container-low rounded-3xl border border-outline-variant/10 shadow-sm overflow-hidden">
               <div className="p-8 border-b border-outline-variant/10 flex justify-between items-center bg-surface/50">
                  <h2 className="text-xl font-bold font-headline tracking-tight">審計帳本 <span className="text-primary/40 text-xs ml-2">Audit Trail</span></h2>
                  <div className="flex items-center gap-4">
                    <div className="relative">
                      <input 
                        type="text" 
                        placeholder="搜尋標的..."
                        className="bg-surface-container-high border-none rounded-xl py-1.5 pl-9 pr-4 text-xs font-label"
                      />
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant/50 h-3.5 w-3.5" />
                    </div>
                    <button className="p-2 bg-surface-container-high rounded-full hover:bg-surface-variant transition-all">
                      <ArrowRightLeft size={16} />
                    </button>
                  </div>
               </div>
               
               <div className="overflow-x-auto">
                 <table className="w-full text-left border-collapse">
                   <thead className="bg-surface-container-high">
                     <tr>
                        {["日期", "代號", "動作", "數量", "價格", "金額", "手續費", ""].map((h, i) => (
                          <th key={i} className="px-6 py-4 text-[9px] font-black uppercase tracking-widest text-on-surface-variant/60">{h}</th>
                        ))}
                     </tr>
                   </thead>
                   <tbody className="divide-y divide-outline-variant/5">
                     {transLoading ? (
                       <tr>
                         <td colSpan={8} className="px-6 py-24 text-center">
                            <Loader2 className="animate-spin mx-auto mb-4 text-primary" />
                            <p className="text-[10px] font-black uppercase tracking-widest text-on-surface-variant">正在調閱加密交易帳本...</p>
                         </td>
                       </tr>
                     ) : transactions.length > 0 ? (
                       transactions.map((tr: any) => (
                        <tr key={tr.id} className="hover:bg-surface-variant/20 transition-all group">
                          <td className="px-6 py-4">
                             <p className="text-xs font-mono font-bold text-on-surface-variant">{tr.trade_date}</p>
                          </td>
                          <td className="px-6 py-4">
                             <span className="text-xs font-extrabold text-on-surface">{tr.ticker}</span>
                          </td>
                          <td className="px-6 py-4">
                             <span className={cn(
                               "text-[9px] font-black px-2 py-0.5 rounded-full uppercase tracking-tighter",
                               tr.action === "BUY" ? "bg-secondary/10 text-secondary" : 
                               tr.action === "SELL" ? "bg-error/10 text-error" : "bg-primary/10 text-primary"
                             )}>{tr.action}</span>
                          </td>
                          <td className="px-6 py-4 font-mono text-xs">{tr.quantity.toFixed(4)}</td>
                          <td className="px-6 py-4 font-mono text-xs">{formatCurrency(tr.price)}</td>
                          <td className="px-6 py-4 font-mono text-xs font-bold">{formatCurrency(tr.amount)}</td>
                          <td className="px-6 py-4 font-mono text-xs text-on-surface-variant/50">{formatCurrency(tr.fees)}</td>
                          <td className="px-6 py-4 text-right">
                            <button 
                              onClick={() => handleDelete(tr.id)}
                              className="p-2 text-on-surface-variant/30 hover:text-error hover:bg-error/10 rounded-full transition-all opacity-0 group-hover:opacity-100"
                            >
                              <Trash2 size={14} />
                            </button>
                          </td>
                        </tr>
                       ))
                     ) : (
                       <tr>
                         <td colSpan={8} className="px-6 py-24 text-center opacity-20">
                            <History size={48} className="mx-auto mb-4" />
                            <p className="text-xs font-bold uppercase tracking-widest">目前尚無任何交易紀錄</p>
                         </td>
                       </tr>
                     )}
                   </tbody>
                 </table>
               </div>
            </div>
          )}

          {/* Import Tab */}
          {activeTab === "import" && (
            <div className="animate-fade-in max-w-2xl mx-auto py-12">
               <div className="bg-surface-container-low p-12 rounded-[32px] border border-outline-variant/10 shadow-sm text-center">
                  <div className="h-24 w-24 bg-primary/10 rounded-3xl flex items-center justify-center mx-auto mb-8">
                     <Upload size={40} className="text-primary" />
                  </div>
                  <h2 className="text-3xl font-bold font-headline tracking-tighter mb-4">批次匯入 Broker 數據</h2>
                  <p className="text-on-surface-variant text-sm font-label leading-relaxed mb-6">
                     支援 IBKR, Futu 與自定義 CSV 格式。上傳後系統將自動解析並寫入交易帳本。
                  </p>

                  <div className="mb-8">
                     {feedback && (
                        <div className={cn(
                        "p-4 rounded-xl flex gap-3 items-center text-xs font-bold justify-center mb-6",
                        feedback.type === 'success' ? "bg-secondary/10 text-secondary" : "bg-error/10 text-error"
                        )}>
                        {feedback.type === 'success' ? <CheckCircle2 size={16} /> : <AlertCircle size={16} />}
                        {feedback.msg}
                        </div>
                     )}
                  </div>
                  
                  <div className="relative border-4 border-dashed border-outline-variant/20 rounded-[32px] p-16 hover:border-primary/30 transition-all group cursor-pointer overflow-hidden">
                     <input 
                        type="file" 
                        accept=".csv"
                        className="absolute inset-0 opacity-0 cursor-pointer z-10"
                        onChange={handleFileUpload}
                        disabled={isSubmitting}
                     />
                     <div className="relative z-0">
                        {isSubmitting ? (
                           <div className="flex flex-col items-center gap-4">
                              <Loader2 className="animate-spin text-primary" size={32} />
                              <p className="text-xs font-black uppercase tracking-widest text-primary">檔案處理中...</p>
                           </div>
                        ) : (
                           <p className="text-xs font-black uppercase tracking-[0.2em] text-on-surface-variant group-hover:text-primary transition-colors">
                              點擊或拖放 CSV 檔案
                           </p>
                        )}
                     </div>
                  </div>

                  <div className="mt-12 flex flex-col gap-6 items-center">
                     <p className="text-[10px] text-on-surface-variant/40 font-mono">
                        支援欄位: date, ticker, action (BUY/SELL), quantity, price
                     </p>
                     <button className="flex items-center gap-2 px-6 py-3 bg-surface-container-highest rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-surface-variant transition-all">
                       <Download size={14} />
                       下載 CSV 格式範本
                     </button>
                  </div>
               </div>
            </div>
          )}

          {/* Browser Tab */}
          {activeTab === "browser" && (
            <div className="animate-fade-in space-y-8 pb-12">
               <div className="bg-surface-container-low p-8 rounded-3xl border border-outline-variant/10 shadow-sm">
                  <div className="flex justify-between items-end mb-8">
                    <div>
                      <h2 className="text-xl font-bold font-headline tracking-tight">系統資料表架構 <span className="text-primary/40 text-xs ml-2">Schema Browser</span></h2>
                      <p className="text-on-surface-variant text-xs mt-2 font-light">
                        即時預覽 PostgreSQL 核心資料庫中的資料結構與索引配置。
                      </p>
                    </div>
                    <div className="bg-secondary/10 px-3 py-1 rounded-full text-[9px] font-black text-secondary uppercase tracking-widest border border-secondary/20">
                      LIVE SCHEMA
                    </div>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {[
                      { 
                        name: "transactions", 
                        desc: "交易帳本與資金流水", 
                        cols: ["id (UUID)", "user_id", "ticker", "action", "quantity", "price", "fees", "amount", "trade_date"]
                      },
                      { 
                        name: "settings", 
                        desc: "系統配置與 API 金鑰 (加密存储)", 
                        cols: ["user_id", "key", "value", "created_at", "updated_at"]
                      },
                      { 
                        name: "agent_states", 
                        desc: "Swarm 代理人運行狀態與權重", 
                        cols: ["agent_id", "status", "performance_score", "last_active", "assigned_task"]
                      },
                      { 
                        name: "market_intelligence", 
                        desc: "AI 回測與新聞特徵快照", 
                        cols: ["id", "source_url", "sentiment_score", "keywords", "risk_level", "timestamp"]
                      }
                    ].map(table => (
                      <div key={table.name} className="bg-surface-container-high/50 p-6 rounded-2xl border border-outline-variant/10 hover:border-primary/20 transition-all">
                        <div className="flex items-center gap-2 mb-4">
                           <Database size={16} className="text-primary" />
                           <h4 className="font-black text-xs uppercase tracking-[0.15em]">{table.name}</h4>
                        </div>
                        <p className="text-[10px] text-on-surface-variant mb-4 font-bold">{table.desc}</p>
                        <div className="flex flex-wrap gap-1.5 border-t border-outline-variant/5 pt-4">
                          {table.cols.map(col => (
                            <span key={col} className="bg-background/80 px-2 py-1 rounded-md text-[9px] font-mono border border-outline-variant/10 text-on-surface-variant/80">
                              {col}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
               </div>

               <div className="bg-primary/5 p-8 rounded-[32px] border border-primary/10 flex items-center justify-between">
                  <div className="flex gap-4 items-center">
                    <div className="p-3 bg-primary/10 rounded-2xl text-primary">
                      <Search size={24} />
                    </div>
                    <div>
                      <h4 className="font-bold text-sm">需要執行自定義 SQL 查詢？</h4>
                      <p className="text-xs text-on-surface-variant/60 font-light mt-1">
                        進階用戶可直接透過系統後台執行原子化 Query，或聯繫開發團隊開啟隱藏面板。
                      </p>
                    </div>
                  </div>
                  <button className="px-6 py-3 bg-primary text-on-primary font-black text-[10px] uppercase tracking-widest rounded-xl hover:scale-105 active:scale-95 transition-all">
                    SQL 控制台
                  </button>
               </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
