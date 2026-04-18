"use client";

/**
 * AgentOverrideRow — Single row in the Agent Overrides table.
 *
 * Displays agent_name / override_tier / primary_model / forbid_local /
 * forbid_fallback / enabled toggle, with inline edit and delete actions.
 */

import React, { useState } from "react";
import { Pencil, Trash2, Check, X, ChevronDown } from "lucide-react";
import type {
    AgentOverride,
    AgentOverrideUpdate,
    LLMModel,
    TierName,
} from "../domain/types";
import { KNOWN_AGENT_NAMES, AGENT_DISPLAY_NAMES } from "../domain/types";

interface AgentOverrideRowProps {
    override: AgentOverride;
    models: LLMModel[];
    onSave: (update: AgentOverrideUpdate) => Promise<void>;
    onDelete: (agentName: string) => void;
}

const TIER_OPTIONS: Array<{ value: TierName; label: string }> = [
    { value: "nano", label: "Nano" },
    { value: "fast", label: "Fast" },
    { value: "smart", label: "Smart" },
    { value: "advanced", label: "Advanced" },
];

/** Format model display for table cell */
function modelLabel(model: AgentOverride["primary_model"]): string {
    if (!model) return "—";
    return `${model.provider_code} / ${model.model_code}`;
}

export function AgentOverrideRow({
    override,
    models,
    onSave,
    onDelete,
}: AgentOverrideRowProps) {
    const [isEditing, setIsEditing] = useState(false);
    const [isSaving, setIsSaving] = useState(false);

    // Edit form state
    const [agentName, setAgentName] = useState(override.agent_name);
    const [overrideTier, setOverrideTier] = useState<TierName | "">(
        (override.override_tier as TierName) ?? ""
    );
    const [primaryModelId, setPrimaryModelId] = useState(
        override.primary_model_id ?? ""
    );
    const [forbidLocal, setForbidLocal] = useState(override.forbid_local);
    const [forbidFallback, setForbidFallback] = useState(override.forbid_fallback);
    const [enabled, setEnabled] = useState(override.enabled);

    const handleEdit = () => {
        // Reset form to current values
        setAgentName(override.agent_name);
        setOverrideTier((override.override_tier as TierName) ?? "");
        setPrimaryModelId(override.primary_model_id ?? "");
        setForbidLocal(override.forbid_local);
        setForbidFallback(override.forbid_fallback);
        setEnabled(override.enabled);
        setIsEditing(true);
    };

    const handleCancel = () => setIsEditing(false);

    const handleSave = async () => {
        setIsSaving(true);
        try {
            await onSave({
                agent_name: agentName,
                override_tier: overrideTier || null,
                primary_model_id: primaryModelId || null,
                forbid_local: forbidLocal,
                forbid_fallback: forbidFallback,
                enabled,
            });
            setIsEditing(false);
        } finally {
            setIsSaving(false);
        }
    };

    if (isEditing) {
        return (
            <tr className="bg-surface-container-high/30 border-b border-outline-variant/10">
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
                        {TIER_OPTIONS.map((t) => (
                            <option key={t.value} value={t.value}>
                                {t.label}
                            </option>
                        ))}
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

                {/* Enabled */}
                <td className="px-4 py-3 text-center">
                    <input
                        type="checkbox"
                        checked={enabled}
                        onChange={(e) => setEnabled(e.target.checked)}
                        className="w-4 h-4 accent-primary"
                    />
                </td>

                {/* Actions */}
                <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                        <button
                            onClick={handleSave}
                            disabled={isSaving}
                            className="p-1.5 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
                            title="儲存"
                        >
                            <Check size={14} />
                        </button>
                        <button
                            onClick={handleCancel}
                            className="p-1.5 rounded-lg bg-error/10 text-error hover:bg-error/20 transition-colors"
                            title="取消"
                        >
                            <X size={14} />
                        </button>
                    </div>
                </td>
            </tr>
        );
    }

    // Read-only row
    return (
        <tr className="border-b border-outline-variant/10 hover:bg-surface-container/30 transition-colors">
            {/* Agent Name */}
            <td className="px-4 py-3">
                <div className="flex flex-col">
                    <span className="text-sm font-medium">
                        {AGENT_DISPLAY_NAMES[override.agent_name as keyof typeof AGENT_DISPLAY_NAMES] ?? override.agent_name}
                    </span>
                    <span className="text-xs text-on-surface-variant/50 font-mono">
                        {override.agent_name}
                    </span>
                </div>
            </td>

            {/* Override Tier */}
            <td className="px-4 py-3">
                {override.override_tier ? (
                    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-primary/10 text-primary">
                        {override.override_tier}
                    </span>
                ) : (
                    <span className="text-xs text-on-surface-variant/40">—</span>
                )}
            </td>

            {/* Primary Model */}
            <td className="px-4 py-3">
                <span className="text-xs font-mono text-on-surface-variant/70">
                    {modelLabel(override.primary_model)}
                </span>
            </td>

            {/* Forbid Local */}
            <td className="px-4 py-3 text-center">
                {override.forbid_local ? (
                    <span className="text-error text-sm" title="禁止本地模型">🚫</span>
                ) : (
                    <span className="text-on-surface-variant/30 text-sm">✓</span>
                )}
            </td>

            {/* Forbid Fallback */}
            <td className="px-4 py-3 text-center">
                {override.forbid_fallback ? (
                    <span className="text-warning text-sm" title="禁止 Fallback">⛔</span>
                ) : (
                    <span className="text-on-surface-variant/30 text-sm">✓</span>
                )}
            </td>

            {/* Enabled */}
            <td className="px-4 py-3 text-center">
                <span
                    className={`inline-block w-2 h-2 rounded-full ${override.enabled ? "bg-green-400" : "bg-red-400"
                        }`}
                    title={override.enabled ? "啟用" : "停用"}
                />
            </td>

            {/* Actions */}
            <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                    <button
                        onClick={handleEdit}
                        className="p-1.5 rounded-lg text-on-surface-variant/50 hover:text-primary hover:bg-primary/10 transition-colors"
                        title="編輯"
                    >
                        <Pencil size={14} />
                    </button>
                    <button
                        onClick={() => onDelete(override.agent_name)}
                        className="p-1.5 rounded-lg text-on-surface-variant/50 hover:text-error hover:bg-error/10 transition-colors"
                        title="刪除"
                    >
                        <Trash2 size={14} />
                    </button>
                </div>
            </td>
        </tr>
    );
}
