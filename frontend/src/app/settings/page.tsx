"use client";

import React, { useState, useEffect } from "react";
import useSWR, { mutate } from "swr";
import axios from "axios";
import { fetcher } from "@/lib/api";
import { 
  Settings, Save, Cpu, ShieldCheck, Bell, Database, 
  Building2, Settings2, Loader2, CheckCircle2, AlertCircle,
  Eye, EyeOff, Key, Link, ExternalLink, Brain, Zap, Mail,
  Shield, TrendingUp, History, Globe, Lock, Code, Server,
  ShieldAlert, MessageSquare, Send, Smartphone
} from "lucide-react";
import { cn, formatCurrency } from "@/lib/utils";

// --- Tab Definitions ---
const TABS = [
  { id: "ai",       label: "AI 引擎",     icon: Brain,        desc: "模型參數與 Provider" },
  { id: "trading",  label: "交易風控",    icon: ShieldCheck,  desc: "自動執行與停損邏輯" },
  { id: "notify",   label: "通知渠道",    icon: Bell,         desc: "Telegram, LINE & Email" },
  { id: "sources",  label: "數據源",      icon: Database,     desc: "API 金鑰與來源管理" },
  { id: "broker",   label: "Broker 整合", icon: Building2,    desc: "eToro, IBKR & Futu" },
  { id: "system",   label: "排程 & 系統", icon: Settings2,    desc: "執行頻率與系統時區" },
];

export default function SettingsPage() {
  const { data: settingsData, isLoading: settingsLoading } = useSWR("/api/dashboard/settings", fetcher);
  
  const [activeTab, setActiveTab] = useState("ai");
  const [localSettings, setLocalSettings] = useState<Record<string, any>>({});
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error', msg: string } | null>(null);
  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({});

  useEffect(() => {
    if (settingsData?.data) {
      setLocalSettings(settingsData.data);
    }
  }, [settingsData]);

  const handleSave = async () => {
    setIsSaving(true);
    setFeedback(null);
    try {
      await axios.post("/api/dashboard/settings", localSettings);
      setFeedback({ type: 'success', msg: "設定已成功儲存並生效" });
      mutate("/api/dashboard/settings");
    } catch (err: any) {
      setFeedback({ type: 'error', msg: err.response?.data?.detail || "儲存失敗" });
    } finally {
      setIsSaving(false);
      // Auto-clear success message
      setTimeout(() => setFeedback(null), 5000);
    }
  };

  const updateSetting = (key: string, value: any) => {
    setLocalSettings(prev => ({ ...prev, [key]: value }));
  };

  const toggleSecret = (key: string) => {
    setShowSecrets(prev => ({ ...prev, [key]: !prev[key] }));
  };

  if (settingsLoading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4 opacity-50">
          <Loader2 className="animate-spin text-primary" size={32} />
          <p className="text-[10px] font-black uppercase tracking-[0.2em]">正在同步全域設定雲...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col bg-background pt-24 p-8 overflow-hidden h-full">
      <div className="max-w-7xl mx-auto w-full flex flex-col h-full">
        {/* Header Section */}
        <div className="flex justify-between items-end mb-8 flex-shrink-0">
          <div>
            <div className="flex items-center gap-2 mb-2">
              <div className="p-1.5 bg-primary/10 rounded-lg text-primary">
                <Settings size={20} />
              </div>
              <h1 className="text-4xl font-bold font-headline tracking-tighter">系統控制中心</h1>
            </div>
            <p className="text-on-surface-variant font-label text-xs uppercase tracking-[0.3em]">
              配置 AI 模型集群、多維度數據源與全球 Broker 接口
            </p>
          </div>
          
          <div className="flex items-center gap-6">
            {feedback && (
              <div className={cn(
                "animate-in fade-in slide-in-from-right-4 px-4 py-2 rounded-xl border flex items-center gap-2 text-xs font-bold",
                feedback.type === 'success' ? "bg-secondary/10 border-secondary/20 text-secondary" : "bg-error/10 border-error/20 text-error"
              )}>
                {feedback.type === 'success' ? <CheckCircle2 size={14} /> : <AlertCircle size={14} />}
                {feedback.msg}
              </div>
            )}
            <button 
              onClick={handleSave}
              disabled={isSaving}
              className="group flex items-center gap-2 px-8 py-3 bg-primary text-on-primary rounded-xl font-bold translate-y-0 hover:-translate-y-0.5 active:translate-y-0 shadow-lg shadow-primary/20 hover:shadow-xl transition-all disabled:opacity-50"
            >
              {isSaving ? <Loader2 className="animate-spin" size={18} /> : <Save size={18} className="group-hover:rotate-12 transition-transform" />}
              儲存全域變更
            </button>
          </div>
        </div>

        {/* Main Interface Layout */}
        <div className="flex gap-8 flex-1 overflow-hidden">
          {/* Left Sidebar Navigation */}
          <div className="w-64 flex flex-col gap-2 flex-shrink-0">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = activeTab === tab.id;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex flex-col items-start p-4 rounded-2xl transition-all text-left group",
                    isActive 
                      ? "bg-surface-container-high shadow-sm border border-outline-variant/10 ring-1 ring-primary/20" 
                      : "hover:bg-surface-container-low opacity-60 hover:opacity-100"
                  )}
                >
                  <div className="flex items-center gap-3 mb-1">
                    <div className={cn(
                      "p-2 rounded-xl transition-colors",
                      isActive ? "bg-primary text-on-primary" : "bg-surface-variant group-hover:bg-surface-container-high"
                    )}>
                      <Icon size={18} />
                    </div>
                    <span className={cn("font-bold text-sm", isActive ? "text-on-surface" : "text-on-surface-variant")}>
                      {tab.label}
                    </span>
                  </div>
                  <p className="text-[10px] font-medium text-on-surface-variant/70 pl-11">
                    {tab.desc}
                  </p>
                </button>
              );
            })}
            
            <div className="mt-auto p-6 bg-surface-container-lowest/50 rounded-2xl border border-dashed border-outline-variant/20 italic">
               <p className="text-[10px] text-on-surface-variant/40 leading-relaxed">
                 所有變更將即時同步至多代理人集群 (Sovereign Swarm)。請謹慎調整風控參數。
               </p>
               <div className="mt-4 text-[9px] opacity-50">
                - `[x]` Phase B — Settings 完整化 (6 Tab 重構)
    - `[x]` B-1: 建立 Tab 導航基礎架構與主佈局
    - `[x]` B-2: 實作 「AI 引擎」 與 「交易風控」 面板
    - `[x]` B-3: 實作 「通知渠道」 與 「數據源」 面板
    - `[x]` B-4: 實作 「Broker 整合」 與 「排程系統」 面板
    - `[/]` B-5: 儲存與測試通知邏輯整合
               </div>
            </div>
          </div>

          {/* Right Content Area */}
          <div className="flex-1 bg-surface-container-low rounded-[32px] border border-outline-variant/10 shadow-sm overflow-hidden flex flex-col">
            <div className="flex-1 overflow-y-auto p-12 custom-scrollbar">
               {/* Tab content will be rendered here */}
               <div className="animate-in fade-in slide-in-from-bottom-4 duration-500">
                  {renderTabContent(activeTab, localSettings, updateSetting, toggleSecret, showSecrets)}
               </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// --- Tab Rendering Logic ---
