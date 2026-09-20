"use client";

import React from "react";
import {
  Loader2, Save, CheckCircle2, AlertCircle, RotateCcw, Play,
} from "lucide-react";
import api from "@/lib/api";
import { cn } from "@/lib/utils";
import { useWorkflow, useNodePalette } from "../useWorkflows";
import { LayerGraph } from "./LayerGraph";
import type { ValidateResult } from "../types";

/**
 * Edit one workflow document.
 *
 * Validate-before-save is enforced on the SERVER (PUT returns 400 for a document
 * that will not load), not just offered here — these graphs run scheduled
 * portfolio reviews, so a broken save would surface as a missed run rather than
 * as an error anyone sees.
 *
 * 儲存前驗證由伺服器強制（PUT 對無法載入的文件回 400），而非僅在前端提示：
 * 這些圖負責排程的投組審查，存壞了會以「漏掉一次執行」的形式出現。
 */
export function WorkflowEditor({ id, onSaved }: { id: string; onSaved?: () => void }) {
  const { workflow, isLoading, refresh } = useWorkflow(id);
  const palette = useNodePalette();

  const [draft, setDraft] = React.useState<string | null>(null);
  const [check, setCheck] = React.useState<ValidateResult | null>(null);
  const [busy, setBusy] = React.useState<"validate" | "save" | null>(null);
  const [banner, setBanner] = React.useState<{ kind: "ok" | "err"; msg: string } | null>(null);

  React.useEffect(() => {
    setDraft(null);
    setCheck(null);
    setBanner(null);
  }, [id]);

  const text = draft ?? workflow?.yaml ?? "";
  const dirty = draft !== null && draft !== workflow?.yaml;

  async function validate() {
    setBusy("validate");
    setBanner(null);
    try {
      const res = await api.post<ValidateResult>("/api/v1/workflows/validate", { yaml: text });
      setCheck(res.data);
      setBanner(
        res.data.valid
          ? { kind: "ok", msg: `Valid — ${res.data.node_count} nodes in ${res.data.layers.length} layers.` }
          : { kind: "err", msg: res.data.error ?? "invalid" },
      );
    } catch (err: any) {
      setBanner({ kind: "err", msg: err?.response?.data?.detail ?? "validation request failed" });
    } finally {
      setBusy(null);
    }
  }

  async function save() {
    setBusy("save");
    setBanner(null);
    try {
      await api.put(`/api/v1/workflows/${id}`, { yaml: text });
      setBanner({ kind: "ok", msg: "Saved. Previous version snapshotted to .history/." });
      setDraft(null);
      setCheck(null);
      refresh();
      onSaved?.();
    } catch (err: any) {
      // 400 carries the loader's own error text, which names the offending node.
      setBanner({ kind: "err", msg: err?.response?.data?.detail ?? "save failed" });
    } finally {
      setBusy(null);
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 p-6 text-on-surface-variant">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading {id}…
      </div>
    );
  }

  const layers = check?.layers ?? workflow?.layers ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="font-mono text-sm font-bold text-on-surface">{id}</h2>
          {workflow?.description && (
            <p className="mt-0.5 max-w-2xl text-xs text-on-surface-variant">
              {workflow.description}
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          {dirty && (
            <button
              onClick={() => { setDraft(null); setCheck(null); setBanner(null); }}
              className="inline-flex items-center gap-1.5 rounded-md border border-outline-variant/30 px-2.5 py-1.5 text-xs text-on-surface-variant hover:bg-surface-variant"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Discard
            </button>
          )}
          <button
            onClick={validate}
            disabled={busy !== null}
            className="inline-flex items-center gap-1.5 rounded-md border border-outline-variant/30 px-2.5 py-1.5 text-xs font-medium text-on-surface hover:bg-surface-variant disabled:opacity-50"
          >
            {busy === "validate" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            Validate
          </button>
          <button
            onClick={save}
            disabled={busy !== null || !dirty}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium",
              dirty ? "bg-primary text-on-primary hover:opacity-90"
                    : "cursor-not-allowed bg-surface-variant text-on-surface-variant",
            )}
          >
            {busy === "save" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
            Save
          </button>
        </div>
      </div>

      {banner && (
        <div className={cn(
          "flex items-start gap-2 rounded-md px-3 py-2 text-xs",
          banner.kind === "ok" ? "bg-primary/10 text-primary" : "bg-error/10 text-error",
        )}>
          {banner.kind === "ok"
            ? <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            : <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span className="break-words font-mono">{banner.msg}</span>
        </div>
      )}

      {workflow && !workflow.valid && !banner && (
        <div className="flex items-start gap-2 rounded-md bg-error/10 px-3 py-2 text-xs text-error">
          <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
          <span className="break-words font-mono">
            This file does not currently load: {workflow.error}
          </span>
        </div>
      )}

      {layers.length > 0 && (
        <section>
          <h3 className="mb-2 text-[10px] font-bold uppercase tracking-widest text-on-surface-variant">
            Execution order (derived from input/output keys)
          </h3>
          <LayerGraph layers={layers} />
        </section>
      )}

      <textarea
        value={text}
        onChange={(e) => setDraft(e.target.value)}
        spellCheck={false}
        className="h-[460px] w-full rounded-md border border-outline-variant/30 bg-surface-container p-3 font-mono text-xs leading-relaxed text-on-surface focus:outline-none focus:ring-1 focus:ring-primary"
      />

      <details className="rounded-md border border-outline-variant/20 px-3 py-2">
        <summary className="cursor-pointer text-xs font-medium text-on-surface">
          Available code nodes ({Object.keys(palette).length})
        </summary>
        <p className="mt-2 text-[11px] text-on-surface-variant">
          A <code>type: code</code> node may only reference a name from this list.
          Arbitrary import paths are rejected.
        </p>
        <ul className="mt-2 space-y-1">
          {Object.entries(palette).map(([name, desc]) => (
            <li key={name} className="text-[11px]">
              <code className="text-primary">{name}</code>
              <span className="text-on-surface-variant"> — {desc}</span>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
