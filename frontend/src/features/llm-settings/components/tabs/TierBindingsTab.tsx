"use client";

import React, { useCallback, useEffect, useState } from "react";
import { Save, RefreshCw, AlertCircle, CheckCircle2, ExternalLink } from "lucide-react";
import { TierBindingCard } from "../TierBindingCard";
import { useTierBindings, saveTierBindings } from "../../use-cases/useTierBindings";
import { useModels } from "../../use-cases/useModels";
import type { TierName, TierBinding, TierBindingUpdate } from "../../domain/types";

const TIER_ORDER: TierName[] = ["nano", "fast", "smart", "advanced"];

interface ValidationError {
    tier: string;
    field: string;
    message: string;
}

/**
 * TierBindingsTab — Tab C: Manage Tier → Model bindings.
 *
 * Shows 4 TierBindingCard components (nano/fast/smart/advanced).
 * User can set primary model + fallback chain for each tier.
 * "Save All Tiers" calls PUT /tiers; 422 errors shown inline.
 */
export function TierBindingsTab() {
    const { bindings, bindingsByTier, isLoading: tiersLoading, refresh } = useTierBindings();
    const { models, isLoading: modelsLoading } = useModels();

    // Local draft state — keyed by tier
    const [draft, setDraft] = useState<Partial<Record<TierName, TierBinding>>>({});
    const [isSaving, setIsSaving] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const [validationErrors, setValidationErrors] = useState<ValidationError[]>([]);
    const [globalError, setGlobalError] = useState<string | null>(null);

    // Initialise draft from server data
    useEffect(() => {
        if (bindings.length > 0) {
            const initial: Partial<Record<TierName, TierBinding>> = {};
            for (const b of bindings) {
                initial[b.tier as TierName] = { ...b };
            }
            setDraft(initial);
        }
    }, [bindings]);

    // ── Handlers ──────────────────────────────────────────────────────

    const handlePrimaryChange = useCallback((tier: TierName, modelId: string) => {
        setDraft((prev) => ({
            ...prev,
            [tier]: {
                ...(prev[tier] ?? {
                    tier,
                    primary_model_id: "",
                    primary_model: null,
                    fallback_model_ids: [],
                    fallback_models: [],
                    per_candidate_config: {},
                    budget_aware: true,
                    estimated_daily_cost: null,
                }),
                primary_model_id: modelId,
            } as TierBinding,
        }));
        setSaveSuccess(false);
        setValidationErrors((prev) => prev.filter((e) => e.tier !== tier || e.field !== "primary_model_id"));
    }, []);

    const handleFallbackChange = useCallback((tier: TierName, index: number, modelId: string) => {
        setDraft((prev) => {
            const current = prev[tier];
            if (!current) return prev;
            const newFallbacks = [...current.fallback_model_ids];
            newFallbacks[index] = modelId;
            return {
                ...prev,
                [tier]: { ...current, fallback_model_ids: newFallbacks },
            };
        });
        setSaveSuccess(false);
        setValidationErrors((prev) =>
            prev.filter((e) => e.tier !== tier || e.field !== `fallback_model_ids[${index}]`)
        );
    }, []);

    const handleFallbackAdd = useCallback((tier: TierName) => {
        setDraft((prev) => {
            const current = prev[tier];
            if (!current) return prev;
            if (current.fallback_model_ids.length >= 4) return prev;
            return {
                ...prev,
                [tier]: {
                    ...current,
                    fallback_model_ids: [...current.fallback_model_ids, ""],
                },
            };
        });
    }, []);

    const handleFallbackRemove = useCallback((tier: TierName, index: number) => {
        setDraft((prev) => {
            const current = prev[tier];
            if (!current) return prev;
            const newFallbacks = current.fallback_model_ids.filter((_, i) => i !== index);
            return {
                ...prev,
                [tier]: { ...current, fallback_model_ids: newFallbacks },
            };
        });
        setSaveSuccess(false);
    }, []);

    // ── Save ──────────────────────────────────────────────────────────

    const handleSave = async () => {
        setIsSaving(true);
        setSaveSuccess(false);
        setValidationErrors([]);
        setGlobalError(null);

        // Build update payload — only include tiers with a primary model set
        const updates: TierBindingUpdate[] = TIER_ORDER.flatMap((tier) => {
            const d = draft[tier];
            if (!d || !d.primary_model_id) return [];
            const update: TierBindingUpdate = {
                tier,
                primary_model_id: d.primary_model_id,
                fallback_model_ids: d.fallback_model_ids.filter(Boolean),
                per_candidate_config: d.per_candidate_config ?? {},
                budget_aware: d.budget_aware ?? true,
            };
            return [update];
        });

        if (updates.length === 0) {
            setGlobalError("請至少為一個 Tier 設定主模型");
            setIsSaving(false);
            return;
        }

        try {
            await saveTierBindings({ bindings: updates });
            setSaveSuccess(true);
            await refresh();
        } catch (err: unknown) {
            // Handle 422 validation errors
            const anyErr = err as { response?: { data?: { detail?: { errors?: ValidationError[] } } } };
            const detail = anyErr?.response?.data?.detail;
            if (detail && typeof detail === "object" && "errors" in detail) {
                const errors = (detail as { errors: ValidationError[] }).errors;
                setValidationErrors(errors ?? []);
            } else {
                setGlobalError(
                    err instanceof Error ? err.message : "儲存失敗，請稍後再試"
                );
            }
        } finally {
            setIsSaving(false);
        }
    };

    // ── Render ────────────────────────────────────────────────────────

    const isLoading = tiersLoading || modelsLoading;

    if (isLoading) {
        return (
            <div className="flex items-center justify-center min-h-[300px]">
                <RefreshCw size={20} className="animate-spin text-primary/50" />
                <span className="ml-2 text-sm text-on-surface-variant/50">載入中…</span>
            </div>
        );
    }

    if (models.length === 0) {
        return (
            <div className="flex flex-col items-center justify-center min-h-[300px] space-y-4 text-center">
                <AlertCircle size={32} className="text-amber-400" />
                <div>
                    <p className="font-semibold">尚未設定任何 Model</p>
                    <p className="text-sm text-on-surface-variant/60 mt-1">
                        請先到{" "}
                        <span className="font-bold text-primary">Models</span>{" "}
                        Tab 新增或 Discover 模型，再回此頁設定 Tier 綁定。
                    </p>
                </div>
                <a
                    href="#models"
                    className="flex items-center gap-1 text-sm text-primary hover:underline"
                >
                    前往 Models Tab <ExternalLink size={12} />
                </a>
            </div>
        );
    }

    return (
        <div className="space-y-6">
            {/* Page header */}
            <div>
                <h2 className="text-lg font-bold">Tier Bindings</h2>
                <p className="text-sm text-on-surface-variant/60 mt-0.5">
                    為 4 個 Tier 設定主模型與 Fallback 鏈。下拉選單只能從已建立的 Models 中選擇。
                </p>
            </div>

            {/* Global error */}
            {globalError && (
                <div className="flex items-start gap-2 rounded-xl bg-red-50 border border-red-200 px-4 py-3 text-sm text-red-700">
                    <AlertCircle size={16} className="shrink-0 mt-0.5" />
                    <span>{globalError}</span>
                </div>
            )}

            {/* Success banner */}
            {saveSuccess && (
                <div className="flex items-center gap-2 rounded-xl bg-emerald-50 border border-emerald-200 px-4 py-3 text-sm text-emerald-700">
                    <CheckCircle2 size={16} />
                    <span>Tier 綁定已儲存成功</span>
                </div>
            )}

            {/* Tier cards */}
            <div className="space-y-4">
                {TIER_ORDER.map((tier) => {
                    const tierErrors = validationErrors.filter((e) => e.tier === tier);
                    return (
                        <TierBindingCard
                            key={tier}
                            tier={tier}
                            binding={draft[tier]}
                            models={models}
                            onPrimaryChange={handlePrimaryChange}
                            onFallbackChange={handleFallbackChange}
                            onFallbackAdd={handleFallbackAdd}
                            onFallbackRemove={handleFallbackRemove}
                            errors={tierErrors}
                        />
                    );
                })}
            </div>

            {/* Footer hint */}
            <p className="text-xs text-on-surface-variant/40 text-center">
                💡 找不到想要的模型？請先到{" "}
                <span className="font-bold text-primary">Models</span>{" "}
                Tab 新增或 Discover
            </p>

            {/* Save button */}
            <div className="flex justify-end pt-2 border-t border-outline-variant/10">
                <button
                    type="button"
                    onClick={handleSave}
                    disabled={isSaving}
                    className={[
                        "flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-semibold",
                        "bg-primary text-on-primary",
                        "hover:bg-primary/90 active:scale-95 transition-all",
                        "disabled:opacity-50 disabled:cursor-not-allowed",
                    ].join(" ")}
                >
                    {isSaving ? (
                        <RefreshCw size={14} className="animate-spin" />
                    ) : (
                        <Save size={14} />
                    )}
                    {isSaving ? "儲存中…" : "Save All Tiers"}
                </button>
            </div>
        </div>
    );
}