function renderTabContent(tabId: string, settings: any, update: any, toggle: any, secrets: any) {
    switch (tabId) {
      case "ai":      return <AIEnginePanel settings={settings} update={update} toggle={toggle} secrets={secrets} />;
      case "trading": return <TradingRiskPanel settings={settings} update={update} />;
      case "notify":  return <NotifyPanel settings={settings} update={update} toggle={toggle} secrets={secrets} />;
      case "sources": return <SourcesPanel settings={settings} update={update} toggle={toggle} secrets={secrets} />;
      case "broker":  return <BrokerPanel settings={settings} update={update} toggle={toggle} secrets={secrets} />;
      case "system":  return <SystemPanel settings={settings} update={update} />;
      default:        return <div>Tab not found</div>;
    }
}

// --- Tab Panels ---

function AIEnginePanel({ settings, update, toggle, secrets }: any) {
  return (
    <div className="space-y-12">
      <SectionHead title="AI 核心引擎配置" desc="多層級代理人集群模型分發設定。各角色根據複雜度對應不同算力等級。" />
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Model Tiers - Row 1 */}
        <SettingCard title="Primary Model (總裁級)" icon={<Cpu size={20} />} desc="用於 CIO 核心戰略、每日摘要與長期投資決策。">
          <LabeledInput 
            label="核心 LLM 模型"
            value={settings.AI_MODEL || ""}
            onChange={(v: string) => update("AI_MODEL", v)}
            placeholder="e.g. google/gemini-2.5-pro"
          />
        </SettingCard>

        <SettingCard title="Advanced Model (專家級)" icon={<Brain size={20} />} desc="用於生成深度分析報告與多維度風險掃描。">
          <LabeledInput 
            label="深度分析模型"
            value={settings.AI_MODEL_ADVANCED || ""}
            onChange={(v: string) => update("AI_MODEL_ADVANCED", v)}
            placeholder="e.g. google/gemini-3.1-pro-preview"
          />
        </SettingCard>

        {/* Model Tiers - Row 2 */}
        <SettingCard title="Smart Model (經理級)" icon={<Zap size={20} />} desc="用於執行具體持倉分析與細微策略調整建議。">
          <LabeledInput 
            label="持倉分析模型"
            value={settings.AI_MODEL_SMART || ""}
            onChange={(v: string) => update("AI_MODEL_SMART", v)}
            placeholder="e.g. google/gemini-2.5-pro"
          />
        </SettingCard>

        <SettingCard title="Fast Model (助理級)" icon={<Loader2 size={20} />} desc="用於 24/7 市場警報識別、即時問答與基礎過濾。">
          <LabeledInput 
            label="快速推論模型"
            value={settings.AI_MODEL_FAST || ""}
            onChange={(v: string) => update("AI_MODEL_FAST", v)}
            placeholder="e.g. gemini-2.0-flash"
          />
        </SettingCard>
      </div>

      <SectionHead title="Provider & API 接口" desc="設定算力供應商及其授權密鑰。" />
      <div className="p-8 bg-surface-container rounded-3xl border border-outline-variant/10 space-y-6">
        <div className="grid grid-cols-2 gap-8">
           <div>
             <label className="block text-[10px] font-black uppercase text-on-surface-variant mb-3 tracking-widest">
               LLM 供應商 (Provider)
             </label>
             <select 
               value={settings.AI_PROVIDER || "OpenRouter"}
               onChange={(e: React.ChangeEvent<HTMLSelectElement>) => update("AI_PROVIDER", e.target.value)}
               className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm focus:border-primary/50 transition-all outline-none"
             >
               <option value="OpenRouter">OpenRouter (多模型接入)</option>
               <option value="Groq">Groq (高速推理)</option>
               <option value="Google">Google Gemini (原生)</option>
               <option value="OpenAI">OpenAI (GPT 集群)</option>
             </select>
           </div>
           
           <SecretInput 
             label="供應商 API Key"
             value={settings.API_KEY || ""}
             id="API_KEY"
             toggle={toggle}
             show={secrets.API_KEY}
             onChange={(v: string) => update("API_KEY", v)}
           />
        </div>
        <div>
           <LabeledInput 
             label="API 端點 (Base URL)"
             value={settings.BASE_URL || ""}
             onChange={(v: string) => update("BASE_URL", v)}
             placeholder="https://openrouter.ai/api/v1"
           />
        </div>
      </div>
    </div>
  );
}

