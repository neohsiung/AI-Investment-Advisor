"use client";

import React from "react";
import { cn } from "@/lib/utils";
import type { HealthStatus } from "../domain/types";

interface StatusBadgeProps {
    status: HealthStatus | null;
    latencyMs?: number | null;
    lastCheckedAt?: string | null;
    className?: string;
}

export function StatusBadge({ status, latencyMs, lastCheckedAt, className }: StatusBadgeProps) {
    const dot =
        status === "healthy" || status === "ok"
            ? "bg-green-500"
            : status === "unhealthy" || status === "error"
                ? "bg-red-500"
                : "bg-gray-400";

    const label =
        status === "healthy" || status === "ok"
            ? latencyMs != null
                ? `OK (${latencyMs}ms)`
                : "OK"
            : status === "unhealthy" || status === "error"
                ? "Unhealthy"
                : "Unknown";

    const checkedStr = lastCheckedAt
        ? new Date(lastCheckedAt).toLocaleString("zh-TW", {
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
        })
        : null;

    return (
        <div className={cn("flex items-center gap-1.5", className)}>
            <span className={cn("w-2 h-2 rounded-full flex-shrink-0", dot)} />
            <span className="text-[11px] font-medium text-on-surface-variant">
                {label}
                {checkedStr && (
                    <span className="opacity-50 ml-1">· {checkedStr}</span>
                )}
            </span>
        </div>
    );
}
