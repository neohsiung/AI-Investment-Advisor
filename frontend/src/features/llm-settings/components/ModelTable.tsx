"use client";

import React, { useState } from "react";
import { Edit2, Trash2, Search, Loader2, AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LLMModel, LLMProvider, ModelUsagesResponse } from "../domain/types";
import { CapabilityChips } from "./CapabilityChips";
import { ModelUsageBadge } from "./ModelUsageBadge";
import { StatusBadge } from "./StatusBadge";
import { DiscoverModelsModal } from "./DiscoverModelsModal";
import {
    deleteModelMutation,
    getModelUsagesMutation,
} from "../use-cases/useModels";

// ─── Cost formatter ───────────────────────────────────────────────────────────

function formatCost(val: number | null): string {
    if (val == null) return "—";
    if (val === 0) return "Free";
    return `$${val.toFixed(4)}`;
}

function formatCtx(ctx: number | null): string {
    if (ctx == null) return "—";
    if (ctx >= 1000) return `${Math.round(ctx / 1000)}K`;
    return String(ctx);
}

// ─── Source badge ─────────────────────────────────────────────────────────────

function SourceBadge({ source }: { source: LLMModel["source"] }) {
    const map = {
        manual: { label: "手動", cls: "bg-blue-500/10 text-blue-700 dark:text-blue-400 border-blue-500/20" },
        auto_discovered: { label: "探索", cls: "bg-green-500/10 text-green-700 dark:text-green-400 border-green-500/20" },
        seed: { label: "Seed", cls: "bg-surface-container-high text-on-surface-variant/60 border-outline-variant/20" },
    };
    const { label, cls } = map[source] ?? map.seed;
    return (
        <span className={cn("text-[10px] px-1.5 py-0.5 rounded-md border font-bold", cls)}>
            {label}
        </span>
    );
}

// ─── Delete confirm modal ─────────────────────────────────────────────────────

interface DeleteModelModalProps {
    model: LLMModel;
    usages: ModelUsagesResponse | null;
    onConfirm: () => void;
    onDisable: () => void;
    onCancel: () => void;
    isDeleting: boolean;
}