function TradingRiskPanel({ settings, update }: any) {
  return (
    <div className="space-y-12">
      <SectionHead title="全自動執行風控" desc="調整 AI 代理人自動化動作的信賴閾值與極端情況下的連鎖熔斷機制。" />
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <SettingCard title="自動執行信心閾值 (1-10)" icon={<Shield size={20} />} desc="數值越高越謹慎。建議值為 7-8，代表 AI 需具備高度把握才會自動下單。">
          <input 
            type="range" min="1" max="100" step="1"
            value={settings.auto_trade_threshold || 75}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => update("auto_trade_threshold", parseInt(e.target.value))}
            className="w-full accent-primary mt-4"
          />
          <div className="flex justify-between mt-2 text-[10px] font-black text-primary">
            <span>小心 (1)</span>
            <span className="text-xl">{settings.auto_trade_threshold || 75} / 100</span>
            <span>極度穩健 (100)</span>
          </div>
        </SettingCard>

        <SettingCard title="最低參與信心 (1-10)" icon={<TrendingUp size={20} />} desc="低於此信心分值的建議將會被系統自動過濾，不顯示在前端介面。">
           <input 
            type="range" min="1" max="100" step="1"
            value={settings.auto_trade_min_threshold || 30}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => update("auto_trade_min_threshold", parseInt(e.target.value))}
            className="w-full accent-secondary mt-4"
          />
          <div className="flex justify-between mt-2 text-[10px] font-black text-secondary">
            <span>寬鬆 (1)</span>
            <span className="text-xl">{settings.auto_trade_min_threshold || 30} / 100</span>
            <span>嚴格 (100)</span>
          </div>
        </SettingCard>

        <SettingCard title="緊急熔斷與對沖" icon={<ShieldAlert size={20} />} desc="異常行情觸發的系統應對措施。">
          <div className="space-y-6 mt-4">
            <div className="flex justify-between items-center bg-surface-container-high p-4 rounded-xl">
               <span className="text-xs font-bold">自動對沖分數 (Hedge Score)</span>
               <div className="flex items-center gap-4">
                 <input 
                  type="number" className="w-16 bg-surface p-2 rounded text-center font-mono text-sm"
                  value={settings.auto_hedge_score || 8}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => update("auto_hedge_score", parseInt(e.target.value))}
                 />
                 <span className="text-[10px] font-black opacity-30">/ 10</span>
               </div>
            </div>
            <div className="flex justify-between items-center bg-error/5 p-4 rounded-xl border border-error/10">
               <span className="text-xs font-bold text-error">緊急清倉分數 (Liquidate Score)</span>
               <input 
                  type="number" className="w-16 bg-surface p-2 rounded text-center font-mono text-sm border border-error/20"
                  value={settings.emergency_liquidation_score || 9}
                  onChange={(e: React.ChangeEvent<HTMLInputElement>) => update("emergency_liquidation_score", parseInt(e.target.value))}
               />
            </div>
          </div>
        </SettingCard>

        <SettingCard title="資產比例與曝險控管" icon={<Database size={20} />} desc="限制單一持有與目標現金比例。">
           <div className="space-y-4 mt-2">
             <LabeledInput label="目標現金比例 (Target Cash Ratio)" value={settings.target_cash_ratio || 0.2} onChange={(v: string) => update("target_cash_ratio", parseFloat(v))} />
             <LabeledInput label="單一板塊曝險上限 (Sector Limit)" value={settings.risk_max_sector_exposure || 0.35} onChange={(v: string) => update("risk_max_sector_exposure", parseFloat(v))} />
             <div className="flex justify-between items-center px-2">
                <span className="text-[10px] font-bold text-on-surface-variant uppercase tracking-widest">風險偏好級別</span>
                <select 
                  value={settings.risk_profile || "Aggressive"}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => update("risk_profile", e.target.value)}
                  className="bg-transparent font-bold text-primary outline-none"
                >
                  <option value="Conservative">保守 (Conservative)</option>
                  <option value="Moderate">適中 (Moderate)</option>
                  <option value="Aggressive">積極 (Aggressive)</option>
                </select>
             </div>
           </div>
        </SettingCard>
      </div>
    </div>
  );
}

