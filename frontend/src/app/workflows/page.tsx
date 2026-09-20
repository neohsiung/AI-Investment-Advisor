"use client";

import React from "react";
import { GitBranch, AlertCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkflowList } from "@/features/workflows/useWorkflows";
import { WorkflowEditor } from "@/features/workflows/components/WorkflowEditor";

/**
 * Workflows.
 *
 * The analysis graphs used to be ~40 hand-constructed CodeNode/AgentNode objects
 * across three classes in src/infrastructure/workflow/portfolio_dag.py (620
 * lines). Changing which tier an agent ran at, or inserting a step, meant editing
 * Python and redeploying. They are now YAML in config/workflows/, editable here.
 *
 * Deliberately not a drag-and-drop canvas: the execution order is derived from
 * the input/output keys rather than drawn, so a canvas would have to invent edges
 * the engine does not actually read.
 *
 * 分析圖原本是三個類別中約 40 個手寫節點物件（620 行）；改 tier 或插入步驟都得
 * 改 Python 並重新部署。刻意不做拖拉畫布：執行順序由輸入輸出鍵推導而非畫出，
 * 畫布反而得虛構引擎並不讀取的連線。
 */
export default function WorkflowsPage() {
  const { workflows, isLoading, refresh } = useWorkflowList();
  const [selected, setSelected] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!selected && workflows.length) setSelected(workflows[0].id);
  }, [workflows, selected]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex items-center gap-3">
        <GitBranch className="h-5 w-5 text-primary" />
        <div>
          <h1 className="text-lg font-bold text-on-surface">Workflows</h1>
          <p className="text-xs text-on-surface-variant">
            Defined in config/workflows/ — execution order is derived from the key wiring
          </p>
        </div>
      </header>

      {isLoading ? (
        <div className="flex items-center gap-2 text-on-surface-variant">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : (
        <div className="grid gap-6 md:grid-cols-[220px_1fr]">
          <nav className="space-y-1">
            {workflows.map((w) => (
              <button
                key={w.id}
                onClick={() => setSelected(w.id)}
                className={cn(
                  "w-full rounded-md px-3 py-2 text-left transition-colors",
                  selected === w.id ? "bg-primary/10" : "hover:bg-surface-variant",
                )}
              >
                <div className="flex items-center gap-1.5">
                  <span className="truncate font-mono text-xs font-medium text-on-surface">
                    {w.id}
                  </span>
                  {!w.valid && <AlertCircle className="h-3 w-3 shrink-0 text-error" />}
                </div>
                <div className="mt-0.5 text-[10px] text-on-surface-variant">
                  {w.valid ? `${w.node_count} nodes · ${w.layer_count} layers` : "does not load"}
                </div>
              </button>
            ))}
          </nav>

          <div>{selected && <WorkflowEditor id={selected} onSaved={refresh} />}</div>
        </div>
      )}
    </div>
  );
}
