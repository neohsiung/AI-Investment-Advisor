"use client";

import React from "react";
import useSWR, { mutate } from "swr";
import {
  Blocks,
  Database,
  Bell,
  Wrench,
  Sparkles,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Check,
  X,
  Radio,
} from "lucide-react";
import api, { fetcher } from "@/lib/api";
import { cn } from "@/lib/utils";
import { SchemaForm } from "@/features/settings/components/SchemaForm";

type Tab = "sources" | "channels" | "tools" | "skills";

interface SkillItem {
  name: string;
  description: string;
  category: string;
  tier: string;
  version: string;
  intents: string[];
  tags: string[];
  platform: string[];
  enabled: boolean;
  is_pending: boolean;
  has_impl: boolean;
}

interface SkillListResponse {
  skills: SkillItem[];
  pending_count: number;
}

export default function ExtensionsPage() {
  const [tab, setTab] = React.useState<Tab>("sources");
  const [actingSkill, setActingSkill] = React.useState<string | null>(null);
  const [banner, setBanner] = React.useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  // SWR for skills
  const { data: skillsData, isLoading: skillsLoading } = useSWR<SkillListResponse>(
    "/api/v1/skills",
    fetcher,
    { revalidateOnFocus: false }
  );

  const skills = skillsData?.skills ?? [];
  const pendingCount = skillsData?.pending_count ?? 0;

  const TABS: { id: Tab; label: string; icon: any; count?: number }[] = [
    { id: "sources", label: "資料來源 (Data Sources)", icon: Database },
    { id: "channels", label: "通知管道 (Channels)", icon: Bell },
    { id: "tools", label: "工具與 MCP (Tools)", icon: Wrench },
    { id: "skills", label: "技能模組 (Skills)", icon: Sparkles, count: skills.length },
  ];

  async function toggleSkill(name: string, currentState: boolean) {
    setActingSkill(name);
    try {
      await api.post(`/api/v1/skills/${name}/toggle`, { enabled: !currentState });
      setBanner({ kind: "ok", msg: `已${!currentState ? "啟用" : "停用"}技能 ${name}` });
      mutate("/api/v1/skills");
    } catch (err: any) {
      setBanner({ kind: "err", msg: err?.response?.data?.detail ?? "切換失敗" });
    } finally {
      setActingSkill(null);
    }
  }

  async function handleApprove(name: string) {
    setActingSkill(name);
    try {
      await api.post(`/api/v1/skills/${name}/approve`);
      setBanner({ kind: "ok", msg: `已核准並啟用技能 ${name}` });
      mutate("/api/v1/skills");
    } catch (err: any) {
      setBanner({ kind: "err", msg: err?.response?.data?.detail ?? "核准失敗" });
    } finally {
      setActingSkill(null);
    }
  }

  async function handleReject(name: string) {
    setActingSkill(name);
    try {
      await api.post(`/api/v1/skills/${name}/reject`);
      setBanner({ kind: "ok", msg: `已拒絕並移除待核准技能 ${name}` });
      mutate("/api/v1/skills");
    } catch (err: any) {
      setBanner({ kind: "err", msg: err?.response?.data?.detail ?? "拒絕失敗" });
    } finally {
      setActingSkill(null);
    }
  }

  const activeSkills = skills.filter((s) => !s.is_pending);
  const pendingSkills = skills.filter((s) => s.is_pending);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex items-center gap-3">
        <Blocks className="h-6 w-6 text-primary" />
        <div>
          <h1 className="text-xl font-bold text-on-surface font-headline">外掛與擴充 (Extensions)</h1>
          <p className="text-xs text-on-surface-variant">
            宣告式 Manifest 驅動 · 統一外掛註冊表 · 自動生成設定與憑證表單
          </p>
        </div>
      </header>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 border-b border-outline-variant/20 pb-2">
        {TABS.map((t) => {
          const Icon = t.icon;
          const isActive = tab === t.id;
          return (
            <button
              key={t.id}
              onClick={() => {
                setTab(t.id);
                setBanner(null);
              }}
              className={cn(
                "flex items-center gap-2 rounded-md px-3.5 py-2 text-xs font-medium transition-all",
                isActive
                  ? "bg-primary text-on-primary shadow-sm"
                  : "text-on-surface-variant hover:bg-surface-variant"
              )}
            >
              <Icon className="h-4 w-4" />
              <span>{t.label}</span>
              {t.count !== undefined && (
                <span className={cn("ml-1 rounded px-1.5 py-0.5 text-[10px]", isActive ? "bg-white/20" : "bg-surface-variant")}>
                  {t.count}
                </span>
              )}
              {t.id === "skills" && pendingCount > 0 && (
                <span className="ml-1 rounded-full bg-amber-500 px-1.5 py-0.2 text-[10px] text-white">
                  {pendingCount} 待審
                </span>
              )}
            </button>
          );
        })}
      </div>

      {banner && (
        <div
          className={cn(
            "flex items-start gap-2 rounded-md px-3.5 py-2 text-sm",
            banner.kind === "ok" ? "bg-primary/10 text-primary" : "bg-error/10 text-error"
          )}
        >
          {banner.kind === "ok" ? <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" /> : <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />}
          <span>{banner.msg}</span>
        </div>
      )}

      {/* Data Sources Tab */}
      {tab === "sources" && (
        <div className="space-y-4">
          <div className="rounded-lg bg-surface-container-low p-4 border border-outline-variant/15">
            <h2 className="text-sm font-semibold text-on-surface flex items-center gap-2">
              <Database className="h-4 w-4 text-primary" /> 行情與經濟數據源設定
            </h2>
            <p className="mt-1 text-xs text-on-surface-variant">
              支援 Polygon, Tiingo, Finnhub, Fred, AlphaVantage, Yahoo 等多資料源。憑證與開關由系統 SchemaForm 動態管理。
            </p>
          </div>
          <SchemaForm allowedGroupIds={["sources", "broker"]} initialGroup="sources" />
        </div>
      )}

      {/* Channels Tab */}
      {tab === "channels" && (
        <div className="space-y-4">
          <div className="rounded-lg bg-surface-container-low p-4 border border-outline-variant/15">
            <h2 className="text-sm font-semibold text-on-surface flex items-center gap-2">
              <Bell className="h-4 w-4 text-primary" /> 通知管道設定
            </h2>
            <p className="mt-1 text-xs text-on-surface-variant">
              支援 Discord, Telegram, Slack, Line, Email, Messenger, Google Chat 等通知管道。各管道憑證加密儲存。
            </p>
          </div>
          <SchemaForm allowedGroupIds={["notify"]} initialGroup="notify" hideGroupTabs={true} />
        </div>
      )}

      {/* Tools / MCP Tab */}
      {tab === "tools" && (
        <div className="space-y-4">
          <div className="rounded-lg bg-surface-container-low p-4 border border-outline-variant/15">
            <h2 className="text-sm font-semibold text-on-surface flex items-center gap-2">
              <Wrench className="h-4 w-4 text-primary" /> 工具與 MCP Server 介面
            </h2>
            <p className="mt-1 text-xs text-on-surface-variant">
              透過 config/tools.yaml 宣告共用工具與外部 MCP 伺服器，已消除舊版損壞的 HTTP 工具分派漏洞。
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="rounded-lg bg-surface-container-low p-4 border border-outline-variant/15 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-on-surface">內建工具集 (Built-in Tools)</span>
                <span className="rounded bg-primary/10 px-2 py-0.5 text-[10px] text-primary">宣告於 tools.yaml</span>
              </div>
              <ul className="space-y-2 text-xs text-on-surface-variant">
                <li className="rounded border border-outline-variant/10 p-2.5">
                  <div className="font-mono font-medium text-on-surface">run_script</div>
                  <div className="mt-1 text-[11px]">執行 Skill 目錄下的 Python CLI 工具，支援受限引數與安全檢驗。</div>
                </li>
                <li className="rounded border border-outline-variant/10 p-2.5">
                  <div className="font-mono font-medium text-on-surface">llama_index_rag</div>
                  <div className="mt-1 text-[11px]">財務報告與市場新聞的語意檢索與知識庫儲存 (pgvector)。</div>
                </li>
              </ul>
            </div>

            <div className="rounded-lg bg-surface-container-low p-4 border border-outline-variant/15 space-y-3">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-on-surface">外部 MCP 整合 (External MCP)</span>
                <span className="rounded bg-surface-variant px-2 py-0.5 text-[10px] text-on-surface-variant">可擴充</span>
              </div>
              <p className="text-xs text-on-surface-variant">
                外部 MCP Server 可直接在 <code className="bg-surface-variant px-1 rounded">config/tools.yaml</code> 的 <code className="bg-surface-variant px-1 rounded">external:</code> 區塊設定 endpoint 與認證 header。所有 Agent 均可透明調用。
              </p>
              <div className="rounded border border-outline-variant/10 p-2.5 text-[11px] font-mono text-on-surface-variant">
                # config/tools.yaml 範例<br/>
                external:<br/>
                &nbsp;&nbsp;- name: custom_tools<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;transport: sse<br/>
                &nbsp;&nbsp;&nbsp;&nbsp;url: http://127.0.0.1:8001/mcp
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Skills Tab */}
      {tab === "skills" && (
        <div className="space-y-4">
          <div className="rounded-lg bg-surface-container-low p-4 border border-outline-variant/15">
            <h2 className="text-sm font-semibold text-on-surface flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" /> 技能模組 (Skills)
            </h2>
            <p className="mt-1 text-xs text-on-surface-variant">
              已全面標準化為 <code className="bg-surface-variant px-1 rounded">SKILL.md</code> 規格。支援意圖路由（Intents）、動態啟用/停用，以及 GapDetector 自動生成技能的審核佇列。
            </p>
          </div>

          {skillsLoading && (
            <div className="flex items-center gap-2 p-8 text-on-surface-variant">
              <Loader2 className="h-4 w-4 animate-spin" /> 載入技能清單…
            </div>
          )}

          {/* Pending Approval Queue */}
          {pendingSkills.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-amber-500">
                <Radio className="h-4 w-4 animate-pulse" /> 待核准技能佇列 (Pending Approval)
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                {pendingSkills.map((ps) => (
                  <div key={ps.name} className="flex items-center justify-between rounded-md bg-surface-container p-3 border border-outline-variant/10">
                    <div>
                      <div className="font-mono text-xs font-bold text-on-surface">{ps.name}</div>
                      <div className="text-[11px] text-on-surface-variant line-clamp-1">{ps.description}</div>
                    </div>
                    <div className="flex items-center gap-1.5 ml-2">
                      <button
                        onClick={() => handleApprove(ps.name)}
                        disabled={actingSkill === ps.name}
                        className="flex items-center gap-1 rounded bg-primary px-2.5 py-1 text-[11px] font-medium text-on-primary hover:bg-primary/90 transition-all"
                      >
                        <Check className="h-3 w-3" /> 核准
                      </button>
                      <button
                        onClick={() => handleReject(ps.name)}
                        disabled={actingSkill === ps.name}
                        className="flex items-center gap-1 rounded bg-error/10 px-2 py-1 text-[11px] font-medium text-error hover:bg-error/20 transition-all"
                      >
                        <X className="h-3 w-3" /> 拒絕
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Active Skills Grid */}
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {activeSkills.map((s) => {
              const isActing = actingSkill === s.name;
              return (
                <div
                  key={s.name}
                  className={cn(
                    "flex flex-col justify-between rounded-lg border p-4 transition-all bg-surface-container-low",
                    s.enabled ? "border-outline-variant/20" : "border-outline-variant/10 opacity-60"
                  )}
                >
                  <div className="space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-mono text-xs font-bold text-on-surface truncate">{s.name}</div>
                        <span className="rounded bg-surface-variant px-1.5 py-0.5 text-[10px] text-on-surface-variant">
                          {s.category} · {s.tier}
                        </span>
                      </div>
                      <button
                        onClick={() => toggleSkill(s.name, s.enabled)}
                        disabled={isActing}
                        className={cn(
                          "rounded-full px-2.5 py-0.5 text-[10px] font-medium transition-colors",
                          s.enabled
                            ? "bg-primary/10 text-primary hover:bg-primary/20"
                            : "bg-surface-variant text-on-surface-variant hover:bg-surface-bright"
                        )}
                      >
                        {isActing ? (
                          <Loader2 className="h-3 w-3 animate-spin" />
                        ) : s.enabled ? (
                          "已啟用"
                        ) : (
                          "已停用"
                        )}
                      </button>
                    </div>

                    <p className="text-xs text-on-surface-variant line-clamp-2 min-h-[2rem]">
                      {s.description || "無說明文件"}
                    </p>
                  </div>

                  <div className="mt-3 pt-2 border-t border-outline-variant/10 space-y-1">
                    {s.intents.length > 0 && (
                      <div className="flex items-center gap-1 text-[10px] text-on-surface-variant">
                        <span className="font-medium text-primary">意圖:</span>
                        <span className="font-mono truncate">{s.intents.join(", ")}</span>
                      </div>
                    )}
                    {s.tags.length > 0 && (
                      <div className="flex flex-wrap gap-1 text-[9px] text-on-surface-variant opacity-80">
                        {s.tags.map((tag) => (
                          <span key={tag} className="rounded bg-surface-variant/50 px-1">
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