function NotifyPanel({ settings, update, toggle, secrets }: any) {
  const [isTesting, setIsTesting] = useState<string | null>(null);

  const handleTest = async (channel: string) => {
    setIsTesting(channel);
    try {
      await axios.post("/api/dashboard/settings/test-notification", { channels: [channel] });
      alert(`${channel.toUpperCase()} 測試通知已發送，請檢查您的裝置。`);
    } catch (err: any) {
      alert(`測試失敗: ${err.response?.data?.detail || err.message}`);
    } finally {
      setIsTesting(null);
    }
  };

  return (
    <div className="space-y-12">
      <SectionHead title="多渠道通知設定" desc="配置系統警報、交易執行與週報的發送管道。" />

      <div className="grid grid-cols-1 gap-8">
        {/* Telegram */}
        <div className="bg-surface-container p-8 rounded-[32px] border border-outline-variant/5">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#0088cc]/10 rounded-2xl text-[#0088cc]">
                <Send size={20} />
              </div>
              <div>
                <h3 className="font-bold text-lg tracking-tight">Telegram Bot</h3>
                <p className="text-[10px] uppercase font-black text-on-surface-variant tracking-widest mt-1">即時推送 & 指令互動</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
               <button 
                onClick={() => handleTest('telegram')}
                disabled={isTesting === 'telegram'}
                className="px-4 py-2 border border-outline-variant/30 rounded-lg text-[10px] font-black uppercase hover:bg-surface-variant transition-all disabled:opacity-50"
               >
                 {isTesting === 'telegram' ? "發送中..." : "發送測試"}
               </button>
               <Switch 
                checked={settings.channel_telegram_enabled} 
                onChange={(v: boolean) => update("channel_telegram_enabled", v)} 
               />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-6 mb-6">
             <SecretInput label="Bot Token" id="tg_token" value={settings.channel_telegram_bot_token || ""} toggle={toggle} show={secrets.tg_token} onChange={(v: string) => update("channel_telegram_bot_token", v)} />
             <LabeledInput label="Chat ID" value={settings.channel_telegram_chat_id || ""} onChange={(v: string) => update("channel_telegram_chat_id", v)} />
          </div>
          <InterestSelector 
            label="通知內容偏好 (Interests)"
            value={settings.channel_telegram_interests || ""}
            onChange={(v: string) => update("channel_telegram_interests", v)}
          />
        </div>

        {/* LINE Notify */}
        <div className="bg-surface-container p-8 rounded-[32px] border border-outline-variant/5">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#00c300]/10 rounded-2xl text-[#00c300]">
                <Smartphone size={20} />
              </div>
              <div>
                <h3 className="font-bold text-lg tracking-tight">LINE Notify / Messaging</h3>
                <p className="text-[10px] uppercase font-black text-on-surface-variant tracking-widest mt-1">台灣市場主流通知工具</p>
              </div>
            </div>
            <div className="flex items-center gap-4">
               <button 
                onClick={() => handleTest('line')}
                disabled={isTesting === 'line'}
                className="px-4 py-2 border border-outline-variant/30 rounded-lg text-[10px] font-black uppercase hover:bg-surface-variant transition-all disabled:opacity-50"
               >
                 {isTesting === 'line' ? "發送中..." : "發送測試"}
               </button>
               <Switch 
                checked={settings.channel_line_enabled} 
                onChange={(v: boolean) => update("channel_line_enabled", v)} 
               />
            </div>
          </div>
          <div className="grid grid-cols-3 gap-6 mb-6">
             <SecretInput label="Access Token" id="line_token" value={settings.channel_line_access_token || ""} toggle={toggle} show={secrets.line_token} onChange={(v: string) => update("channel_line_access_token", v)} />
             <SecretInput label="Channel Secret" id="line_sec" value={settings.channel_line_secret || ""} toggle={toggle} show={secrets.line_sec} onChange={(v: string) => update("channel_line_secret", v)} />
             <LabeledInput label="User ID (推播對象)" value={settings.channel_line_user_id || ""} onChange={(v: string) => update("channel_line_user_id", v)} />
          </div>
          <InterestSelector 
            label="通知內容偏好 (Interests)"
            value={settings.channel_line_interests || ""}
            onChange={(v: string) => update("channel_line_interests", v)}
          />
        </div>

        {/* Email SMTP */}
        <div className="bg-surface-container p-8 rounded-[32px] border border-outline-variant/5">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-primary/10 rounded-2xl text-primary">
                <Mail size={20} />
              </div>
              <div>
                <h3 className="font-bold text-lg tracking-tight">Email SMTP</h3>
                <p className="text-[10px] uppercase font-black text-on-surface-variant tracking-widest mt-1">正式投資週報與報告外寄</p>
              </div>
            </div>
            <Switch 
              checked={settings.channel_email_enabled} 
              onChange={(v: boolean) => update("channel_email_enabled", v)} 
            />
          </div>
          <div className="grid grid-cols-4 gap-6 mb-6">
             <div className="col-span-2">
               <LabeledInput label="SMTP Server" value={settings.channel_email_smtp_server || ""} onChange={(v: string) => update("channel_email_smtp_server", v)} placeholder="smtp.gmail.com" />
             </div>
             <LabeledInput label="Port" value={settings.channel_email_smtp_port || 587} onChange={(v: string) => update("channel_email_smtp_port", v)} />
             <LabeledInput label="From Address" value={settings.channel_email_from_address || ""} onChange={(v: string) => update("channel_email_from_address", v)} />
             <div className="col-span-2">
               <LabeledInput label="SMTP User" value={settings.channel_email_smtp_user || ""} onChange={(v: string) => update("channel_email_smtp_user", v)} />
             </div>
             <div className="col-span-2">
               <SecretInput label="SMTP Password" id="smtp_pass" value={settings.channel_email_smtp_pass || ""} toggle={toggle} show={secrets.smtp_pass} onChange={(v: string) => update("channel_email_smtp_pass", v)} />
             </div>
          </div>
          <InterestSelector 
            label="通知內容偏好 (Interests)"
            value={settings.channel_email_interests || ""}
            onChange={(v: string) => update("channel_email_interests", v)}
          />
        </div>
      </div>
    </div>
  );
}

