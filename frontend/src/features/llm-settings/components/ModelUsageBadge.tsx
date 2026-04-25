"use client";

import React from "react";
import { cn } from "@/lib/utils";
import { useModelUsages } from "../use-cases/useModels";

interface ModelUsageBadgeProps {
    modelId: string;
    usagesCount?: number; // pre-fetched count from model list
    className?: string;
}

export function ModelUsageBadge({ modelId, usagesCount, className }: ModelUsageBadgeProps) {
    // Use pre-fetched count if available, otherwise show the count from the model
    const count = usagesCount ?? 0;

    if (count === 0) {
        return (
            <span className={cn("text-[10px] text-on-surface-variant/40", className)}>
                未引用
            </span>
        );
    }

    return (
        <span
            className={cn(
                "inline-flex items-center px-2 py-0.5 rounded-lg text-[10px] font-bold bg-primary/10 text-primary border border-primary/20",
                className
            )}
            title={`被 ${count} 個 Tier/Agent 引用`}
        >
            {count} 引用
        </span>
    );
}

// ─── On-demand variant (fetches usages) ──────────────────────────────────────

interface ModelUsageBadgeOnDemandProps {
    modelId: string;
    className?: string;
}

export function ModelUsageBadgeOnDemand({ modelId, className }: ModelUsageBadgeOnDemandProps) {
    const { usages, isLoading } = useModelUsages(modelId);

    if (isLoading) {
        return <span className={cn("text-[10px] text-on-surface-variant/30", className)}>...</span>;
    }

    const count = usages?.total_references ?? 0;

    if (count === 0) {
        return (
            <span className={cn("text-[10px] text-on-surface-variant/40", className)}>
                未引用
            </span>
        );
    }

    return (
        <span
            className={cn(
                "inline-flex items-center px-2 py-0.5 rounded-lg text-[10px] font-bold bg-primary/10 text-primary border border-primary/20",
                className
            )}
            title={`被 ${count} 個 Tier/Agent 引用`}
        >
            {count} 引用
        </span>
    );
}
