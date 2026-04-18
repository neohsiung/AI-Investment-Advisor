"use client";

import React from "react";
import { Plus, X, DollarSign } from "lucide-react";
import { ModelSelect } from "./ModelSelect";
import type { TierBinding, TierName, LLMModel } from "../domain/types";
import { TIER_DESCRIPTIONS } from "../domain/types";

interface TierBindingCardProps {
    /** The tier this card represents */
    tier: TierName;
    /** Current binding state (may be undefined if not yet configured) */
    binding: TierBinding | undefined;
    /** All available models for the select dropdowns */
    models: LLMModel[];
    /** Called when the user changes the primary model */
    onPrimaryChange: (tier: TierName, modelId: string) => void;
    /** Called when the user changes a fallback model */
    onFallbackChange: (tier: TierName, index: number, modelId: string) => void;
    /** Called when the user adds a new fallback slot */
    onFallbackAdd: (tier: TierName) => void;
    /** Called when the user removes a fallback slot */
    onFallbackRemove: (tier: TierName, index: number) => void;
    /** Validation errors for this tier (from 422 response) */
    errors?: Array<{ field: string; message: string }>;
}

const MAX_FALLBACKS = 4;

/** Format estimated daily cost */
function formatDailyCost(cost: number | null): string {
    if (cost === null || cost === undefined) return "—";
    if (cost === 0) return "$0.00 / day";
    if (cost < 0.01) return `$${cost.toFixed(4)} / day`;
    return `$${cost.toFixed(2)} / day`;
}

/** Tier colour accent */
const TIER_COLOURS: Record<TierName, string> = {
    nano: "border-l-emerald-400",
    fast: "border-l-blue-400",
    smart: "border-l-violet-400",
    advanced: "border-l-amber-400",
};

/**
 * TierBindingCard — Single tier card with primary model + fallback chain editor.
 */
export function TierBindingCard({
    tier,
    binding,
    models,
    onPrimaryChange,
    onFallbackChange,
    onFallbackAdd,
    onFallbackRemove,
    errors = [],
}: TierBindingCardProps) {
    const info = TIER_DESCRIPTIONS[tier];
    const primaryModelId = binding?.primary_model_id ?? "";
    const fallbackIds = binding?.fallback_model_ids ?? [];
    const estimatedCost = binding?.estimated_daily_cost ?? null;

    // All model IDs already in the chain (to disable duplicates)
    const usedIds = [primaryModelId, ...fallbackIds].filter(Boolean);

    // Find errors for specific fields
    const primaryError = errors.find((e) => e.field === "primary_model_id");
    const fallbackErrors = (idx: number) =>
        errors.find((e) => e.field === `fallback_model_ids[${idx}]`);
    const chainError = errors.find((e) => e.field === "fallback_model_ids");

    return (
        <div
            className={[
                "rounded-2xl border border-outline-variant/20 bg-surface-container",
                "border-l-4 p-5 space-y-4",
                TIER_COLOURS[tier],
            ].join(" ")}
        >
            {/* Header */}
            <div className="flex items-start justify-between gap-4">
                <div>
                    <div className="flex items-center gap-2">
                        <h3 className="text-base font-bold tracking-tight capitalize">
                            {info.label}
                        </h3>
                        <span className="text-xs font-mono text-on-surface-variant/50 uppercase">
                            {tier}
                        </span>
                    </div>
                    <p className="text-xs text-on-surface-variant/60 mt-0.5 max-w-sm">
                        {info.description}
                    </p>
                </div>
                {/* Estimated daily cost */}
                <div className="flex items-center gap-1 text-xs text-on-surface-variant/50 shrink-0">
                    <DollarSign size={12} />
                    <span>{formatDailyCost(estimatedCost)}</span>
                </div>
            </div>

            {/* Primary Model */}
            <div className="space-y-1">
                <label className="text-xs font-semibold text-on-surface-variant/70 uppercase tracking-wide">
                    Primary Model
                </label>
                <ModelSelect
                    models={models}
                    value={primaryModelId}
                    onChange={(id) => onPrimaryChange(tier, id)}
                    disabledIds={fallbackIds}
                    placeholder="— 選擇主模型 —"
                    className={primaryError ? "border-red-400 ring-1 ring-red-400" : ""}
                />
                {primaryError && (
                    <p className="text-xs text-red-500">{primaryError.message}</p>
                )}
            </div>

            {/* Fallback Chain */}
            <div className="space-y-2">
                <label className="text-xs font-semibold text-on-surface-variant/70 uppercase tracking-wide">
                    Fallback 鏈（最多 {MAX_FALLBACKS} 個）
                </label>

                {fallbackIds.length === 0 && (
                    <p className="text-xs text-on-surface-variant/40 italic">
                        尚未設定 Fallback — 主模型失敗時將直接拋出錯誤
                    </p>
                )}

                {fallbackIds.map((fid, idx) => {
                    const fbError = fallbackErrors(idx);
                    return (
                        <div key={idx} className="flex items-center gap-2">
                            <span className="text-xs text-on-surface-variant/40 w-4 shrink-0">
                                {idx + 1}.
                            </span>
                            <div className="flex-1">
                                <ModelSelect
                                    models={models}
                                    value={fid}
                                    onChange={(id) => onFallbackChange(tier, idx, id)}
                                    disabledIds={usedIds.filter((id) => id !== fid)}
                                    placeholder="— 選擇 Fallback 模型 —"
                                    className={fbError ? "border-red-400 ring-1 ring-red-400" : ""}
                                />
                                {fbError && (
                                    <p className="text-xs text-red-500 mt-0.5">{fbError.message}</p>
                                )}
                            </div>
                            <button
                                type="button"
                                onClick={() => onFallbackRemove(tier, idx)}
                                className="p-1 rounded-lg text-on-surface-variant/40 hover:text-red-500 hover:bg-red-50 transition-colors"
                                title="移除此 Fallback"
                            >
                                <X size={14} />
                            </button>
                        </div>
                    );
                })}

                {chainError && (
                    <p className="text-xs text-red-500">{chainError.message}</p>
                )}

                {fallbackIds.length < MAX_FALLBACKS && (
                    <button
                        type="button"
                        onClick={() => onFallbackAdd(tier)}
                        className="flex items-center gap-1.5 text-xs text-primary hover:text-primary/80 transition-colors"
                    >
                        <Plus size={12} />
                        新增 Fallback
                    </button>
                )}
            </div>
        </div>
    );
}
