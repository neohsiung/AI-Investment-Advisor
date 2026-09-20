"use client";

import React from "react";
import { Loader2, Save, RotateCcw, Play, CheckCircle2, AlertCircle, Info } from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";
import { useAgentPrompt } from "../useAgents";
import type { AgentSummary, PromptSource } from "../types";

const SOURCE_LABEL: Record<PromptSource, string> = {
  override: "你的修改（存於資料庫）",
  manifest: "manifest 本文（出貨預設）",
  workspace: "workspace/IDENTITY.md + SOUL.md",
  legacy: "prompts/*.txt（舊路徑）",
  none: "尚無提示詞",
};

/**
 * Edit one agent's system prompt.
 *
 * The editor shows WHICH of the four sources is currently in effect, because
 * saving always creates a database override — so without that label an operator
 * editing a `workspace` prompt could not tell that their save would shadow the
 * file rather than change it.
 *
 * 編輯器會顯示目前生效的是四個來源中的哪一個：儲存一律建立資料庫覆寫，
 * 若不顯示來源，使用者無法得知自己的儲存是「遮蔽檔案」而非「修改檔案」。
 */
export function PromptEditor({ agent }: { agent: AgentSummary }) {
  const { prompt, isLoading, refresh } = useAgentPrompt(agent.id);
  const [draft, setDraft] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState<"save" | "revert" | "test" | null>(null);
  const [banner, setBanner] = React.useState<{ kind: "ok" | "err"; msg: string } | null>(null);
  const [testOut, setTestOut] = React.useState<string | null>(null);

  React.useEffect(() => {
    setDraft(null);
    setBanner(null);
    setTestOut(null);
  }, [agent.id]);

  const text = draft ?? prompt?.prompt ?? "";
  const dirty = draft !== null && draft !== (prompt?.prompt ?? "");

  async function save() {
    setBusy("save"); setBanner(null);
    try {
      await api.put(`/api/v1/agents/${agent.id}/prompt`, { prompt: text, reason: "edited via UI" });
      setBanner({ kind: "ok", msg: "已儲存為覆寫（存於 user_custom_prompts）。" });
      setDraft(null); refresh();
    } catch (err: any) {
      setBanner({ kind: "err", msg: err?.response?.data?.detail ?? "儲存失敗" });
    } finally { setBusy(null); }
  }

  async function revert() {
    setBusy("revert"); setBanner(null);
    try {
      await api.delete(`/api/v1/agents/${agent.id}/prompt`);
      setBanner({ kind: "ok", msg: "已移除覆寫，回到出貨預設值。" });
      setDraft(null); refresh();
    } catch (err: any) {
      setBanner({ kind: "err", msg: err?.response?.data?.detail ?? "移除失敗" });
    } finally { setBusy(null); }
  }

  async function testRun() {
    setBusy("test"); setBanner(null); setTestOut(null);
    try {
      const res = await api.post(`/api/v1/agents/${agent.id}/test`, {
        input: "Summarise the current market in two sentences.",
      });
      setTestOut(res.data.output);
    } catch (err: any) {
      setBanner({ kind: "err", msg: err?.response?.data?.detail ?? "測試執行失敗" });
    } finally { setBusy(null); }
  }

  if (isLoading) {
    return <div className="flex items-center gap-2 p-4 text-on-surface-variant">
      <Loader2 className="h-4 w-4 animate-spin" /> 載入提示詞…
    </div>;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-xs text-on-surface-variant">
          <Info className="h-3.5 w-3.5" />
          目前來源：<span className="font-medium text-on-surface">
            {SOURCE_LABEL[prompt?.source ?? "none"]}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {prompt?.has_override && (
            <button onClick={revert} disabled={busy !== null}
              className="inline-flex items-center gap-1.5 rounded-md border border-outline-variant/30 px-2.5 py-1.5 text-xs text-on-surface-variant hover:bg-surface-variant disabled:opacity-50">
              {busy === "revert" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
              還原預設
            </button>
          )}
          <button onClick={testRun} disabled={busy !== null}
            title="以目前提示詞執行一次；期間強制關閉自動交易"
            className="inline-flex items-center gap-1.5 rounded-md border border-outline-variant/30 px-2.5 py-1.5 text-xs text-on-surface hover:bg-surface-variant disabled:opacity-50">
            {busy === "test" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            測試執行
          </button>
          <button onClick={save} disabled={busy !== null || !dirty}
            className={cn("inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium",
              dirty ? "bg-primary text-on-primary hover:opacity-90"
                    : "cursor-not-allowed bg-surface-variant text-on-surface-variant")}>
            {busy === "save" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            儲存
          </button>
        </div>
      </div>

      {banner && (
        <div className={cn("flex items-start gap-2 rounded-md px-3 py-2 text-xs",
          banner.kind === "ok" ? "bg-primary/10 text-primary" : "bg-error/10 text-error")}>
          {banner.kind === "ok" ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                                : <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span className="break-words">{banner.msg}</span>
        </div>
      )}

      <textarea
        value={text}
        onChange={(e) => setDraft(e.target.value)}
        spellCheck={false}
        placeholder="尚無提示詞。輸入內容後儲存即建立覆寫。"
        className="h-[380px] w-full rounded-md border border-outline-variant/30 bg-surface-container p-3 font-mono text-xs leading-relaxed text-on-surface focus:outline-none focus:ring-1 focus:ring-primary"
      />

      <p className="text-[11px] text-on-surface-variant">
        提示詞無法擴大代理的權限。下單仍須通過 RiskManager 的每日上限、斷路器與
        <code className="mx-1">ai_trading_enabled</code>，這些都不讀取提示詞。
        測試執行期間會強制關閉自動交易。
      </p>

      {testOut && (
        <div className="rounded-md border border-outline-variant/20 bg-surface-container p-3">
          <div className="mb-1 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
            測試輸出（自動交易已關閉）
          </div>
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs text-on-surface">{testOut}</pre>
        </div>
      )}
    </div>
  );
}
