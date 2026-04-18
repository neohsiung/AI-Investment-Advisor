"use client";

import React, { useState } from "react";
import { Edit2, Trash2, Zap, Loader2, AlertTriangle, Server } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LLMProvider, ProviderUsagesResponse } from "../domain/types";
import { StatusBadge } from "./StatusBadge";
import {
    testProviderMutation,
    deleteProviderMutation,
    getProviderUsagesMutation,
} from "../use-cases/useProviders";

interface ProviderCardProps {
    provider: LLMProvider;
    onEdit: (provider: LLMProvider) => void;
    onDeleted: () => void;
}

export function ProviderCard({ provider, onEdit, onDeleted }: ProviderCardProps) {
    const [isTesting, setIsTesting] = useState(false);
    const [testResult, setTestResult] = useState<{ success: boolean; msg: string } | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);
    const [deleteModal, setDeleteModal] = useState<ProviderUsagesResponse | null>(null);
    const [deleteError, setDeleteError] = useState<string | null>(null);

    // ─── Test Connection ────────────────────────────────────────────────────────
    const handleTest = async () => {
        setIsTesting(true);
        setTestResult(null);
        try {
            const result = await testProviderMutation(provider.id);
            setTestResult({
                success: result.success,
                msg: result.success
                    ? `連線成功 (${result.latency_ms ?? "?"}ms)`
                    : result.error ?? "連線失敗",
            });
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "測試失敗";
            setTestResult({ success: false, msg });
        } finally {
            setIsTesting(false);
            setTimeout(() => setTestResult(null), 5000);
        }
    };

    // ─── Delete ─────────────────────────────────────────────────────────────────
    const handleDeleteClick = async () => {
        setDeleteError(null);
        // Pre-check usages
        try {
            const usages = await getProviderUsagesMutation(provider.id);
            if (!usages.can_delete) {
                setDeleteModal(usages);
                return;
            }
        } catch {
            // If usages endpoint not available, proceed with delete attempt
        }
        await confirmDelete();
    };

    const confirmDelete = async () => {
        setIsDeleting(true);
        setDeleteError(null);
        try {
            await deleteProviderMutation(provider.id);
            setDeleteModal(null);
            onDeleted();
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "刪除失敗";
            setDeleteError(msg);
        } finally {
            setIsDeleting(false);
        }
    };

    // ─── Health dot color ────────────────────────────────────────────────────────
    const healthDot =
        provider.health_status === "healthy"
            ? "bg-green-500"
            : provider.health_status === "unhealthy"
                ? "bg-red-500"
                : "bg-gray-400";

    const isOllama = provider.provider_code === "ollama";

    return (
        <>
            <div
                className={cn(
                    "bg-surface-container p-6 rounded-[24px] border transition-all",
                    provider.enabled
                        ? "border-outline-variant/10"
                        : "border-outline-variant/5 opacity-60"
                )}
            >
                {/* Header row */}
                <div className="flex items-start justify-between gap-4 mb-4">
                    <div className="flex items-center gap-3 min-w-0">
                        <span className={cn("w-2.5 h-2.5 rounded-full flex-shrink-0 mt-0.5", healthDot)} />
                        <div className="min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                                <h3 className="font-bold text-sm truncate">{provider.display_name}</h3>
                                <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-lg bg-surface-container-high text-on-surface-variant border border-outline-variant/20 flex-shrink-0">
                                    {provider.provider_code}
                                </span>
                                {!provider.enabled && (
                                    <span className="text-[10px] font-bold px-2 py-0.5 rounded-lg bg-error/10 text-error border border-error/20">
                                        已停用
                                    </span>
                                )}
                            </div>
                            <StatusBadge
                                status={provider.health_status}
                                lastCheckedAt={provider.last_checked_at}
                                className="mt-1"
                            />
                        </div>
                    </div>

                    {/* Action buttons */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                        <button
                            onClick={handleTest}
                            disabled={isTesting}
                            title="Test Connection"
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-outline-variant/30 text-[11px] font-bold hover:bg-surface-container-high transition-all disabled:opacity-50"
                        >
                            {isTesting ? (
                                <Loader2 size={12} className="animate-spin" />
                            ) : (
                                <Zap size={12} />
                            )}
                            Test
                        </button>
                        <button
                            onClick={() => onEdit(provider)}
                            title="Edit"
                            className="p-2 rounded-xl hover:bg-surface-container-high transition-colors text-on-surface-variant"
                        >
                            <Edit2 size={14} />
                        </button>
                        <button
                            onClick={handleDeleteClick}
                            disabled={isDeleting}
                            title="Delete"
                            className="p-2 rounded-xl hover:bg-error/10 transition-colors text-on-surface-variant hover:text-error disabled:opacity-50"
                        >
                            {isDeleting ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                        </button>
                    </div>
                </div>

                {/* Details */}
                <div className="space-y-1.5 text-[11px] text-on-surface-variant/70">
                    {provider.base_url && (
                        <div className="flex items-center gap-2">
                            <Server size={11} className="flex-shrink-0" />
                            <span className="font-mono truncate">{provider.base_url}</span>
                        </div>
                    )}
                    {provider.api_key_masked && (
                        <div className="flex items-center gap-2">
                            <span className="font-mono tracking-widest">{provider.api_key_masked}</span>
                        </div>
                    )}
                    <div className="flex items-center gap-2">
                        <span className="text-on-surface-variant/50">Models:</span>
                        <span className="font-bold text-on-surface-variant">{provider.model_count} 個</span>
                    </div>
                </div>

                {/* Ollama hint */}
                {isOllama && (
                    <div className="mt-4 bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2 text-[11px] text-amber-700 dark:text-amber-400">
                        💡 本地模型，確保 Ollama 服務已啟動（<code>ollama serve</code>），並透過 Models Tab 的 Discover 按鈕匯入已 pull 的模型
                    </div>
                )}

                {/* Test result feedback */}
                {testResult && (
                    <div
                        className={cn(
                            "mt-3 px-3 py-2 rounded-xl text-[11px] font-medium border",
                            testResult.success
                                ? "bg-green-500/10 border-green-500/20 text-green-700 dark:text-green-400"
                                : "bg-error/10 border-error/20 text-error"
                        )}
                    >
                        {testResult.success ? "✓" : "✗"} {testResult.msg}
                    </div>
                )}

                {/* Delete error */}
                {deleteError && (
                    <div className="mt-3 px-3 py-2 rounded-xl text-[11px] font-medium border bg-error/10 border-error/20 text-error">
                        {deleteError}
                    </div>
                )}
            </div>

            {/* Delete conflict modal */}
            {deleteModal && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
                    <div className="bg-surface-container-low rounded-3xl border border-outline-variant/20 shadow-2xl w-full max-w-md mx-4 p-8">
                        <div className="flex items-center gap-3 mb-4">
                            <AlertTriangle size={20} className="text-amber-500 flex-shrink-0" />
                            <h3 className="font-bold text-base">無法直接刪除</h3>
                        </div>
                        <p className="text-sm text-on-surface-variant mb-4">
                            此 Provider 下有 <strong>{deleteModal.model_count}</strong> 個 Model，刪除前需先處理：
                        </p>
                        <ul className="space-y-1 mb-6">
                            {deleteModal.models.slice(0, 5).map((m) => (
                                <li key={m.id} className="text-xs font-mono text-on-surface-variant/70 pl-4">
                                    • {m.model_code}
                                </li>
                            ))}
                            {deleteModal.models.length > 5 && (
                                <li className="text-xs text-on-surface-variant/50 pl-4">
                                    ...及其他 {deleteModal.models.length - 5} 個
                                </li>
                            )}
                        </ul>
                        <div className="flex gap-3 justify-end">
                            <button
                                onClick={() => setDeleteModal(null)}
                                className="px-5 py-2 rounded-xl border border-outline-variant/30 text-sm font-bold hover:bg-surface-container-high transition-all"
                            >
                                取消
                            </button>
                            <button
                                onClick={() => {
                                    setDeleteModal(null);
                                    // Guide user to Models tab
                                }}
                                className="px-5 py-2 rounded-xl bg-surface-container-high text-sm font-bold hover:bg-surface-container-highest transition-all"
                            >
                                前往 Models Tab 刪除
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
