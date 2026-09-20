"use client";

import React from "react";
import { Bot, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { useAgents, usePersonas, useSwarms } from "@/features/agents/useAgents";
import { PromptEditor } from "@/features/agents/components/PromptEditor";

/**
 * Agents.
 *
 * The set of agents used to be hardcoded in three places at once — the factory's
 * if/elif chain, BaseAgent's workspace_map, and
 * LLMAgentOverrideService.KNOWN_AGENT_NAMES — so nowhere in the product could
 * list them, and two of those three lists disagreed about who existed. They are
 * now declared in config/agents/*.md and enumerated by GET /api/v1/agents.
 *
 * 代理清單原本同時硬編在三個地方，產品中沒有任何地方能列出它們，
 * 且其中兩份清單對「誰存在」意見不一。現由 config/agents/*.md 宣告。
 */
type Tab = "agents" | "personas" | "swarms";

export default function AgentsPage() {
  const { agents, isLoading } = useAgents();
  const personas = usePersonas();
  const swarms = useSwarms();

  const [tab, setTab] = React.useState<Tab>("agents");
  const [selected, setSelected] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!selected && agents.length) setSelected(agents[0].id);
  }, [agents, selected]);

  const active = agents.find((a) => a.id === selected);

  const TABS: { id: Tab; label: string; count: number }[] = [
    { id: "agents", label: "代理與提示詞", count: agents.length },
    { id: "personas", label: "人格", count: personas.length },
    { id: "swarms", label: "Swarm 子代理", count: swarms.length },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <header className="flex items-center gap-3">
        <Bot className="h-5 w-5 text-primary" />
        <div>
          <h1 className="text-lg font-bold text-on-surface">代理</h1>
          <p className="text-xs text-on-surface-variant">
            宣告於 config/agents/ · 提示詞覆寫存於資料庫
          </p>
        </div>
      </header>

      <div className="flex flex-wrap gap-1 border-b border-outline-variant/20 pb-2">
        {TABS.map((t) => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={cn("rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
              tab === t.id ? "bg-primary text-on-primary"
                           : "text-on-surface-variant hover:bg-surface-variant")}>
            {t.label} <span className="ml-1 text-[10px]">({t.count})</span>
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-on-surface-variant">
          <Loader2 className="h-4 w-4 animate-spin" /> 載入中…
        </div>
      )}

      {tab === "agents" && !isLoading && (
        <div className="grid gap-6 md:grid-cols-[240px_1fr]">
          <nav className="space-y-1">
            {agents.map((a) => (
              <button key={a.id} onClick={() => setSelected(a.id)}
                className={cn("w-full rounded-md px-3 py-2 text-left transition-colors",
                  selected === a.id ? "bg-primary/10" : "hover:bg-surface-variant")}>
                <div className="flex items-center gap-1.5">
                  <span className="truncate text-xs font-medium text-on-surface">{a.display_name}</span>
                  {a.has_prompt_override && (
                    <span title="有提示詞覆寫" className="h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                  )}
                  {!a.enabled && <AlertCircle className="h-3 w-3 shrink-0 text-error" />}
                </div>
                <div className="mt-0.5 font-mono text-[10px] text-on-surface-variant">
                  {a.impl} · {a.default_tier}
                </div>
              </button>
            ))}
          </nav>

          <div className="space-y-4">
            {active && (
              <>
                <div>
                  <h2 className="text-sm font-bold text-on-surface">{active.display_name}</h2>
                  <p className="mt-0.5 text-xs text-on-surface-variant">{active.description}</p>
                  <dl className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-[10px] text-on-surface-variant">
                    <div>id: {active.id}</div>
                    <div>impl: {active.impl}</div>
                    <div>tier: {active.default_tier}</div>
                    {active.workspace && <div>workspace: {active.workspace}</div>}
                    {active.persona && <div>persona: {active.persona}</div>}
                  </dl>
                </div>
                <PromptEditor agent={active} />
              </>
            )}
          </div>
        </div>
      )}

      {tab === "personas" && (
        <div className="space-y-3">
          <p className="text-xs text-on-surface-variant">
            來自 config/personas/*.md。人格前綴會加在勝出的提示詞之前。
          </p>
          {personas.map((p) => (
            <div key={p.name} className="rounded-md border border-outline-variant/20 p-3">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-on-surface">
                  {p.display_name || p.name}
                </span>
                <span className="font-mono text-[10px] text-on-surface-variant">{p.name}</span>
                {p.tone && <span className="text-[10px] text-on-surface-variant">· {p.tone}</span>}
              </div>
              {p.body && (
                <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap text-[11px] text-on-surface-variant">
                  {p.body}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}

      {tab === "swarms" && (
        <div className="space-y-4">
          <p className="text-xs text-on-surface-variant">
            來自 config/agents/swarms/*.yaml。這些名稱、指令與 tier 原本是各 swarm
            <code className="mx-1">__init__</code> 裡的 Python 字面值。
          </p>
          {swarms.map((s) => (
            <div key={s.id} className="rounded-md border border-outline-variant/20 p-3">
              <div className="mb-2 font-mono text-xs font-bold text-on-surface">{s.id}</div>
              <div className="space-y-2">
                {s.sub_agents.map((sa) => (
                  <div key={sa.name} className="rounded border border-outline-variant/20 bg-surface-container px-2 py-1.5">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[11px] font-medium text-on-surface">{sa.name}</span>
                      <span className="rounded bg-primary/10 px-1.5 text-[10px] text-primary">{sa.tier}</span>
                      {sa.column && (
                        <span className="font-mono text-[10px] text-on-surface-variant">{sa.column}</span>
                      )}
                    </div>
                    <p className="mt-1 text-[11px] text-on-surface-variant">{sa.instruction}</p>
                  </div>
                ))}
                {!s.sub_agents.length && (
                  <div className="flex items-center gap-1.5 text-[11px] text-error">
                    <AlertCircle className="h-3 w-3" /> 名單為空 — 此 swarm 不會產生任何子代理輸出
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
