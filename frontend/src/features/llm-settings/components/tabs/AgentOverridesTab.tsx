"use client";

/**
 * AgentOverridesTab — Tab D of the LLM Settings panel (Phase C).
 *
 * Displays a table of per-agent model overrides. Users can:
 *   - View all existing overrides with expanded model details
 *   - Add a new override via the "+ 新增覆寫" button
 *   - Edit an existing override inline
 *   - Delete an override
 *   - Save all changes via "儲存 Agent 覆寫"
 *
 * Design: docs/architecture/multi_provider_multi_model_design.md §5.5
 */

import React, { useState, useCallback } from "react";
import { Plus, RefreshCw, Bot, AlertCircle, Save } from "lucide-react";
import { useAgentOverrides } from "../../use-cases/useAgentOverrides";
import { useModels } from "../../use-cases/useModels";
import { AgentOverrideRow } from "../AgentOverrideRow";
import type {
    AgentOverride,
    AgentOverrideUpdate,
    TierName,
} from "../../domain/types";
import { KNOWN_AGENT_NAMES, AGENT_DISPLAY_NAMES } from "../../domain/types";

// ─── New Override Form ────────────────────────────────────────────────────────

interface NewOverrideFormProps {
    models: ReturnType<typeof useModels>["models"];
    onAdd: (update: AgentOverrideUpdate) => void;
    onCancel: () => void;
}

function NewOverrideForm({ models, onAdd, onCancel }: NewOverrideFormProps) {
    const [agentName, setAgentName] = useState<string>(KNOWN_AGENT_NAMES[0]);
    const [overrideTier, setOverrideTier] = useState<TierName | "">("");
    const [primaryModelId, setPrimaryModelId] = useState("");
    const [forbidLocal, setForbidLocal] = useState(false);
    const [forbidFallback, setForbidFallback] = useState(false);

    const handleAdd = () => {
        if (!overrideTier && !primaryModelId) {
            alert("請選擇 Override Tier 或 Primary Model 其中之一");
            return;
        }
        onAdd({
            agent_name: agentName,
            override_tier: overrideTier || null,
            primary_model_id: primaryModelId || null,
            forbid_local: forbidLocal,
            forbid_fallback: forbidFallback,
            enabled: true,
        });
    };

    return (
        <tr className="bg-primary/5 border-b border-outline-variant/10">
            {/* Agent Name */}
            <td className="px-4 py-3">
                <select
                    value={agentName}
                    onChange={(e) => setAgentName(e.target.value)}
                    className="w-full text-sm bg-surface-container border border-outline-variant/30 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
                >
                    {KNOWN_AGENT_NAMES.map((n) => (
                        <option key={n} value={n}>
                            {AGENT_DISPLAY_NAMES[n]}
                        </option>
                    ))}
                </select>
            </td>

            {/* Override Tier */}
            <td className="px-4 py-3">
                <select
                    value={overrideTier}
                    onChange={(e) => setOverrideTier(e.target.value as TierName | "")}
                    className="w-full text-sm bg-surface-container border border-outline-variant/30 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary"
                >
                    <option value="">— 自訂模型 —</option>
                    <option value="nano">Nano</option>
                    <option value="fast">Fast</option>
                    <option value="smart">Smart</option>
                    <option value="advanced">Advanced</option>
                </select>
            </td>

            {/* Primary Model */}
            <td className="px-4 py-3">
                <select
                    value={primaryModelId}
                    onChange={(e) => setPrimaryModelId(e.target.value)}
                    disabled={!!overrideTier}
                    className="w-full text-sm bg-surface-container border border-outline-variant/30 rounded-lg px-2 py-1 focus:outline-none focus:ring-1 focus:ring-primary disabled:opacity-40"
                >
                    <option value="">— 繼承 Tier 鏈 —</option>
                    {models.filter((m) => m.enabled).map((m) => (
                        <option key={m.id} value={m.id}>
                            {m.provider_code} / {m.model_code}
                        </option>
                    ))}
                </select>
            </td>

            {/* Forbid Local */}
            <td className="px-4 py-3 text-center">
                <input
                    type="checkbox"
                    checked={forbidLocal}
                    onChange={(e) => setForbidLocal(e.target.checked)}
                    className="w-4 h-4 accent-primary"
                />
            </td>

            {/* Forbid Fallback */}
            <td className="px-4 py-3 text-center">
                <input
                    type="checkbox"
                    checked={forbidFallback}
                    onChange={(e) => setForbidFallback(e.target.checked)}
                    className="w-4 h-4 accent-primary"
                />
            </td>

            {/* Enabled (always true for new) */}
            <td className="px-4 py-3 text-center">
                <span className="inline-block w-2 h-2 rounded-full bg-green-400" />
            </td>

            {/* Actions */}
            <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                    <button
                        onClick={handleAdd}
                        className="px-3 py-1 text-xs rounded-lg bg-primary text-on-primary hover:bg-primary/90 transition-colors"
                    >
                        新增
                    </button>
                    <button
                        onClick={onCancel}
                        className="px-3 py-1 text-xs rounded-lg bg-surface-container text-on-surface-variant hover:bg-surface-container-high transition-colors"
                    >
                        取消
                    </button>
                </div>
            </td>
        </tr>
    );
}

