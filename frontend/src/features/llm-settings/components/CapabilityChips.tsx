"use client";

import React from "react";
import { cn } from "@/lib/utils";
import type { ModelCapabilities } from "../domain/types";

interface CapabilityChipsProps {
    capabilities: ModelCapabilities;
    className?: string;
}

const CHIP_DEFS: Array<{
    key: keyof ModelCapabilities;
    label: string;
    emoji: string;
    title: string;
}> = [
        { key: "tool_calling", label: "Tools", emoji: "⚡", title: "Tool Calling" },
        { key: "vision", label: "Vision", emoji: "🖼", title: "Vision / Image Input" },
        { key: "json_mode", label: "JSON", emoji: "📋", title: "JSON Mode" },
        { key: "streaming", label: "Stream", emoji: "🌊", title: "Streaming" },
        { key: "embeddings", label: "Embed", emoji: "🔗", title: "Embeddings" },
    ];

export function CapabilityChips({ capabilities, className }: CapabilityChipsProps) {
    const active = CHIP_DEFS.filter((d) => capabilities[d.key]);

    if (active.length === 0) {
        return <span className="text-[10px] text-on-surface-variant/40">—</span>;
    }

    return (
        <div className={cn("flex flex-wrap gap-1", className)}>
            {active.map((d) => (
                <span
                    key={d.key}
                    title={d.title}
                    className="text-[11px] px-1.5 py-0.5 rounded-md bg-surface-container-high text-on-surface-variant border border-outline-variant/20"
                >
                    {d.emoji}
                </span>
            ))}
        </div>
    );
}

// ─── Checkbox editor variant ──────────────────────────────────────────────────

interface CapabilityCheckboxesProps {
    value: ModelCapabilities;
    onChange: (v: ModelCapabilities) => void;
}

export function CapabilityCheckboxes({ value, onChange }: CapabilityCheckboxesProps) {
    const toggle = (key: keyof ModelCapabilities) => {
        onChange({ ...value, [key]: !value[key] });
    };

    return (
        <div className="flex flex-wrap gap-3">
            {CHIP_DEFS.map((d) => (
                <label key={d.key} className="flex items-center gap-1.5 cursor-pointer select-none">
                    <input
                        type="checkbox"
                        checked={!!value[d.key]}
                        onChange={() => toggle(d.key)}
                        className="accent-primary w-3.5 h-3.5"
                    />
                    <span className="text-xs font-medium text-on-surface-variant">
                        {d.emoji} {d.title}
                    </span>
                </label>
            ))}
        </div>
    );
}