function SourcesPanel({ settings, update, toggle, secrets }: any) {
  const sources = [
    { id: "alpha_vantage", label: "Alpha Vantage", desc: "基礎面與歷史股價", hasKey: true },
    { id: "tiingo",        label: "Tiingo",        desc: "即時美股 & ETF", hasKey: true },
    { id: "polygon",       label: "Polygon.io",    desc: "WebSocket 即時流", hasKey: true },
    { id: "fmp",           label: "Financial Modeling Prep", desc: "財報與估值指標", hasKey: true },
    { id: "fred",          label: "FRED (Fed Resource)", desc: "週轉率與總經數據", hasKey: true },
    { id: "finnhub",       label: "Finnhub",       desc: "新聞情緒與 Webhooks", hasKey: true },
    { id: "tavily",        label: "Tavily (AI Search)", desc: "AI 即時網路檢索", hasKey: true },
    { id: "financialdata", label: "FinancialData.ai", desc: "高級聚合數據", hasKey: true },
  ];

  const webhooks = [
    { id: "finnhub", label: "Finnhub Webhook" },
    { id: "polygon", label: "Polygon Webhook" },
    { id: "tradingview", label: "TradingView Signal" },
    { id: "zapier_sec", label: "Zapier Security" },
  ];

  return (
    <div className="space-y-12">
      <SectionHead title="外部數據源管理" desc="整合全球市場行情、新聞情緒與總體經濟數據接口。" />

      <div className="grid grid-cols-2 gap-6">
        {sources.map(src => (
          <div key={src.id} className="bg-surface-container p-6 rounded-[24px] border border-outline-variant/10">
            <div className="flex justify-between items-start mb-4">
              <div>
                <h4 className="font-bold text-sm">{src.label}</h4>
                <p className="text-[10px] text-on-surface-variant mt-1">{src.desc}</p>
              </div>
              <Switch 
                checked={settings[`source_${src.id}_enabled`]} 
                onChange={(v: boolean) => update(`source_${src.id}_enabled`, v)} 
              />
            </div>
            {src.hasKey && (
              <SecretInput 
                label="API Key" 
                id={`sk_${src.id}`} 
                value={settings[`source_${src.id}_api_key`] || ""} 
                toggle={toggle} 
                show={secrets[`sk_${src.id}`]} 
                onChange={(v: string) => update(`source_${src.id}_api_key`, v)} 
              />
            )}
          </div>
        ))}
      </div>

      <SectionHead title="Webhook 實時監聽器" desc="接收來自外部交易訊號或市場突發新聞的推送。" />
      <div className="bg-surface-container p-8 rounded-[32px] border border-outline-variant/5">
         <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            {webhooks.map(wh => (
              <div key={wh.id} className="bg-background/50 p-4 rounded-2xl flex flex-col items-center gap-3">
                 <span className="text-[10px] font-black uppercase text-on-surface-variant">{wh.label}</span>
                 <Switch 
                    checked={settings[`source_webhook_${wh.id}_enabled`]} 
                    onChange={(v: boolean) => update(`source_webhook_${wh.id}_enabled`, v)} 
                 />
              </div>
            ))}
         </div>
         <div className="mt-8 pt-8 border-t border-outline-variant/10">
            <LabeledInput 
              label="系統授權 Webhook API Key (由本系統提供給外部)" 
              value={settings.webhook_api_key || ""} 
              disabled 
              placeholder="自動生成中..."
            />
         </div>
      </div>
    </div>
  );
}
function BrokerPanel({ settings, update, toggle, secrets }: any) {
  return (
    <div className="space-y-12">
      <SectionHead title="券商與交易接口 (Broker Integration)" desc="連接您的真實交易帳戶。支援多券商同時串接與自動下單。" />

      <div className="grid grid-cols-1 gap-8">
        {/* eToro */}
        <div className="bg-surface-container p-8 rounded-[32px] border border-outline-variant/5">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#1976d2]/10 rounded-2xl text-[#1976d2]">
                <Globe size={20} />
              </div>
              <div>
                <h3 className="font-bold text-lg tracking-tight">eToro</h3>
                <p className="text-[10px] uppercase font-black text-on-surface-variant tracking-widest mt-1">Social Trading & Stocks</p>
              </div>
            </div>
            <Switch checked={settings.enable_etoro} onChange={(v: boolean) => update("enable_etoro", v)} />
          </div>
          <div className="grid grid-cols-3 gap-6">
             <div className="col-span-1">
               <label className="block text-[10px] font-black uppercase text-on-surface-variant mb-2 tracking-widest pl-1">執行模式</label>
               <select 
                value={settings.etoro_mode || "demo"}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) => update("etoro_mode", e.target.value)}
                className="w-full bg-surface-container-high border-2 border-outline-variant/10 rounded-xl px-4 py-3 text-sm focus:border-primary/50 outline-none"
               >
                 <option value="demo">虛擬帳戶 (Demo)</option>
                 <option value="real">真實帳戶 (Real)</option>
               </select>
             </div>
             <SecretInput label="API Key" id="et_key" value={settings.etoro_api_key || ""} toggle={toggle} show={secrets.et_key} onChange={(v: string) => update("etoro_api_key", v)} />
             <SecretInput label="User Key" id="et_user" value={settings.etoro_user_key || ""} toggle={toggle} show={secrets.et_user} onChange={(v: string) => update("etoro_user_key", v)} />
          </div>
        </div>

        {/* IBKR */}
        <div className="bg-surface-container p-8 rounded-[32px] border border-outline-variant/5">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#b22222]/10 rounded-2xl text-[#b22222]">
                <Building2 size={20} />
              </div>
              <div>
                <h3 className="font-bold text-lg tracking-tight">Interactive Brokers (TWS/Gateway)</h3>
                <p className="text-[10px] uppercase font-black text-on-surface-variant tracking-widest mt-1">專業級外匯、股票、期權</p>
              </div>
            </div>
            <Switch checked={settings.enable_ibkr} onChange={(v: boolean) => update("enable_ibkr", v)} />
          </div>
          <div className="grid grid-cols-3 gap-6">
             <LabeledInput label="Gateway Host" value={settings.ibkr_host || "127.0.0.1"} onChange={(v: string) => update("ibkr_host", v)} />
             <LabeledInput label="TWS Port" value={settings.ibkr_port || 7497} onChange={(v: string) => update("ibkr_port", v)} />
             <LabeledInput label="Account ID" value={settings.ibkr_account || ""} onChange={(v: string) => update("ibkr_account", v)} />
          </div>
        </div>

        {/* Futu */}
        <div className="bg-surface-container p-8 rounded-[32px] border border-outline-variant/5">
          <div className="flex justify-between items-start mb-6">
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-[#fbd900]/10 rounded-2xl text-[#fbd900]">
                <TrendingUp size={20} />
              </div>
              <div>
                <h3 className="font-bold text-lg tracking-tight">富途 (Futu Open API)</h3>
                <p className="text-[10px] uppercase font-black text-on-surface-variant tracking-widest mt-1">港美股與即時行情</p>
              </div>
            </div>
            <Switch checked={settings.enable_futu} onChange={(v: boolean) => update("enable_futu", v)} />
          </div>
          <div className="grid grid-cols-4 gap-6">
             <LabeledInput label="Host" value={settings.futu_host || "127.0.0.1"} onChange={(v: string) => update("futu_host", v)} />
             <LabeledInput label="Port" value={settings.futu_port || 11111} onChange={(v: string) => update("futu_port", v)} />
             <div className="col-span-2">
               <SecretInput label="Unlock Password" id="futu_pwd" value={settings.futu_pwd || ""} toggle={toggle} show={secrets.futu_pwd} onChange={(v: string) => update("futu_pwd", v)} />
             </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function SystemPanel({ settings, update }: any) {
  const days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
  const currentDays = settings.schedule_daily_days ? settings.schedule_daily_days.split(",") : [];

  const toggleDay = (day: string) => {
    let newDays;
    if (currentDays.includes(day)) {
      newDays = currentDays.filter((d: string) => d !== day);
    } else {
      newDays = [...currentDays, day];
    }
    update("schedule_daily_days", newDays.join(","));
  };

  return (
    <div className="space-y-12">
      <SectionHead title="系統排程與分析頻率" desc="定義 AI 掃描市場與生成報告的時間表。" />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <SettingCard title="每日例行工作" icon={<History size={20} />} desc="設定每日 CIO 自動分析與持倉掃描的時間。">
           <div className="space-y-6">
             <LabeledInput label="執行時間 (Daily Time)" type="time" value={settings.schedule_daily || "20:00"} onChange={(v: string) => update("schedule_daily", v)} />
             <div className="space-y-3">
                <p className="text-[10px] font-black uppercase text-on-surface-variant tracking-widest pl-1">執行日期 (Weekly Cycle)</p>
                <div className="flex flex-wrap gap-2">
                   {days.map(day => (
                     <button
                      key={day}
                      onClick={() => toggleDay(day)}
                      className={cn(
                        "px-3 py-1.5 rounded-lg text-[10px] font-bold border transition-all",
                        currentDays.includes(day) ? "bg-primary border-primary text-on-primary" : "border-outline-variant/30 text-on-surface-variant"
                      )}
                     >
                       {day.slice(0, 3).toUpperCase()}
                     </button>
                   ))}
                </div>
             </div>
           </div>
        </SettingCard>

        <SettingCard title="週報生成任務" icon={<ExternalLink size={20} />} desc="在特定週末時間進行全盤回測與策略修正報告。">
           <div className="space-y-6">
             <LabeledInput label="週末執行時間" type="time" value={settings.schedule_weekly || "08:00"} onChange={(v: string) => update("schedule_weekly", v)} />
             <div>
                <label className="block text-[10px] font-black uppercase text-on-surface-variant mb-2 tracking-widest pl-1">目標星期</label>
                <select 
                  value={settings.schedule_weekly_day || "Saturday"}
                  onChange={(e: React.ChangeEvent<HTMLSelectElement>) => update("schedule_weekly_day", e.target.value)}
                  className="w-full bg-surface-container-high border-2 border-outline-variant/10 rounded-xl px-4 py-3 text-sm focus:border-primary/50 outline-none"
                >
                  <option value="Saturday">週六 (Saturday)</option>
                  <option value="Sunday">週日 (Sunday)</option>
                </select>
             </div>
           </div>
        </SettingCard>

        {/* System & Localization */}
        <SettingCard title="環境與定位" icon={<Globe size={20} />} desc="系統語言、顯示時區與環境標籤。">
           <div className="space-y-4">
              <LabeledInput label="顯示時區 (Timezone)" value={settings.DISPLAY_TIMEZONE || "Asia/Taipei"} onChange={(v: string) => update("DISPLAY_TIMEZONE", v)} />
              <div className="flex justify-between items-center bg-surface-container-high p-4 rounded-xl">
                 <span className="text-xs font-bold">系統語言</span>
                 <select value="zh-TW" disabled className="bg-transparent font-bold text-primary opacity-50">
                    <option value="zh-TW">繁體中文 (Taiwan)</option>
                 </select>
              </div>
           </div>
        </SettingCard>

        <SettingCard title="開發與通訊" icon={<Code size={20} />} desc="WebSocket 端口與核心通訊伺服器路徑。">
           <div className="space-y-4">
              <LabeledInput label="WebSocket Port" value={settings.WS_PORT || 3000} onChange={(v: string) => update("WS_PORT", v)} />
              <LabeledInput label="Internal Base URL" value={settings.INTERNAL_BASE_URL || "http://localhost:8000"} onChange={(v: string) => update("INTERNAL_BASE_URL", v)} />
           </div>
        </SettingCard>
      </div>
    </div>
  );
}

// --- Helper UI Components ---

function SectionHead({ title, desc }: any) {
  return (
    <div>
      <h2 className="text-2xl font-bold tracking-tight mb-2">{title}</h2>
      <p className="text-sm text-on-surface-variant/60">{desc}</p>
    </div>
  );
}

function SettingCard({ title, icon, desc, children }: any) {
  return (
    <div className="bg-surface-container p-8 rounded-[32px] border border-outline-variant/5 shadow-sm flex flex-col">
       <div className="flex items-center gap-3 mb-4">
          <div className="p-2.5 bg-background rounded-2xl text-primary border border-outline-variant/10">
            {icon}
          </div>
          <h3 className="font-bold text-lg tracking-tight">{title}</h3>
       </div>
       <p className="text-xs text-on-surface-variant/60 leading-relaxed mb-6">
         {desc}
       </p>
       <div className="mt-auto">
          {children}
       </div>
    </div>
  );
}

function LabeledInput({ label, value, onChange, placeholder, disabled, type = "text" }: {
  label: string;
  value: any;
  onChange?: (v: string) => void;
  placeholder?: string;
  disabled?: boolean;
  type?: string;
}) {
  return (
    <div className="space-y-2">
      <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest pl-1">
        {label}
      </label>
      <input
        type={type}
        disabled={disabled}
        value={value}
        onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange && onChange(e.target.value)}
        className="w-full bg-surface-container-high border-2 border-outline-variant/10 rounded-xl px-4 py-3 text-sm font-mono focus:border-primary/50 transition-all outline-none"
        placeholder={placeholder}
      />
    </div>
  );
}