// ─── Main Tab ─────────────────────────────────────────────────────────────────

export function AgentOverridesTab() {
    const { overrides, isLoading, isSaving, error, reload, saveOverrides } =
        useAgentOverrides();
    const { models } = useModels();

    // Local draft state (pending changes not yet saved to API)
    const [draftOverrides, setDraftOverrides] = useState<AgentOverride[] | null>(null);
    const [showNewForm, setShowNewForm] = useState(false);
    const [saveError, setSaveError] = useState<string | null>(null);
    const [saveSuccess, setSaveSuccess] = useState(false);

    // Use draft if available, otherwise use server state
    const displayOverrides = draftOverrides ?? overrides;

    // ── Handlers ──────────────────────────────────────────────────────

    const handleAddNew = useCallback((update: AgentOverrideUpdate) => {
        const newOverride: AgentOverride = {
            id: `draft-${Date.now()}`,
            user_id: "",
            agent_name: update.agent_name,
            override_tier: update.override_tier ?? null,
            primary_model_id: update.primary_model_id ?? null,
            primary_model: null,
            fallback_model_ids: update.fallback_model_ids ?? [],
            fallback_models: [],
            forbid_local: update.forbid_local ?? false,
            forbid_fallback: update.forbid_fallback ?? false,
            enabled: update.enabled ?? true,
            notes: update.notes ?? null,
        };
        setDraftOverrides((prev) => [...(prev ?? overrides), newOverride]);
        setShowNewForm(false);
    }, [overrides]);

    const handleRowSave = useCallback(async (update: AgentOverrideUpdate) => {
        // Update draft immediately for optimistic UI
        setDraftOverrides((prev) => {
            const base = prev ?? overrides;
            const idx = base.findIndex((o) => o.agent_name === update.agent_name);
            if (idx === -1) return base;
            const updated = [...base];
            updated[idx] = { ...updated[idx], ...update };
            return updated;
        });
    }, [overrides]);

    const handleDelete = useCallback((agentName: string) => {
        setDraftOverrides((prev) =>
            (prev ?? overrides).filter((o) => o.agent_name !== agentName)
        );
    }, [overrides]);

    const handleSaveAll = useCallback(async () => {
        setSaveError(null);
        setSaveSuccess(false);
        const toSave = displayOverrides.map((o): AgentOverrideUpdate => ({
            agent_name: o.agent_name,
            override_tier: o.override_tier as TierName | null,
            primary_model_id: o.primary_model_id,
            fallback_model_ids: o.fallback_model_ids,
            forbid_local: o.forbid_local,
            forbid_fallback: o.forbid_fallback,
            enabled: o.enabled,
            notes: o.notes,
        }));
        try {
            await saveOverrides(toSave);
            setDraftOverrides(null); // Clear draft — server is now source of truth
            setSaveSuccess(true);
            setTimeout(() => setSaveSuccess(false), 3000);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            setSaveError(msg);
        }
    }, [displayOverrides, saveOverrides]);

    const handleDiscard = useCallback(() => {
        setDraftOverrides(null);
        setSaveError(null);
        setSaveSuccess(false);
        setShowNewForm(false);
    }, []);

    const hasDraft = draftOverrides !== null;

    // ── Render ────────────────────────────────────────────────────────

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-[300px]">
                <RefreshCw size={20} className="animate-spin text-primary mr-2" />
                <span className="text-sm text-on-surface-variant/60">載入 Agent 覆寫設定…</span>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="p-2 bg-secondary/10 rounded-xl text-secondary">
                        <Bot size={18} />
                    </div>
                    <div>
                        <h3 className="text-sm font-bold">Agent 覆寫設定</h3>
                        <p className="text-xs text-on-surface-variant/50">
                            為特定 Agent 覆寫 Tier 綁定，指定專屬模型鏈
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={reload}
                        disabled={isLoading}
                        className="p-2 rounded-xl text-on-surface-variant/50 hover:text-primary hover:bg-primary/10 transition-colors"
                        title="重新載入"
                    >
                        <RefreshCw size={14} className={isLoading ? "animate-spin" : ""} />
                    </button>
                    <button
                        onClick={() => setShowNewForm(true)}
                        disabled={showNewForm}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-xl bg-primary text-on-primary hover:bg-primary/90 transition-colors disabled:opacity-50"
                    >
                        <Plus size={12} />
                        新增覆寫
                    </button>
                </div>
            </div>

            {/* Error banner */}
            {(error || saveError) && (
                <div className="flex items-start gap-2 p-3 bg-error/10 border border-error/20 rounded-xl text-error text-xs">
                    <AlertCircle size={14} className="mt-0.5 shrink-0" />
                    <span>{error || saveError}</span>
                </div>
            )}

            {/* Success banner */}
            {saveSuccess && (
                <div className="flex items-center gap-2 p-3 bg-green-500/10 border border-green-500/20 rounded-xl text-green-600 text-xs">
                    <span>✓ Agent 覆寫已儲存</span>
                </div>
            )}

            {/* Table */}
            <div className="overflow-x-auto rounded-2xl border border-outline-variant/10">
                <table className="w-full text-sm">
                    <thead>
                        <tr className="bg-surface-container border-b border-outline-variant/10">
                            <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-on-surface-variant/50">
                                Agent
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-on-surface-variant/50">
                                Tier 覆寫
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-on-surface-variant/50">
                                主 Model
                            </th>
                            <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-on-surface-variant/50">
                                禁本地
                            </th>
                            <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-on-surface-variant/50">
                                禁 Fallback
                            </th>
                            <th className="px-4 py-3 text-center text-xs font-bold uppercase tracking-wider text-on-surface-variant/50">
                                啟用
                            </th>
                            <th className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-on-surface-variant/50">
                                操作
                            </th>
                        </tr>
                    </thead>
                    <tbody>
                        {/* New override form row */}
                        {showNewForm && (
                            <NewOverrideForm
                                models={models}
                                onAdd={handleAddNew}
                                onCancel={() => setShowNewForm(false)}
                            />
                        )}

                        {/* Existing overrides */}
                        {displayOverrides.length === 0 && !showNewForm ? (
                            <tr>
                                <td colSpan={7} className="px-4 py-12 text-center">
                                    <div className="flex flex-col items-center gap-3 text-on-surface-variant/40">
                                        <Bot size={32} />
                                        <div>
                                            <p className="text-sm font-medium">尚無 Agent 覆寫設定</p>
                                            <p className="text-xs mt-1">
                                                未列出的 Agent 使用 Tier 預設鏈（Tab C）
                                            </p>
                                        </div>
                                    </div>
                                </td>
                            </tr>
                        ) : (
                            displayOverrides.map((override) => (
                                <AgentOverrideRow
                                    key={override.id}
                                    override={override}
                                    models={models}
                                    onSave={handleRowSave}
                                    onDelete={handleDelete}
                                />
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Info note */}
            <p className="text-xs text-on-surface-variant/40 px-1">
                💡 未列出的 Agent 使用 Tier 預設鏈（Tab C 設定）。
                設定 Override Tier 時，主 Model 選項將被停用（繼承該 Tier 的鏈）。
            </p>

            {/* Footer actions */}
            <div className="flex items-center justify-end gap-3 pt-2 border-t border-outline-variant/10">
                {hasDraft && (
                    <button
                        onClick={handleDiscard}
                        className="px-4 py-2 text-xs rounded-xl border border-outline-variant/30 text-on-surface-variant hover:bg-surface-container transition-colors"
                    >
                        捨棄變更
                    </button>
                )}
                <button
                    onClick={handleSaveAll}
                    disabled={isSaving || !hasDraft}
                    className="flex items-center gap-2 px-4 py-2 text-xs rounded-xl bg-primary text-on-primary hover:bg-primary/90 transition-colors disabled:opacity-50"
                >
                    {isSaving ? (
                        <RefreshCw size={12} className="animate-spin" />
                    ) : (
                        <Save size={12} />
                    )}
                    {isSaving ? "儲存中…" : "儲存 Agent 覆寫"}
                </button>
            </div>
        </div>
    );
}
