"use client";

import React, { useState } from "react";
import { Plus, RefreshCw } from "lucide-react";
import type { LLMModel } from "../../domain/types";
import { useProviders } from "../../use-cases/useProviders";
import { useModels } from "../../use-cases/useModels";
import { ModelTable } from "../ModelTable";
import { ModelFormModal } from "../ModelFormModal";

export function ModelsTab() {
    const { providers, isLoading: providersLoading, refresh: refreshProviders } = useProviders();
    const { models, isLoading: modelsLoading, error: modelsError, refresh: refreshModels } = useModels();

    const [editTarget, setEditTarget] = useState<LLMModel | null | undefined>(undefined);
    // undefined = modal closed, null = create mode, LLMModel = edit mode

    const isLoading = providersLoading || modelsLoading;

    const handleRefresh = () => {
        refreshProviders();
        refreshModels();
    };

    const openCreate = () => setEditTarget(null);
    const openEdit = (m: LLMModel) => setEditTarget(m);
    const closeModal = () => setEditTarget(undefined);

    return (
        <div className="space-y-6">
            {/* Toolbar */}
            <div className="flex items-center justify-between">
                <div>
                    <h3 className="text-lg font-bold tracking-tight">LLM Models</h3>
                    <p className="text-xs text-on-surface-variant/60 mt-0.5">
                        管理各 Provider 下的模型，支援手動新增與自動探索
                    </p>
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={handleRefresh}
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
                        手動新增 Model
                    </button>
                </div>
            </div>

            {/* Model table grouped by provider */}
            <ModelTable
                providers={providers}
                models={models}
                isLoading={isLoading}
                error={modelsError instanceof Error ? modelsError : null}
                onEdit={openEdit}
                onRefresh={handleRefresh}
            />

            {/* Create / Edit Modal */}
            {editTarget !== undefined && (
                <ModelFormModal
                    model={editTarget}
                    providers={providers}
                    onClose={closeModal}
                    onSuccess={() => {
                        handleRefresh();
                        closeModal();
                    }}
                />
            )}
        </div>
    );
}