function SecretInput({ label, value, id, toggle, show, onChange }: {
  label: string;
  value: any;
  id: string;
  toggle: (id: string) => void;
  show: boolean;
  onChange: (v: string) => void;
}) {
  return (
    <div className="space-y-2">
      <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest pl-1">
        {label}
      </label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
          className="w-full bg-surface-container-high border-2 border-outline-variant/10 rounded-xl pl-4 pr-12 py-3 text-sm font-mono focus:border-primary/50 transition-all outline-none"
        />
        <button
          onClick={() => toggle(id)}
          className="absolute right-4 top-1/2 -translate-y-1/2 text-on-surface-variant/50 hover:text-primary transition-colors"
        >
          {show ? <EyeOff size={16} /> : <Eye size={16} />}
        </button>
      </div>
    </div>
  );
}

function InterestSelector({ label, value, onChange }: { label: string, value: string, onChange: (v: string) => void }) {
  const options = [
    { id: 'sentinel', label: '🛡️ Sentinel 警報' },
    { id: 'report',   label: '📊 投資報告' },
    { id: 'approval', label: '✅ 交易審核' },
    { id: 'trading',  label: '💸 交易執行' },
  ];

  const currentInterests = value ? value.split(',').map(s => s.trim()) : [];

  const toggleInterest = (id: string) => {
    let next;
    if (currentInterests.includes(id)) {
      next = currentInterests.filter(i => i !== id);
    } else {
      next = [...currentInterests, id];
    }
    onChange(next.join(','));
  };

  return (
    <div className="space-y-2">
      <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest pl-1 mb-3">
        {label}
      </label>
      <div className="flex flex-wrap gap-2">
        {options.map(opt => {
          const isActive = currentInterests.includes(opt.id);
          return (
            <button
              key={opt.id}
              onClick={() => toggleInterest(opt.id)}
              className={cn(
                "px-4 py-2 rounded-xl text-xs font-bold border transition-all flex items-center gap-2",
                isActive 
                  ? "bg-primary/10 border-primary/30 text-primary shadow-sm" 
                  : "bg-background/40 border-outline-variant/20 text-on-surface-variant/70 hover:border-outline-variant/40"
              )}
            >
              <div className={cn(
                "w-3 h-3 rounded-full border-2 transition-all",
                isActive ? "bg-primary border-primary scale-110" : "border-outline-variant/40"
              )} />
              {opt.label}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Switch({ checked, onChange }: { checked: boolean, onChange: (v: boolean) => void }) {
  return (
    <button
      onClick={() => onChange(!checked)}
      className={cn(
        "relative w-12 h-6 rounded-full transition-all duration-300 outline-none",
        checked ? "bg-primary shadow-inner" : "bg-surface-container-highest"
      )}
    >
      <div className={cn(
        "absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-all duration-300 shadow-sm",
        checked ? "translate-x-6" : "translate-x-0"
      )} />
    </button>
  );
}

// --- Placeholder Component ---
function PlaceholderContainer({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center min-h-[400px] opacity-20 border-2 border-dashed border-outline-variant/30 rounded-3xl">
       <Loader2 className="animate-spin mb-4" />
       <p className="text-xs font-black uppercase tracking-widest">{label} Panel Initializing...</p>
    </div>
  );
}
