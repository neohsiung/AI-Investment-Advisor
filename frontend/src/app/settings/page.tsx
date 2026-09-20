"use client";

import React from "react";
import { Settings as SettingsIcon, Send, Loader2 } from "lucide-react";
import api from "@/lib/api";
import { SchemaForm } from "@/features/settings/components/SchemaForm";
import { CostProfileSelector } from "@/features/settings/components/CostProfileSelector";
import { LLMSettingsPanel } from "@/features/llm-settings/components/LLMSettingsPanel";

/**
 * Settings.
 *
 * This file was 1030 lines: six hand-written tabs with a bespoke JSX block per
 * setting, its own show/hide state per secret, and a third copy of the
 * data-source list hardcoded inline. Adding one knob meant editing it.
 *
 * The fields now come from config/settings_schema.yaml via
 * GET /api/v1/settings/schema, so adding a setting is a YAML row — no
 * TypeScript, no rebuild. What stays hand-written here is only what is not a
 * field: the LLM provider/model/tier panel (its own feature module) and the
 * send-a-test-notification action.
 *
 * 本檔原本 1030 行、每個設定一段手寫 JSX，且內嵌了第三份資料來源清單。
 * 欄位改由後端 schema 端點提供，新增設定只需改 YAML。
 * 這裡只保留「不是欄位」的東西：LLM 面板與測試通知動作。
 */
export default function SettingsPage() {
  const [testing, setTesting] = React.useState<string | null>(null);

  async function sendTest(channel: string) {
    setTesting(channel);
    try {
      await api.post("/api/v1/settings/test-notification", { channels: [channel] });
      alert(`${channel.toUpperCase()} 測試通知已發送，請檢查您的裝置。`);
    } catch (err: any) {
      alert(`測試失敗: ${err?.response?.data?.detail ?? err?.message ?? "unknown"}`);
    } finally {
      setTesting(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8 p-6">
      <header className="flex items-center gap-3">
        <SettingsIcon className="h-5 w-5 text-primary" />
        <div>
          <h1 className="text-lg font-bold text-on-surface">系統設定</h1>
          <p className="text-xs text-on-surface-variant">
            欄位由 config/settings_schema.yaml 定義
          </p>
        </div>
      </header>

      <section className="space-y-3">
        <h2 className="text-sm font-bold text-on-surface">運行成本方案</h2>
        <p className="text-xs text-on-surface-variant">
          調整系統背景哨兵巡邏頻率與 AI 運算預算，隨時依個人需求即時切換。
        </p>
        <CostProfileSelector />
      </section>

      <SchemaForm />

      <section className="space-y-3">
        <h2 className="text-sm font-bold text-on-surface">測試通知</h2>
        <p className="text-xs text-on-surface-variant">
          使用目前已儲存的設定發送一則測試訊息。
        </p>
        <div className="flex flex-wrap gap-2">
          {["telegram", "line", "email"].map((ch) => (
            <button
              key={ch}
              onClick={() => sendTest(ch)}
              disabled={testing !== null}
              className="inline-flex items-center gap-2 rounded-md border border-outline-variant/30 px-3 py-1.5 text-xs font-medium text-on-surface hover:bg-surface-variant disabled:opacity-50"
            >
              {testing === ch ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="h-3.5 w-3.5" />
              )}
              {ch.toUpperCase()}
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-bold text-on-surface">AI 引擎</h2>
        <p className="text-xs text-on-surface-variant">
          Provider、模型與 tier 綁定由專屬面板管理（llm_providers / llm_tier_bindings 表）。
        </p>
        <LLMSettingsPanel />
      </section>
    </div>
  );
}