function DeleteModelModal({
    model,
    usages,
    onConfirm,
    onDisable,
    onCancel,
    isDeleting,
}: DeleteModelModalProps) {
    const canDelete = usages?.can_delete !== false;

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div className="bg-surface-container-low rounded-3xl border border-outline-variant/20 shadow-2xl w-full max-w-md mx-4 p-8">
                <div className="flex items-center gap-3 mb-4">
                    <AlertTriangle size={20} className="text-amber-500 flex-shrink-0" />
                    <h3 className="font-bold text-base">
                        {canDelete ? "確認刪除" : "無法刪除"}
                    </h3>
                </div>

                <p className="text-sm text-on-surface-variant mb-2">
                    Model: <strong className="font-mono">{model.model_code}</strong>
                </p>

                {!canDelete && usages && (
                    <>
                        <p className="text-sm text-on-surface-variant mb-3">
                            此 Model 被 <strong>{usages.total_references}</strong> 個 Tier/Agent 引用：
                        </p>
                        <div className="bg-surface-container rounded-xl px-4 py-3 mb-4 space-y-1 max-h-32 overflow-y-auto">
                            {usages.usages.tier_bindings?.map((u, i) => (
                                <div key={i} className="text-xs font-mono text-on-surface-variant/70">
                                    Tier: {u.tier} ({u.role})
                                </div>
                            ))}
                            {usages.usages.agent_overrides?.map((u, i) => (
                                <div key={i} className="text-xs font-mono text-on-surface-variant/70">
                                    Agent: {u.agent_name} ({u.role})
                                </div>
                            ))}
                        </div>
                    </>
                )}

                <div className="flex gap-3 justify-end mt-2">
                    <button
                        onClick={onCancel}
                        className="px-5 py-2 rounded-xl border border-outline-variant/30 text-sm font-bold hover:bg-surface-container-high transition-all"
                    >
                        取消
                    </button>
                    {!canDelete && (
                        <button
                            onClick={onDisable}
                            className="px-5 py-2 rounded-xl bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-400 text-sm font-bold hover:bg-amber-500/20 transition-all"
                        >
                            改為停用
                        </button>
                    )}
                    {canDelete && (
                        <button
                            onClick={onConfirm}
                            disabled={isDeleting}
                            className="flex items-center gap-2 px-5 py-2 rounded-xl bg-error text-white text-sm font-bold hover:opacity-90 transition-all disabled:opacity-50"
                        >
                            {isDeleting && <Loader2 size={14} className="animate-spin" />}
                            確認刪除
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}

// ─── Provider group ───────────────────────────────────────────────────────────

interface ProviderGroupProps {
    provider: LLMProvider;
    models: LLMModel[];
    onEdit: (model: LLMModel) => void;
    onDeleted: () => void;
}

function ProviderGroup({ provider, models, onEdit, onDeleted }: ProviderGroupProps) {
    const [expanded, setExpanded] = useState(true);
    const [discoverOpen, setDiscoverOpen] = useState(false);
    const [deleteTarget, setDeleteTarget] = useState<LLMModel | null>(null);
    const [deleteUsages, setDeleteUsages] = useState<ModelUsagesResponse | null>(null);
    const [isDeleting, setIsDeleting] = useState(false);

    const healthDot =
        provider.health_status === "healthy"
            ? "bg-green-500"
            : provider.health_status === "unhealthy"
                ? "bg-red-500"
                : "bg-gray-400";

    const handleDeleteClick = async (model: LLMModel) => {
        setDeleteTarget(model);
        try {
            const usages = await getModelUsagesMutation(model.id);
            setDeleteUsages(usages);
        } catch {
            setDeleteUsages(null);
        }
    };

    const confirmDelete = async () => {
        if (!deleteTarget) return;
        setIsDeleting(true);
        try {
            await deleteModelMutation(deleteTarget.id);
            setDeleteTarget(null);
            setDeleteUsages(null);
            onDeleted();
        } catch {
            // error handled by mutation
        } finally {
            setIsDeleting(false);
        }
    };

    const handleDisable = async () => {
        // Disable instead of delete
        if (!deleteTarget) return;
        const { updateModelMutation } = await import("../use-cases/useModels");
        try {
            await updateModelMutation(deleteTarget.id, { enabled: false });
            setDeleteTarget(null);
            setDeleteUsages(null);
            onDeleted();
        } catch {
            // ignore
        }
    };

    return (
        <>
            <div className="bg-surface-container rounded-[24px] border border-outline-variant/10 overflow-hidden">
                {/* Group header */}
                <button
                    onClick={() => setExpanded((v) => !v)}
                    className="w-full flex items-center gap-3 px-6 py-4 hover:bg-surface-container-high transition-colors text-left"
                >
                    {expanded ? (
                        <ChevronDown size={16} className="text-on-surface-variant/50 flex-shrink-0" />
                    ) : (
                        <ChevronRight size={16} className="text-on-surface-variant/50 flex-shrink-0" />
                    )}
                    <span className={cn("w-2 h-2 rounded-full flex-shrink-0", healthDot)} />
                    <span className="font-bold text-sm">{provider.display_name}</span>
                    <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded-lg bg-surface-container-highest text-on-surface-variant/60 border border-outline-variant/20">
                        {provider.provider_code}
                    </span>
                    <span className="text-xs text-on-surface-variant/50 ml-1">
                        {models.length} 個模型
                    </span>
                    <div className="ml-auto flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
                        <button
                            onClick={() => setDiscoverOpen(true)}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-outline-variant/30 text-[11px] font-bold hover:bg-surface-container-highest transition-all"
                        >
                            🔄 Discover
                        </button>
                    </div>
                </button>

                {/* Ollama hint */}
                {expanded && provider.provider_code === "ollama" && (
                    <div className="mx-6 mb-3 bg-amber-500/10 border border-amber-500/20 rounded-xl px-3 py-2 text-[11px] text-amber-700 dark:text-amber-400">
                        💡 先 <code>ollama pull &lt;model&gt;</code> 再用 Discover 匯入
                    </div>
                )}

                {/* Models table */}
                {expanded && models.length > 0 && (
                    <div className="px-6 pb-4 overflow-x-auto">
                        <table className="w-full text-xs">
                            <thead>
                                <tr className="border-b border-outline-variant/10">
                                    <th className="text-left py-2 pr-4 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        Model Code
                                    </th>
                                    <th className="text-left py-2 pr-4 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        顯示名稱
                                    </th>
                                    <th className="text-left py-2 pr-4 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        能力
                                    </th>
                                    <th className="text-right py-2 pr-4 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        Context
                                    </th>
                                    <th className="text-right py-2 pr-4 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        Input
                                    </th>
                                    <th className="text-right py-2 pr-4 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        Output
                                    </th>
                                    <th className="text-center py-2 pr-4 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        來源
                                    </th>
                                    <th className="text-center py-2 pr-4 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        引用
                                    </th>
                                    <th className="py-2 text-[10px] font-black uppercase text-on-surface-variant/50 tracking-widest">
                                        操作
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {models.map((model) => (
                                    <tr
                                        key={model.id}
                                        className={cn(
                                            "border-b border-outline-variant/5 hover:bg-surface-container-high/50 transition-colors",
                                            !model.enabled && "opacity-50"
                                        )}
                                    >
                                        <td className="py-2.5 pr-4 font-mono font-bold text-[11px] max-w-[180px] truncate">
                                            {model.model_code}
                                        </td>
                                        <td className="py-2.5 pr-4 text-on-surface-variant max-w-[160px] truncate">
                                            {model.display_name}
                                            {!model.enabled && (
                                                <span className="ml-1 text-[9px] text-error/70">(停用)</span>
                                            )}
                                        </td>
                                        <td className="py-2.5 pr-4">
                                            <CapabilityChips capabilities={model.capabilities} />
                                        </td>
                                        <td className="py-2.5 pr-4 text-right text-on-surface-variant/70 font-mono">
                                            {formatCtx(model.context_window)}
                                        </td>
                                        <td className="py-2.5 pr-4 text-right text-on-surface-variant/70 font-mono">
                                            {formatCost(model.input_cost_per_1k)}
                                        </td>
                                        <td className="py-2.5 pr-4 text-right text-on-surface-variant/70 font-mono">
                                            {formatCost(model.output_cost_per_1k)}
                                        </td>
                                        <td className="py-2.5 pr-4 text-center">
                                            <SourceBadge source={model.source} />
                                        </td>
                                        <td className="py-2.5 pr-4 text-center">
                                            <ModelUsageBadge
                                                modelId={model.id}
                                                usagesCount={model.usages_count}
                                            />
                                        </td>
                                        <td className="py-2.5">
                                            <div className="flex items-center gap-1">
                                                <button
                                                    onClick={() => onEdit(model)}
                                                    title="編輯"
                                                    className="p-1.5 rounded-lg hover:bg-surface-container-highest transition-colors text-on-surface-variant"
                                                >
                                                    <Edit2 size={13} />
                                                </button>
                                                <button
                                                    onClick={() => handleDeleteClick(model)}
                                                    title="刪除"
                                                    className="p-1.5 rounded-lg hover:bg-error/10 transition-colors text-on-surface-variant hover:text-error"
                                                >
                                                    <Trash2 size={13} />
                                                </button>
                                            </div>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}

                {/* Empty group */}
                {expanded && models.length === 0 && (
                    <div className="px-6 pb-6 text-xs text-on-surface-variant/40 italic">
                        此 Provider 尚無 Model，點擊 Discover 探索
                    </div>
                )}
            </div>

            {/* Discover modal */}
            {discoverOpen && (
                <DiscoverModelsModal
                    provider={provider}
                    onClose={() => setDiscoverOpen(false)}
                    onImported={() => {
                        setDiscoverOpen(false);
                        onDeleted(); // reuse refresh callback
                    }}
                />
            )}

            {/* Delete confirm modal */}
            {deleteTarget && (
                <DeleteModelModal
                    model={deleteTarget}
                    usages={deleteUsages}
                    onConfirm={confirmDelete}
                    onDisable={handleDisable}
                    onCancel={() => {
                        setDeleteTarget(null);
                        setDeleteUsages(null);
                    }}
                    isDeleting={isDeleting}
                />
            )}
        </>
    );
}

// ─── Main ModelTable ──────────────────────────────────────────────────────────

interface ModelTableProps {
    providers: LLMProvider[];
    models: LLMModel[];
    isLoading: boolean;
    error: Error | null;
    onEdit: (model: LLMModel) => void;
    onRefresh: () => void;
}

export function ModelTable({
    providers,
    models,
    isLoading,
    error,
    onEdit,
    onRefresh,
}: ModelTableProps) {
    const [search, setSearch] = useState("");

    const filteredModels = search
        ? models.filter(
            (m) =>
                m.model_code.toLowerCase().includes(search.toLowerCase()) ||
                m.display_name.toLowerCase().includes(search.toLowerCase())
        )
        : models;

    // Group by provider
    const grouped = providers.map((p) => ({
        provider: p,
        models: filteredModels.filter((m) => m.provider_id === p.id),
    }));

    // Models without a matching provider (edge case)
    const orphaned = filteredModels.filter(
        (m) => !providers.find((p) => p.id === m.provider_id)
    );

    if (isLoading) {
        return (
            <div className="flex items-center justify-center py-16 opacity-50">
                <Loader2 className="animate-spin mr-3" size={20} />
                <span className="text-sm font-medium">載入中...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex items-center gap-3 bg-error/10 border border-error/20 rounded-2xl px-5 py-4 text-sm text-error">
                載入失敗：{error.message}
                <button
                    onClick={onRefresh}
                    className="ml-auto text-xs font-bold underline hover:no-underline"
                >
                    重試
                </button>
            </div>
        );
    }

    return (
        <div className="space-y-4">
            {/* Search bar */}
            <div className="relative">
                <Search
                    size={14}
                    className="absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant/40"
                />
                <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="搜尋 model_code 或顯示名稱..."
                    className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl pl-10 pr-4 py-2.5 text-sm focus:border-primary/50 transition-all outline-none"
                />
            </div>

            {/* Provider groups */}
            {grouped.map(({ provider, models: pModels }) => (
                <ProviderGroup
                    key={provider.id}
                    provider={provider}
                    models={pModels}
                    onEdit={onEdit}
                    onDeleted={onRefresh}
                />
            ))}

            {/* Orphaned models */}
            {orphaned.length > 0 && (
                <div className="bg-surface-container rounded-[24px] border border-outline-variant/10 p-6">
                    <p className="text-xs font-bold text-on-surface-variant/50 mb-3">其他 Models</p>
                    {orphaned.map((m) => (
                        <div key={m.id} className="text-xs font-mono text-on-surface-variant/60">
                            {m.model_code}
                        </div>
                    ))}
                </div>
            )}

            {/* Empty */}
            {providers.length === 0 && (
                <div className="flex flex-col items-center justify-center py-20 opacity-40 border-2 border-dashed border-outline-variant/30 rounded-3xl">
                    <p className="text-sm font-bold mb-2">尚無 Provider</p>
                    <p className="text-xs text-on-surface-variant">請先到 Providers Tab 新增 Provider</p>
                </div>
            )}
        </div>
    );
}
