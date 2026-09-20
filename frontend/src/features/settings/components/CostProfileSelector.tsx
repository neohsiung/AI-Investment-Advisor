"use client";

import React, { useEffect, useState } from "react";
import { Zap, Shield, Sparkles, Check, Loader2, Clock, AlertTriangle } from "lucide-react";
import api from "@/lib/api";

interface CostProfile {
  id: string;
  name: string;
  description: string;
  estimated_weekly_cost: string;
  sentinel_tick_minute: string;
  sentinel_breaking_news_interval_min: number;
  sentinel_macro_interval_min: number;
  sentinel_deep_interval_min: number;
  recommended_providers: string[];
}

export function CostProfileSelector() {
  const [profiles, setProfiles] = useState<CostProfile[]>([]);
  const [activeProfile, setActiveProfile] = useState<string>("balanced");
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState<string | null>(null);
  const [needsOnboarding, setNeedsOnboarding] = useState(false);

  // Quick setup modal state
  const [showSetupModal, setShowSetupModal] = useState(false);
  const [providerCode, setProviderCode] = useState<"openrouter" | "ollama">("openrouter");
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("http://host.docker.internal:11434");
  const [submittingSetup, setSubmittingSetup] = useState(false);

  useEffect(() => {
    fetchStatus();
  }, []);

  async function fetchStatus() {
    try {
      setLoading(true);
      const [profilesRes, statusRes] = await Promise.all([
        api.get("/api/v1/settings/cost-profiles"),
        api.get("/api/v1/settings/onboarding-status"),
      ]);

      if (profilesRes.data?.profiles) {
        setProfiles(profilesRes.data.profiles);
        setActiveProfile(profilesRes.data.active_profile || "balanced");
      }
      if (statusRes.data) {
        setNeedsOnboarding(statusRes.data.needs_onboarding);
      }
    } catch (err) {
      console.error("Failed to load cost profiles or status:", err);
    } finally {
      setLoading(false);
    }
  }

  async function handleApplyProfile(profileId: string) {
    if (profileId === activeProfile) return;
    try {
      setSwitching(profileId);
      await api.post("/api/v1/settings/cost-profiles/apply", { profile: profileId });
      setActiveProfile(profileId);
    } catch (err: any) {
      alert(`切換方案失敗: ${err?.response?.data?.detail ?? err?.message}`);
    } finally {
      setSwitching(null);
    }
  }

  async function handleCompleteSetup(e: React.FormEvent) {
    e.preventDefault();
    try {
      setSubmittingSetup(true);
      await api.post("/api/v1/settings/onboarding/complete", {
        cost_profile: activeProfile,
        provider_code: providerCode,
        api_key: providerCode === "openrouter" ? apiKey : undefined,
        base_url: providerCode === "ollama" ? baseUrl : undefined,
      });
      setShowSetupModal(false);
      setNeedsOnboarding(false);
      alert("開箱設定完成！AI 提供商已成功配置。");
    } catch (err: any) {
      alert(`設定失敗: ${err?.response?.data?.detail ?? err?.message}`);
    } finally {
      setSubmittingSetup(false);
    }
  }

  const getProfileIcon = (id: string) => {
    switch (id) {
      case "frugal":
        return <Shield className="h-5 w-5 text-emerald-400" />;
      case "aggressive":
        return <Zap className="h-5 w-5 text-amber-400" />;
      default:
        return <Sparkles className="h-5 w-5 text-primary" />;
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-xs text-on-surface-variant p-4">
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
        載入成本方案中...
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Onboarding Banner if no LLM configured */}
      {needsOnboarding && (
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 text-on-surface">
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="h-5 w-5 text-amber-400 shrink-0" />
            <div>
              <h3 className="text-sm font-bold">尚未配置主要 AI 模型提供商 (LLM Provider)</h3>
              <p className="text-xs text-on-surface-variant">
                哨兵巡邏與分析團隊需要 AI 模型支援。您可以一鍵配置 OpenRouter 或本機 Ollama。
              </p>
            </div>
          </div>
          <button
            onClick={() => setShowSetupModal(true)}
            className="px-3.5 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-600 text-black text-xs font-bold shrink-0 transition-colors shadow-sm"
          >
            快速配置 LLM
          </button>
        </div>
      )}

      {/* Profiles Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {profiles.map((p) => {
          const isActive = p.id === activeProfile;
          const isBusy = switching === p.id;

          return (
            <div
              key={p.id}
              onClick={() => !switching && handleApplyProfile(p.id)}
              className={`relative flex flex-col justify-between p-4 rounded-xl border transition-all cursor-pointer ${
                isActive
                  ? "bg-primary/5 border-primary/40 shadow-sm ring-1 ring-primary/30"
                  : "bg-surface-container border-outline-variant/20 hover:border-outline-variant/50 hover:bg-surface-container-high"
              }`}
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-2">
                  <div className="flex items-center gap-2">
                    {getProfileIcon(p.id)}
                    <h3 className="text-sm font-bold text-on-surface">{p.name}</h3>
                  </div>
                  {isActive && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-primary/20 text-primary text-[10px] font-bold">
                      <Check className="h-3 w-3" /> 使用中
                    </span>
                  )}
                </div>

                <p className="text-xs text-on-surface-variant line-clamp-3 mb-3 leading-relaxed">
                  {p.description}
                </p>
              </div>

              <div className="space-y-2 pt-3 border-t border-outline-variant/10 text-xs">
                <div className="flex items-center justify-between text-on-surface-variant">
                  <span className="flex items-center gap-1">
                    <Clock className="h-3.5 w-3.5" /> 哨兵巡邏週期:
                  </span>
                  <span className="font-semibold text-on-surface">{p.sentinel_tick_minute}</span>
                </div>
                <div className="flex items-center justify-between text-on-surface-variant">
                  <span>預估週花費:</span>
                  <span className="font-bold text-primary">{p.estimated_weekly_cost}</span>
                </div>

                <button
                  type="button"
                  disabled={isActive || switching !== null}
                  className={`w-full mt-2 py-1.5 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors ${
                    isActive
                      ? "bg-transparent text-on-surface-variant/40 cursor-default"
                      : "bg-surface-container-highest hover:bg-primary hover:text-black text-on-surface border border-outline-variant/20"
                  }`}
                >
                  {isBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  {isActive ? "目前運作中" : "套用此方案"}
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Quick Setup Modal */}
      {showSetupModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 animate-in fade-in">
          <div className="w-full max-w-md bg-surface-container-high border border-outline-variant/30 rounded-2xl p-6 shadow-xl space-y-5">
            <div>
              <h2 className="text-base font-bold text-on-surface">主要 AI 模型提供商配置</h2>
              <p className="text-xs text-on-surface-variant mt-1">
                選擇您的 AI 引擎端點。此設定將即時加密儲存於資料庫中。
              </p>
            </div>

            <form onSubmit={handleCompleteSetup} className="space-y-4">
              <div className="space-y-2">
                <label className="text-xs font-medium text-on-surface">提供商類型</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setProviderCode("openrouter")}
                    className={`py-2 px-3 rounded-xl text-xs font-bold border transition-colors ${
                      providerCode === "openrouter"
                        ? "bg-primary/20 border-primary text-primary"
                        : "bg-surface-container border-outline-variant/20 text-on-surface hover:bg-surface-container-highest"
                    }`}
                  >
                    OpenRouter (推薦)
                  </button>
                  <button
                    type="button"
                    onClick={() => setProviderCode("ollama")}
                    className={`py-2 px-3 rounded-xl text-xs font-bold border transition-colors ${
                      providerCode === "ollama"
                        ? "bg-primary/20 border-primary text-primary"
                        : "bg-surface-container border-outline-variant/20 text-on-surface hover:bg-surface-container-highest"
                    }`}
                  >
                    Ollama (本機 $0)
                  </button>
                </div>
              </div>

              {providerCode === "openrouter" ? (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-on-surface">
                    OpenRouter API Key
                  </label>
                  <input
                    type="password"
                    placeholder="sk-or-v1-..."
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant/30 text-xs text-on-surface focus:outline-none focus:border-primary"
                  />
                  <p className="text-[11px] text-on-surface-variant">
                    支援單一金鑰存取 Claude、GPT-4o、Llama 3.3 等所有模型。
                  </p>
                </div>
              ) : (
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-on-surface">
                    Ollama Base URL
                  </label>
                  <input
                    type="text"
                    placeholder="http://host.docker.internal:11434"
                    value={baseUrl}
                    onChange={(e) => setBaseUrl(e.target.value)}
                    required
                    className="w-full px-3 py-2 rounded-lg bg-surface-container border border-outline-variant/30 text-xs text-on-surface focus:outline-none focus:border-primary"
                  />
                  <p className="text-[11px] text-on-surface-variant">
                    若於 Docker 內部執行，請使用 host.docker.internal:11434。
                  </p>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowSetupModal(false)}
                  className="px-3.5 py-1.5 rounded-lg border border-outline-variant/20 text-xs text-on-surface hover:bg-surface-variant"
                >
                  取消
                </button>
                <button
                  type="submit"
                  disabled={submittingSetup}
                  className="px-4 py-1.5 rounded-lg bg-primary hover:bg-primary/90 text-black text-xs font-bold flex items-center gap-1.5 disabled:opacity-50"
                >
                  {submittingSetup && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                  完成配置
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
