"use client";

import React, { useMemo } from "react";
import type { LLMModel } from "../domain/types";

interface ModelSelectProps {
    /** All available models (from GET /models) */
    models: LLMModel[];
    /** Currently selected model ID */
    value: string;
    /** Called when user selects a model */
    onChange: (modelId: string) => void;
    /** Model IDs already used in this chain (to disable duplicates) */
    disabledIds?: string[];
    /** Placeholder text */
    placeholder?: string;
    /** Whether the select is disabled */
    disabled?: boolean;
    /** Additional CSS classes */
    className?: string;
}

/** Format cost as a human-readable string */
function formatCost(inputCost: number | null, outputCost: number | null): string {
    if (inputCost === null && outputCost === null) return "";
    const avg = ((inputCost ?? 0) + (outputCost ?? 0)) / 2;
    if (avg === 0) return "FREE";
    if (avg < 0.001) return `$${(avg * 1000).toFixed(3)}/1K`;
    return `$${avg.toFixed(4)}/1K`;
}

/** Capability emoji chips */
function capabilityChips(model: LLMModel): string {
    const chips: string[] = [];
    if (model.capabilities.tool_calling) chips.push("⚡");
    if (model.capabilities.vision) chips.push("🖼");
    if (model.capabilities.json_mode) chips.push("📋");
    if (model.capabilities.embeddings) chips.push("🔗");
    return chips.join("");
}

/**
 * ModelSelect — A grouped <select> that shows models organised by Provider.
 * Displays capability chips and cost info in each option.
 * Disables already-selected model IDs to prevent duplicates in the chain.
 */
export function ModelSelect({
    models,
    value,
    onChange,
    disabledIds = [],
    placeholder = "— 選擇模型 —",
    disabled = false,
    className = "",
}: ModelSelectProps) {
    // Group models by provider
    const grouped = useMemo(() => {
        const map = new Map<string, { providerName: string; models: LLMModel[] }>();
        for (const m of models) {
            if (!m.enabled) continue;
            const key = m.provider_id;
            if (!map.has(key)) {
                map.set(key, {
                    providerName: m.provider_display_name,
                    models: [],
                });
            }
            map.get(key)!.models.push(m);
        }
        // Sort providers alphabetically
        return Array.from(map.entries()).sort(([, a], [, b]) =>
            a.providerName.localeCompare(b.providerName)
        );
    }, [models]);

    return (
        <select
            value={value}
            onChange={(e) => onChange(e.target.value)}
            disabled={disabled}
            className={[
                "w-full rounded-lg border border-outline-variant/30 bg-surface-container",
                "px-3 py-2 text-sm text-on-surface",
                "focus:outline-none focus:ring-2 focus:ring-primary/50",
                "disabled:opacity-50 disabled:cursor-not-allowed",
                className,
            ].join(" ")}
        >
            <option value="">{placeholder}</option>
            {grouped.map(([providerId, group]) => {
                const options = group.models.map((m) => {
                    const isDisabled = disabledIds.includes(m.id);
                    const chips = capabilityChips(m);
                    const cost = formatCost(m.input_cost_per_1k, m.output_cost_per_1k);
                    const label = [
                        m.display_name,
                        chips ? `(${chips})` : "",
                        cost ? `· ${cost}` : "",
                    ]
                        .filter(Boolean)
                        .join(" ");
                    return (
                        <option
                            key={m.id}
                            value={m.id}
                            disabled={isDisabled}
                        >
                            {isDisabled ? `✓ ${label}` : label}
                        </option>
                    );
                });
                return (
                    <optgroup key={providerId} label={`── ${group.providerName} ──`}>
                        {options}
                    </optgroup>
                );
            })}
        </select>
    );
}
