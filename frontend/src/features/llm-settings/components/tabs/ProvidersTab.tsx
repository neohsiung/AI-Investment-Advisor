"use client";

import React, { useState } from "react";
import { Plus, Loader2, RefreshCw, AlertCircle } from "lucide-react";
import type { LLMProvider } from "../../domain/types";
import { useProviders } from "../../use-cases/useProviders";
import { ProviderCard } from "../ProviderCard";
import { ProviderFormModal } from "../ProviderFormModal";

export function ProvidersTab() {
    const { providers, isLoading, error, refresh } = useProviders();
    const [editTarget, setEditTarget] = useState<LLMProvider | null | undefined>(undefined);
    // undefined = modal closed, null = create mode, LLMProvider = edit mode

    const openCreate = () => setEditTarget(null);
    const openEdit = (p: LLMProvider) => setEditTarget(p);
    const closeModal = () => setEditTarget(undefined);

    return (
        <div className="space-y-6">
            {/* Toolbar */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-lg font-bold tracking-tight">LLM Providers</h3>
                    <p className="text-xs text-on-surface-variant/60 mt-0.5">
                        管理 AI 供應商連線設定與 API 金鑰
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => refresh()}
                        title="重新整理"
                        className="p-2 rounded-xl hover:bg-surface-container-high transition-colors text-on-surface-variant"
                    >
                        <RefreshCw size={16} />
                    </button>
                    <button
                        onClick={openCreate}
                        className="flex items-center gap-2 px-4 py-2 bg-primary text-on-primary rounded-xl text-sm font-bold hover:opacity-90 transition-all shadow-sm shadow-primary/20"
                    >
                        <Plus size={16} />
                        新增 Provider
                    </button>
                </div>
            </div>

            {/* Loading */}
            {isLoading && (
                <div className="flex items-center justify-center py-16 opacity-50">
                    <Loader2 className="animate-spin mr-3" size={20} />
                    <span className="text-sm font-medium">載入中...</span>
                </div>
            )}

            {/* Error */}
            {error && !isLoading && (
                <div className="flex items-center gap-3 bg-error/10 border border-error/20 rounded-2xl px-5 py-4 text-sm text-error">
                    <AlertCircle size={16} className="flex-shrink-0" />
                    <span>載入失敗：{error instanceof Error ? error.message : "未知錯誤"}</span>
                    <button
                        onClick={() => refresh()}
                        className="ml-auto text-xs font-bold underline hover:no-underline"
                    >
                        重試
                    </button>
                </div>
            )}

            {/* Empty state */}
            {!isLoading && !error && providers.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 opacity-40 border-2 border-dashed border-outline-variant/30 rounded-3xl">
                    <p className="text-sm font-bold mb-2">尚無 Provider</p>
                    <p className="text-xs text-on-surface-variant">點擊「新增 Provider」開始設定</p>
                </div>
            )}

            {/* Provider cards grid */}
            {!isLoading && providers.length > 0 && (
                <div className="grid grid-cols-1 gap-4">
                    {providers.map((provider) => (
                        <ProviderCard
                            key={provider.id}
                            provider={provider}
                            onEdit={openEdit}
                            onDeleted={() => refresh()}
                        />
                    ))}
                </div>
            )}

            {/* Create / Edit Modal */}
            {editTarget !== undefined && (
                <ProviderFormModal
                    provider={editTarget}
                    onClose={closeModal}
                    onSuccess={() => {
                        refresh();
                        closeModal();
                    }}
                />
            )}
        </div>
    );
}
