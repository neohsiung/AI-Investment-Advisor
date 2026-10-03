"use client";

import React, { useState, useCallback } from "react";
import useSWR, { mutate } from "swr";
import api, { fetcher } from "@/lib/api";
import { formatCurrency, cn } from "@/lib/utils";
import { Layers, Target, RefreshCw, TrendingUp, Search, Plus, Trash2, AlertTriangle, Loader2, CheckCircle2, XCircle, Pin } from "lucide-react";

export default function UniversePage() {
  const [activeTab, setActiveTab] = useState("universe");
  
  // Data fetching
  const { data: universeData, isLoading: uniLoading } = useSWR("/api/v1/ticker-universe?status=active", fetcher);
  const { data: candidatesData, isLoading: candLoading } = useSWR("/api/v1/ticker-universe?status=candidate", fetcher);
  const { data: targetsData, isLoading: tgtLoading } = useSWR("/api/v1/ticker-universe/targets", fetcher);
  const { data: rebalancePlan, isLoading: planLoading } = useSWR("/api/v1/ticker-universe/rebalance/plan", fetcher);
  const { data: removalData } = useSWR("/api/v1/ticker-universe/removal-candidates", fetcher);

  const universe = universeData?.data || [];
  const candidates = candidatesData?.data || [];
  const targets = targetsData?.data || [];
  const plan = rebalancePlan?.data || {};
  const removals = removalData?.data?.candidates || [];
  const trades = plan?.trades?.all || [];

  const [isResearching, setIsResearching] = useState(false);
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [isExecutingRebalance, setIsExecutingRebalance] = useState(false);
  const [isPyramidScreening, setIsPyramidScreening] = useState(false);
  const [isEvolvingCandidates, setIsEvolvingCandidates] = useState(false);
  const [isEvolvingActive, setIsEvolvingActive] = useState(false);
  const [pyramidResult, setPyramidResult] = useState<any>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error', msg: string } | null>(null);

  // Build target map for display
  const targetMap: Record<string, any> = {};
  targets.forEach((t: any) => { targetMap[t.ticker] = t; });

  const handleRunPyramidScreen = async (autoAdmit: boolean = false) => {
    setIsPyramidScreening(true); setFeedback(null);
    try {
      const res = await api.post(`/api/v1/ticker-universe/pyramid-screen?top_n=12&auto_admit=${autoAdmit}`);
      const data = res.data;
      setPyramidResult(data.data);
      const admittedCount = data.data?.admitted_to_universe?.length || 0;
      setFeedback({
        type: "success",
        msg: `金字塔初篩完成！掃描 ${data.data?.stage1_total_scanned || 0} 檔，篩出 ${data.data?.stage1_candidates?.length || 0} 檔菁英，${data.data?.stage2_approved?.length || 0} 檔通過深層審查${autoAdmit ? `（已自動納入 ${admittedCount} 檔）` : ''}`
      });
      setActiveTab("pyramid");
      if (autoAdmit) mutate("/api/v1/ticker-universe?status=active");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    } finally { setIsPyramidScreening(false); }
  };

  const handleResearchAll = async () => {
    setIsResearching(true); setFeedback(null);
    try {
      const res = await api.post("/api/v1/ticker-universe/research/run");
      const data = res.data;
      setFeedback({ type: data.status === "success" ? "success" : "error", msg: data.message || data.detail });
      mutate("/api/v1/ticker-universe?status=active");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    } finally { setIsResearching(false); }
  };

  const handleOptimize = async () => {
    setIsOptimizing(true); setFeedback(null);
    try {
      const res = await api.get("/api/v1/ticker-universe/targets/optimize");
      const data = res.data;
      setFeedback({ type: data.status === "success" ? "success" : "error", msg: `優化完成：已收斂至 Top ${data.data?.length || 0} 檔核心標的` });
      mutate("/api/v1/ticker-universe/targets");
      mutate("/api/v1/ticker-universe/rebalance/plan");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    } finally { setIsOptimizing(false); }
  };

  const handleExecuteRebalance = async () => {
    if (!confirm("確定要執行主動資本輪動？系統將優先平倉淘汰標的釋放資金，並集中加碼至核心 Top 標的。")) return;
    setIsExecutingRebalance(true); setFeedback(null);
    try {
      const res = await api.post("/api/v1/ticker-universe/rebalance");
      const data = res.data;
      const count = data.data?.executed_trades?.length || 0;
      setFeedback({ type: data.status === "success" ? "success" : "error", msg: `資本輪動已完成！共執行 ${count} 筆調度下單。` });
      mutate("/api/v1/ticker-universe/targets");
      mutate("/api/v1/ticker-universe/rebalance/plan");
      mutate("/api/v1/ticker-universe?status=active");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    } finally { setIsExecutingRebalance(false); }
  };

  const handleAddTicker = async () => {
    const ticker = prompt("輸入標的代號 (如 AAPL)");
    if (!ticker) return;
    try {
      const res = await api.post("/api/v1/ticker-universe", { ticker: ticker.toUpperCase() });
      const data = res.data;
      setFeedback({ type: data.status === "success" ? "success" : "error", msg: data.message || data.detail });
      mutate("/api/v1/ticker-universe?status=active");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    }
  };

  const handleEvolveCandidates = async () => {
    setIsEvolvingCandidates(true); setFeedback(null);
    try {
      const res = await api.post("/api/v1/ticker-universe/candidates/evolve");
      const data = res.data;
      const count = data.data?.candidate_count || 0;
      const admitted = data.data?.admitted_new_count || 0;
      const pruned = data.data?.pruned_count || 0;
      setFeedback({
        type: "success",
        msg: `候選池演化完成！汰弱留強後保留 Top ${count} 檔（新增納入 ${admitted} 檔，淘汰 Pruned ${pruned} 檔）`
      });
      mutate("/api/v1/ticker-universe?status=candidate");
      mutate("/api/v1/ticker-universe?status=active");
      setActiveTab("candidates");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    } finally { setIsEvolvingCandidates(false); }
  };

  const handlePromoteCandidate = async (ticker: string) => {
    try {
      const res = await api.put(`/api/v1/ticker-universe/${ticker}`, { status: "active" });
      setFeedback({ type: "success", msg: `${ticker} 已成功晉升為活躍持倉標的！` });
      mutate("/api/v1/ticker-universe?status=candidate");
      mutate("/api/v1/ticker-universe?status=active");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    }
  };

  const handleRemoveCandidate = async (ticker: string) => {
    if (!confirm(`確定要將 ${ticker} 移出候選池？`)) return;
    try {
      await api.delete(`/api/v1/ticker-universe/${ticker}`);
      setFeedback({ type: "success", msg: `${ticker} 已移出候選池` });
      mutate("/api/v1/ticker-universe?status=candidate");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    }
  };

  const handleEvolveActive = async () => {
    setIsEvolvingActive(true); setFeedback(null);
    try {
      const res = await api.post("/api/v1/ticker-universe/active/evolve");
      const data = res.data;
      const count = data.data?.rotation_count || 0;
      const rotations = data.data?.rotations || [];
      const rotMsg = rotations.map((r: any) => `${r.demoted_ticker} (評分 ${r.demoted_score}) ➔ ${r.promoted_ticker} (評分 ${r.promoted_score})`).join("; ");
      setFeedback({
        type: "success",
        msg: count > 0 
          ? `活躍池汰弱留強完成！共輪替 ${count} 檔標的：${rotMsg}`
          : `活躍池審核完成：所有未鎖定活躍標的表現皆優於候選股利差門檻，無需輪替（已保護 ${data.data?.pinned_active_count || 0} 檔指定標的）`
      });
      mutate("/api/v1/ticker-universe?status=active");
      mutate("/api/v1/ticker-universe?status=candidate");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    } finally { setIsEvolvingActive(false); }
  };

  const handleTogglePin = async (ticker: string, currentPin: boolean) => {
    try {
      const nextPin = !currentPin;
      await api.put(`/api/v1/ticker-universe/${ticker}/pin`, { is_pinned: nextPin });
      setFeedback({
        type: "success",
        msg: nextPin 
          ? `📌 ${ticker} 已鎖定為指定標的（享有最高豁免保護，免疫自動汰弱留強/剔除）`
          : `⚡️ ${ticker} 已解除鎖定（恢復系統動態汰弱留強輪替）`
      });
      mutate("/api/v1/ticker-universe?status=active");
      mutate("/api/v1/ticker-universe?status=candidate");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    }
  };

  const handleRemoveActive = async (ticker: string) => {
    if (!confirm(`確定要將 ${ticker} 移出活躍標的池？`)) return;
    try {
      await api.delete(`/api/v1/ticker-universe/${ticker}`);
      setFeedback({ type: "success", msg: `${ticker} 已移出活躍池` });
      mutate("/api/v1/ticker-universe?status=active");
    } catch (e: any) {
      const errMsg = e.response?.data?.detail || e.response?.data?.message || e.message;
      setFeedback({ type: "error", msg: errMsg });
    }
  };

  return (
    <div className="flex-1 overflow-y-auto pt-16 sm:pt-20 lg:pt-24 px-4 sm:px-6 lg:px-8 pb-8">
      <div className="max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Layers className="w-6 h-6 text-blue-400" />
          <h1 className="text-2xl font-bold">標的池管理</h1>
        </div>
        <div className="flex gap-2">
          <button onClick={handleAddTicker} className="btn btn-sm btn-outline gap-2">
            <Plus className="w-4 h-4" /> 新增標的
          </button>
          <button onClick={handleEvolveCandidates} disabled={isEvolvingCandidates} className="btn btn-sm btn-accent gap-2">
            {isEvolvingCandidates ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            {isEvolvingCandidates ? "演化中..." : "候選池汰弱留強"}
          </button>
          <button onClick={() => handleRunPyramidScreen(false)} disabled={isPyramidScreening} className="btn btn-sm btn-outline gap-2">
            {isPyramidScreening ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
            {isPyramidScreening ? "初篩中..." : "金字塔初篩"}
          </button>
          <button onClick={handleResearchAll} disabled={isResearching} className="btn btn-sm btn-secondary gap-2">
            {isResearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
            {isResearching ? "研究中..." : "LLM 研究全部"}
          </button>
          <button onClick={handleOptimize} disabled={isOptimizing} className="btn btn-sm btn-primary gap-2">
            {isOptimizing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Target className="w-4 h-4" />}
            {isOptimizing ? "優化中..." : "優化配置"}
          </button>
        </div>
      </div>

      {/* Feedback */}
      {feedback && (
        <div className={cn("alert", feedback.type === "success" ? "alert-success" : "alert-error")}>
          {feedback.type === "success" ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
          <span>{feedback.msg}</span>
          <button onClick={() => setFeedback(null)} className="btn btn-xs">✕</button>
        </div>
      )}

      {/* Tabs */}
      <div className="tabs tabs-bordered">
        <button className={cn("tab", activeTab === "universe" && "tab-active")} onClick={() => setActiveTab("universe")}>
          <Layers className="w-4 h-4 mr-1" /> 活躍池 ({universe.length}/8)
        </button>
        <button className={cn("tab", activeTab === "candidates" && "tab-active")} onClick={() => setActiveTab("candidates")}>
          <Layers className="w-4 h-4 mr-1" /> 候選池 ({candidates.length}/30)
        </button>
        <button className={cn("tab", activeTab === "pyramid" && "tab-active")} onClick={() => setActiveTab("pyramid")}>
          <TrendingUp className="w-4 h-4 mr-1" /> 金字塔初篩 {pyramidResult && <span className="badge badge-accent ml-1">{pyramidResult.stage1_candidates?.length || 0}</span>}
        </button>
        <button className={cn("tab", activeTab === "targets" && "tab-active")} onClick={() => setActiveTab("targets")}>
          <Target className="w-4 h-4 mr-1" /> 目標配置
        </button>
        <button className={cn("tab", activeTab === "rebalance" && "tab-active")} onClick={() => setActiveTab("rebalance")}>
          <RefreshCw className="w-4 h-4 mr-1" /> 再平衡計劃
        </button>
        <button className={cn("tab", activeTab === "removals" && "tab-active")} onClick={() => setActiveTab("removals")}>
          <AlertTriangle className="w-4 h-4 mr-1" /> 剔除候選 {removals.length > 0 && <span className="badge badge-warning ml-1">{removals.length}</span>}
        </button>
      </div>

      {/* Tab: Universe (Active) */}
      {activeTab === "universe" && (
        <div className="space-y-4">
          <div className="bg-base-200/50 p-4 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 border border-base-300">
            <div>
              <h3 className="font-bold text-lg flex items-center gap-2">
                <Layers className="w-5 h-5 text-primary" /> 核心活躍標的池 (Active Core Universe)
              </h3>
              <p className="text-sm text-gray-400 mt-1">
                維持精選 8 檔核心活躍持倉。標記 📌「自選指定」之標的享有最高免疫保護，絕對不會被系統淘汰；未鎖定之標的將在審核或演化時與候選池頂尖強者動態「汰弱留強」競爭輪換。
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                onClick={handleEvolveActive}
                disabled={isEvolvingActive}
                className="btn btn-sm btn-primary gap-2"
                title="審查活躍池標的，並讓未鎖定之落後標的與候選池強者輪動"
              >
                {isEvolvingActive ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                活躍池汰弱留強
              </button>
              <button onClick={handleAddTicker} className="btn btn-sm btn-outline gap-1">
                <Plus className="w-4 h-4" /> 新增標的
              </button>
            </div>
          </div>

          <div className="overflow-x-auto">
            {uniLoading ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" /></div>
            ) : (
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>標的</th>
                    <th>指定保護 (📌)</th>
                    <th>公司名稱</th>
                    <th>板塊 / 產業</th>
                    <th>狀態</th>
                    <th>最新信心</th>
                    <th>目標權重</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {universe.map((t: any) => {
                    const target = targetMap[t.ticker];
                    const isPinned = !!t.is_pinned;
                    return (
                      <tr key={t.ticker} className="hover">
                        <td className="font-bold text-base">{t.ticker}</td>
                        <td>
                          <button
                            onClick={() => handleTogglePin(t.ticker, isPinned)}
                            className={cn(
                              "btn btn-xs gap-1 transition-all",
                              isPinned
                                ? "btn-primary shadow-sm"
                                : "btn-ghost text-gray-400 hover:text-white"
                            )}
                            title={isPinned ? "點擊解除指定保護（恢復系統動態輪動）" : "點擊鎖定為自選指定（享有最高免疫保護，絕不自動汰除）"}
                          >
                            <Pin className={cn("w-3.5 h-3.5", isPinned && "fill-current")} />
                            {isPinned ? "自選指定（免疫汰除）" : "系統輪動"}
                          </button>
                        </td>
                        <td className="text-sm text-gray-300">{t.company_name || "-"}</td>
                        <td className="text-sm">{t.sector || t.industry || "-"}</td>
                        <td><span className="badge badge-success badge-sm">{t.status}</span></td>
                        <td>{target ? `${(target.confidence_score * 100).toFixed(0)}%` : "-"}</td>
                        <td>{target ? `${(target.target_weight * 100).toFixed(1)}%` : "-"}</td>
                        <td>
                          <button
                            onClick={() => handleRemoveActive(t.ticker)}
                            className="btn btn-xs btn-ghost text-error"
                            title="移出活躍池"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Tab: Candidates */}
      {activeTab === "candidates" && (
        <div className="space-y-4">
          <div className="bg-base-200/50 p-4 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 border border-base-300">
            <div>
              <h3 className="font-bold text-lg flex items-center gap-2">
                <Layers className="w-5 h-5 text-accent" /> 動態儲備候選池 (Dynamic Candidate Reserve Pool)
              </h3>
              <p className="text-sm text-gray-400 mt-1">
                制度化擴充至 Top 30 檔儲備標的。標記 📌「指定儲備」之標的享有免疫淘汰保護；未鎖定之標的定期由系統「汰弱留強」收斂留存最強 30 檔。
              </p>
            </div>
            <button
              onClick={handleEvolveCandidates}
              disabled={isEvolvingCandidates}
              className="btn btn-sm btn-accent gap-2"
            >
              {isEvolvingCandidates ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              立即演化（汰弱留強）
            </button>
          </div>

          <div className="overflow-x-auto">
            {candLoading ? (
              <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" /></div>
            ) : candidates.length === 0 ? (
              <div className="text-center py-12 text-gray-500 bg-base-200/20 rounded-xl border border-dashed border-base-300">
                <Layers className="w-8 h-8 mx-auto mb-2 opacity-30" />
                <p>候選池目前暫無標的，請點擊上方「立即演化（汰弱留強）」自動補充儲備標的。</p>
              </div>
            ) : (
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>排名 / 代號</th>
                    <th>指定保護 (📌)</th>
                    <th>公司名稱</th>
                    <th>板塊 / 產業</th>
                    <th>狀態</th>
                    <th>入選日期</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map((c: any, idx: number) => {
                    const isPinned = !!c.is_pinned;
                    return (
                      <tr key={c.ticker} className="hover">
                        <td className="font-bold">
                          <span className="text-xs text-gray-400 mr-2">#{idx + 1}</span>
                          {c.ticker}
                        </td>
                        <td>
                          <button
                            onClick={() => handleTogglePin(c.ticker, isPinned)}
                            className={cn(
                              "btn btn-xs gap-1 transition-all",
                              isPinned
                                ? "btn-accent shadow-sm"
                                : "btn-ghost text-gray-400 hover:text-white"
                            )}
                            title={isPinned ? "點擊解除指定保護" : "點擊鎖定為指定儲備（免疫淘汰，維持於候選池）"}
                          >
                            <Pin className={cn("w-3.5 h-3.5", isPinned && "fill-current")} />
                            {isPinned ? "指定儲備（免疫淘汰）" : "動態儲備"}
                          </button>
                        </td>
                        <td className="text-sm text-gray-300">{c.company_name || "-"}</td>
                        <td className="text-sm">{c.sector || c.industry || "-"}</td>
                        <td><span className="badge badge-warning badge-sm">{c.status}</span></td>
                        <td className="text-xs text-gray-400">{c.added_at ? new Date(c.added_at).toLocaleDateString() : "-"}</td>
                        <td className="flex gap-2">
                          <button
                            onClick={() => handlePromoteCandidate(c.ticker)}
                            className="btn btn-xs btn-outline btn-success"
                            title="晉升至活躍池"
                          >
                            晉升
                          </button>
                          <button
                            onClick={() => handleRemoveCandidate(c.ticker)}
                            className="btn btn-xs btn-ghost text-error"
                            title="移出候選池"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {/* Tab: Pyramid Screener */}
      {activeTab === "pyramid" && (
        <div className="space-y-4">
          <div className="bg-base-200/50 p-4 rounded-xl flex flex-col sm:flex-row sm:items-center justify-between gap-4 border border-base-300">
            <div>
              <h3 className="font-bold text-lg flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-accent" /> 兩階段金字塔標的初篩器 (Two-Stage Pyramid Screener)
              </h3>
              <p className="text-sm text-gray-400 mt-1">
                第一階段：對 160+ 檔標的執行 0 成本 Python 純量化快速篩選（排除仙股、低量與破位股，收窄至 Top 12）<br />
                第二階段：對菁英候選進行多維度深度品質把關（基本面、財務比率、流動性硬指標）
              </p>
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => handleRunPyramidScreen(false)}
                disabled={isPyramidScreening}
                className="btn btn-sm btn-outline gap-2"
              >
                {isPyramidScreening ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                重新初篩
              </button>
              <button
                onClick={() => handleRunPyramidScreen(true)}
                disabled={isPyramidScreening || !pyramidResult?.stage2_approved?.length}
                className="btn btn-sm btn-accent gap-2"
              >
                <CheckCircle2 className="w-4 h-4" /> 一鍵納入標的池
              </button>
            </div>
          </div>

          {!pyramidResult ? (
            <div className="text-center py-16 text-gray-500 bg-base-200/20 rounded-xl border border-dashed border-base-300">
              <TrendingUp className="w-10 h-10 mx-auto mb-3 opacity-30" />
              <p className="text-base font-medium">尚未執行金字塔初篩</p>
              <p className="text-sm text-gray-400 mt-1 mb-4">點擊下方按鈕，對 160+ 檔美股核心流動性標的進行秒級量化篩選與深度審查</p>
              <button onClick={() => handleRunPyramidScreen(false)} disabled={isPyramidScreening} className="btn btn-sm btn-accent gap-2">
                {isPyramidScreening ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
                立即執行金字塔初篩
              </button>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>標的</th>
                    <th>價格</th>
                    <th>量化評分</th>
                    <th>趨勢狀態</th>
                    <th>RSI(14)</th>
                    <th>日均額 ($M)</th>
                    <th>深層品質審核</th>
                    <th>篩選說明</th>
                  </tr>
                </thead>
                <tbody>
                  {pyramidResult.stage1_candidates?.map((cand: any) => {
                    const approved = pyramidResult.stage2_approved?.find((a: any) => a.ticker === cand.ticker);
                    return (
                      <tr key={cand.ticker} className={approved ? "bg-accent/5" : ""}>
                        <td className="font-bold font-mono text-base">{cand.ticker}</td>
                        <td className="font-mono">${cand.price?.toFixed(2)}</td>
                        <td>
                          <span className="badge badge-accent font-bold">
                            {cand.quant_score?.toFixed(1)} / 10
                          </span>
                        </td>
                        <td>
                          {cand.trend_aligned ? (
                            <span className="badge badge-success badge-sm">多頭排列 (P&gt;50&gt;200)</span>
                          ) : cand.price >= cand.sma_50 ? (
                            <span className="badge badge-info badge-sm">突破季線 (P&gt;50)</span>
                          ) : (
                            <span className="badge badge-warning badge-sm">整理格局</span>
                          )}
                        </td>
                        <td className="font-mono">{cand.rsi?.toFixed(1)}</td>
                        <td className="font-mono">${cand.dollar_volume_m?.toFixed(1)}M</td>
                        <td>
                          {approved ? (
                            <span className="badge badge-success gap-1 text-xs">
                              <CheckCircle2 className="w-3 h-3" /> 通過 ({approved.overall_score?.toFixed(1)})
                            </span>
                          ) : (
                            <span className="badge badge-ghost text-xs text-gray-500">候選名單</span>
                          )}
                        </td>
                        <td className="text-xs text-gray-400 max-w-xs truncate" title={cand.reasons?.join("; ")}>
                          {cand.reasons?.join("; ")}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Tab: Targets */}
      {activeTab === "targets" && (
        <div className="overflow-x-auto">
          {tgtLoading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" /></div>
          ) : targets.length === 0 ? (
            <div className="text-center py-12 text-gray-500">尚無目標配置，請先執行「LLM 研究全部」→「優化配置」</div>
          ) : (
            <>
              <div className="mb-2 text-sm text-gray-400">總計: {(targets.reduce((s: number, t: any) => s + t.target_weight, 0) * 100).toFixed(1)}% (保留 5% 現金)</div>
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>標的</th>
                    <th>目標權重</th>
                    <th>信心指數</th>
                    <th>預期回報</th>
                    <th>配置占比</th>
                  </tr>
                </thead>
                <tbody>
                  {targets.sort((a: any, b: any) => b.target_weight - a.target_weight).map((t: any) => {
                    const pct = (t.target_weight * 100).toFixed(1);
                    return (
                      <tr key={t.ticker}>
                        <td className="font-bold">{t.ticker}</td>
                        <td><span className={cn("font-mono", parseFloat(pct) >= 8 ? "text-green-400" : "text-yellow-400")}>{pct}%</span></td>
                        <td>{(t.confidence_score * 100).toFixed(0)}%</td>
                        <td>{(t.expected_return * 100).toFixed(1)}%</td>
                        <td>
                          <div className="w-full bg-gray-700 rounded-full h-2.5">
                            <div className={cn("h-2.5 rounded-full", t.ticker === "NVDA" ? "bg-green-500" : "bg-blue-500")}
                                 style={{ width: pct + "%" }} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      {/* Tab: Rebalance Plan */}
      {activeTab === "rebalance" && (
        <div className="space-y-4">
          {planLoading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="w-6 h-6 animate-spin" /></div>
          ) : (
            <>
              {/* Action Bar */}
              <div className="flex items-center justify-between bg-base-200/50 p-4 rounded-xl border border-outline-variant/10">
                <div>
                  <h3 className="font-bold text-base flex items-center gap-2">
                    <RefreshCw className="w-4 h-4 text-primary" />
                    主動資本輪動與持倉集中化計劃
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    自動優先平倉非核心淘汰標的，釋出死資本全額集中配置於高置信度核心標的。
                  </p>
                </div>
                <button
                  onClick={handleExecuteRebalance}
                  disabled={isExecutingRebalance || trades.length === 0}
                  className="btn btn-sm btn-primary gap-2 shadow-lg shadow-primary/20"
                >
                  {isExecutingRebalance ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                  {isExecutingRebalance ? "調度執行中..." : "⚡ 執行主動資本輪動 (汰弱留強)"}
                </button>
              </div>

              {/* Pruning Alert Banner */}
              {plan.summary?.pruning_summary?.pruned_count > 0 && (
                <div className="alert bg-amber-500/10 border border-amber-500/20 text-amber-300 text-sm">
                  <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0" />
                  <div>
                    <span className="font-bold">資本置換清單：</span>
                    系統已識別出 <span className="font-mono font-bold text-white">{plan.summary.pruning_summary.pruned_count}</span> 筆死資本/淘汰部位（{plan.summary.pruning_summary.pruned_tickers.join(", ")}），執行輪動將主動清倉並釋出約 <span className="font-mono font-bold text-emerald-400">${plan.summary.pruning_summary.pruned_amount} USD</span> 現金，優先停泊至 Top 核心標的！
                  </div>
                </div>
              )}

              {/* Summary */}
              <div className="grid grid-cols-4 gap-4 mb-4">
                <div className="stat bg-base-200 rounded-lg p-4">
                  <div className="stat-title">組合價值</div>
                  <div className="stat-value text-lg">${plan.summary?.total_value.toFixed(0) || "-"}</div>
                </div>
                <div className="stat bg-base-200 rounded-lg p-4">
                  <div className="stat-title">需賣出 (含汰弱)</div>
                  <div className="stat-value text-lg text-red-400">${plan.summary?.total_sell_amount.toFixed(0) || "-"}</div>
                  <div className="stat-desc">{plan.summary?.sells || 0} 筆</div>
                </div>
                <div className="stat bg-base-200 rounded-lg p-4">
                  <div className="stat-title">需買入加碼</div>
                  <div className="stat-value text-lg text-green-400">${plan.summary?.total_buy_amount.toFixed(0) || "-"}</div>
                  <div className="stat-desc">{plan.summary?.buys || 0} 筆</div>
                </div>
                <div className="stat bg-base-200 rounded-lg p-4">
                  <div className="stat-title">可用現金</div>
                  <div className="stat-value text-lg">{plan.cash_weight?.toFixed(1) || "0"}%</div>
                  <div className="stat-desc">${plan.summary?.available_cash.toFixed(0) || "-"}</div>
                </div>
              </div>
              {/* Trades */}
              <table className="table w-full">
                <thead>
                  <tr>
                    <th>動作</th>
                    <th>標的</th>
                    <th>當前</th>
                    <th>→</th>
                    <th>目標</th>
                    <th>差額</th>
                    <th>金額</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t: any) => (
                    <tr key={t.ticker} className={t.action === "SELL" ? "bg-red-900/10" : "bg-green-900/10"}>
                      <td>
                        <span className={cn(
                          "badge",
                          t.action === "SELL"
                            ? (t.is_pruning || t.target_weight === 0 ? "badge-error badge-outline" : "badge-error")
                            : "badge-success"
                        )}>
                          {t.action === "SELL" ? (t.is_pruning || t.target_weight === 0 ? "汰弱清倉" : "減碼賣出") : "加碼買入"}
                        </span>
                      </td>
                      <td className="font-bold">{t.ticker}</td>
                      <td className="font-mono">{t.current_weight}%</td>
                      <td>→</td>
                      <td className="font-mono">{t.target_weight}%</td>
                      <td className={cn("font-mono", t.delta_weight > 0 ? "text-green-400" : "text-red-400")}>
                        {t.delta_weight > 0 ? "+" : ""}{t.delta_weight}%
                      </td>
                      <td className="font-mono">${Math.abs(t.delta_amount).toFixed(0)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {plan.summary?.cash_shortfall > 0 && (
                <div className="alert alert-warning mt-4">
                  <AlertTriangle className="w-4 h-4" />
                  <span>現金不足 ${plan.summary.cash_shortfall.toFixed(0)}，需新增賣出或減少買入</span>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {/* Tab: Removals */}
      {activeTab === "removals" && (
        <div>
          {removals.length === 0 ? (
            <div className="text-center py-12 text-gray-500">目前無建議剔除的標的</div>
          ) : (
            <table className="table w-full">
              <thead>
                <tr><th>標的</th><th>原因</th><th>信心</th><th>操作</th></tr>
              </thead>
              <tbody>
                {removals.map((c: any) => (
                  <tr key={c.ticker}>
                    <td className="font-bold">{c.ticker}</td>
                    <td className="text-sm text-gray-400">{c.reason}</td>
                    <td>{c.confidence ? `${(c.confidence*100).toFixed(0)}%` : "-"}</td>
                    <td><button className="btn btn-xs btn-error" onClick={() => {/* TODO */}}>剔除</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
      </div>
    </div>
  );
}