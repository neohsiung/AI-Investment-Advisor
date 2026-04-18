"use client";

import React, { useState, useEffect, useCallback } from "react";
import { X, RefreshCw, Loader2, Download, CheckSquare, Square, Search } from "lucide-react";
import { cn } from "@/lib/utils";
import type { LLMProvider, DiscoveredModel } from "../domain/types";
import {
    discoverModelsMutation,
    batchImportModelsMutation,
} from "../use-cases/useModels";

interface DiscoverModelsModalProps {
    provider: LLMProvider;
    onClose: () => void;
    onImported: () => void;
}

export function DiscoverModelsModal({
    provider,
    onClose,
    onImported,
}: DiscoverModelsModalProps) {
    const [models, setModels] = useState<DiscoveredModel[]>([]);
    const [selected, setSelected] = useState<Set<string>>(new Set());
    const [isDiscovering, setIsDiscovering] = useState(false);
    const [isImporting, setIsImporting] = useState(false);
    const [discoverError, setDiscoverError] = useState<string | null>(null);
    const [importError, setImportError] = useState<string | null>(null);
    const [importSuccess, setImportSuccess] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState("");

    const discover = useCallback(async () => {
        setIsDiscovering(true);
        setDiscoverError(null);
        setModels([]);
        setSelected(new Set());
        setSearchQuery("");
        try {
            const result = await discoverModelsMutation(provider.id);
            setModels(result);
            // Pre-select new (not yet imported) models
            const newOnes = new Set(
                result.filter((m) => !m.already_imported).map((m) => m.model_code)
            );
            setSelected(newOnes);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "探索失敗";
            setDiscoverError(msg);
        } finally {
            setIsDiscovering(false);
        }
    }, [provider.id]);

    // Auto-discover on mount
    useEffect(() => {
        discover();
    }, [discover]);

    const filteredModels = models.filter((m) => 
        m.model_code.toLowerCase().includes(searchQuery.toLowerCase()) ||
        m.display_name.toLowerCase().includes(searchQuery.toLowerCase())
    );

    const toggleAll = () => {
        const visibleCodes = filteredModels.map(m => m.model_code);
        const allVisibleSelected = visibleCodes.length > 0 && visibleCodes.every(code => selected.has(code));

        if (allVisibleSelected) {
            setSelected((prev) => {
                const next = new Set(prev);
                visibleCodes.forEach(code => next.delete(code));
                return next;
            });
        } else {
            setSelected((prev) => {
                const next = new Set(prev);
                visibleCodes.forEach(code => next.add(code));
                return next;
            });
        }
    };

    const toggleOne = (code: string) => {
        setSelected((prev) => {
            const next = new Set(prev);
            if (next.has(code)) {
                next.delete(code);
            } else {
                next.add(code);
            }
            return next;
        });
    };

    const handleImport = async () => {
        if (selected.size === 0) return;
        setIsImporting(true);
        setImportError(null);
        setImportSuccess(null);

        const items = models.filter((m) => selected.has(m.model_code));
        try {
            const imported = await batchImportModelsMutation({
                provider_id: provider.id,
                items,
            });
            setImportSuccess(`成功匯入 ${imported.length} 個模型`);
            onImported();
            setTimeout(() => onClose(), 1500);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "匯入失敗";
            setImportError(msg);
        } finally {
            setIsImporting(false);
        }
    };

    const formatCtx = (ctx: number | null) => {
        if (ctx == null) return "—";
        if (ctx >= 1000) return `${Math.round(ctx / 1000)}K`;
        return String(ctx);
    };

    const allVisibleSelected = filteredModels.length > 0 && filteredModels.every(m => selected.has(m.model_code));
    const someVisibleSelected = !allVisibleSelected && filteredModels.some(m => selected.has(m.model_code));

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div className="bg-surface-container-low rounded-3xl border border-outline-variant/20 shadow-2xl w-full max-w-4xl mx-4 overflow-hidden max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between px-8 py-6 border-b border-outline-variant/10 flex-shrink-0">
                    <div>
                        <h2 className="text-lg font-bold tracking-tight">Discover Models</h2>
                        <p className="text-xs text-on-surface-variant/60 mt-0.5">
                            Provider: {provider.display_name}
                            {provider.base_url && (
                                <span className="font-mono ml-2 opacity-60">{provider.base_url}</span>
                            )}
                        </p>
                    </div>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={discover}
                            disabled={isDiscovering}
                            title="重新探索"
                            className="p-2 rounded-xl hover:bg-surface-container-high transition-colors text-on-surface-variant disabled:opacity-50"
                        >
                            <RefreshCw size={16} className={cn(isDiscovering && "animate-spin")} />
                        </button>
                        <button
                            onClick={onClose}
                            className="p-2 rounded-xl hover:bg-surface-container-high transition-colors text-on-surface-variant"
                        >
                            <X size={18} />
                        </button>
                    </div>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto custom-scrollbar">
                    {/* Discovering */}
                    {isDiscovering && (
                        <div className="flex items-center justify-center py-16 opacity-50">
                            <Loader2 className="animate-spin mr-3" size={20} />
                            <span className="text-sm font-medium">探索中...</span>
                        </div>
                    )}

                    {/* Error */}
                    {discoverError && !isDiscovering && (
                        <div className="mx-8 my-6 bg-error/10 border border-error/20 rounded-xl px-4 py-3 text-sm text-error">
                            {discoverError}
                        </div>
                    )}

                    {/* Ollama hint */}
                    {provider.provider_code === "ollama" && !isDiscovering && (
                        <div className="mx-8 mt-6 bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
                            💡 先執行 <code>ollama pull &lt;model&gt;</code> 再用 Discover 匯入
                        </div>
                    )}

                    {/* Filter & Model list */}
                    {!isDiscovering && models.length > 0 && (
                        <div className="px-8 py-4">
                            {/* Filter Input */}
                            <div className="relative mb-4">
                                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant/40">
                                    <Search size={14} />
                                </span>
                                <input
                                    type="text"
                                    placeholder="搜尋模型代碼或名稱..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="w-full bg-surface-container-high border border-outline-variant/20 rounded-xl py-2 pl-10 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-primary/20 transition-all"
                                />
                                {searchQuery && (
                                    <button
                                        onClick={() => setSearchQuery("")}
                                        className="absolute right-3 top-1/2 -translate-y-1/2 text-on-surface-variant/40 hover:text-on-surface-variant"
                                    >
                                        <X size={14} />
                                    </button>
                                )}
                            </div>

                            {/* Select all row */}
                            <div className="flex items-center gap-3 mb-3 pb-3 border-b border-outline-variant/10">
                                <button
                                    onClick={toggleAll}
                                    className="flex items-center gap-2 text-xs font-bold text-on-surface-variant hover:text-primary transition-colors"
                                >
                                    {allVisibleSelected ? (
                                        <CheckSquare size={16} className="text-primary" />
                                    ) : someVisibleSelected ? (
                                        <CheckSquare size={16} className="text-primary/50" />
                                    ) : (
                                        <Square size={16} />
                                    )}
                                    全選 ({filteredModels.length}{searchQuery ? " 個過濾結果" : " 個"})
                                </button>
                                <span className="ml-auto text-xs text-on-surface-variant/50">
                                    已選 {selected.size} 個
                                </span>
                            </div>

                            {/* Table */}
                            <div className="space-y-1">
                                {filteredModels.map((m) => {
                                    const isSelected = selected.has(m.model_code);
                                    return (
                                        <div
                                            key={m.model_code}
                                            onClick={() => toggleOne(m.model_code)}
                                            className={cn(
                                                "flex items-center gap-3 px-3 py-2.5 rounded-xl cursor-pointer transition-all",
                                                isSelected
                                                    ? "bg-primary/5 border border-primary/20"
                                                    : "hover:bg-surface-container-high border border-transparent"
                                            )}
                                        >
                                            {/* Checkbox */}
                                            <div className="flex-shrink-0">
                                                {isSelected ? (
                                                    <CheckSquare size={16} className="text-primary" />
                                                ) : (
                                                    <Square size={16} className="text-on-surface-variant/40" />
                                                )}
                                            </div>

                                            {/* Model code */}
                                            <span 
                                                className="font-mono text-xs font-bold flex-[2] min-w-0 truncate"
                                                title={m.model_code}
                                            >
                                                {m.model_code}
                                            </span>

                                            {/* Display name */}
                                            <span 
                                                className="text-xs text-on-surface-variant/70 flex-[1.5] min-w-0 truncate"
                                                title={m.display_name}
                                            >
                                                {m.display_name}
                                            </span>

                                            {/* Context */}
                                            <span className="text-[10px] text-on-surface-variant/50 w-12 text-right flex-shrink-0">
                                                {formatCtx(m.context_window)}
                                            </span>

                                            {/* Status badge */}
                                            <div className="flex-shrink-0 w-20 text-right">
                                                {m.already_imported ? (
                                                    <span className="text-[10px] px-2 py-0.5 rounded-lg bg-surface-container-high text-on-surface-variant/50 border border-outline-variant/20">
                                                        已匯入
                                                    </span>
                                                ) : (
                                                    <span className="text-[10px] px-2 py-0.5 rounded-lg bg-green-500/10 text-green-700 dark:text-green-400 border border-green-500/20">
                                                        新
                                                    </span>
                                                )}
                                            </div>
                                        </div>
                                    );
                                })}

                                {filteredModels.length === 0 && searchQuery && (
                                    <div className="py-8 text-center text-xs text-on-surface-variant/50">
                                        查無符合過濾條件的模型
                                    </div>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Empty */}
                    {!isDiscovering && !discoverError && models.length === 0 && (
                        <div className="flex flex-col items-center justify-center py-16 opacity-40">
                            <p className="text-sm font-bold">未發現任何模型</p>
                            <p className="text-xs text-on-surface-variant mt-1">
                                請確認 Provider 連線正常
                            </p>
                        </div>
                    )}
                </div>

                {/* Footer */}
                <div className="px-8 py-5 border-t border-outline-variant/10 flex-shrink-0">
                    {/* Feedback */}
                    {importError && (
                        <div className="mb-3 bg-error/10 border border-error/20 rounded-xl px-4 py-2 text-xs text-error">
                            {importError}
                        </div>
                    )}
                    {importSuccess && (
                        <div className="mb-3 bg-green-500/10 border border-green-500/20 rounded-xl px-4 py-2 text-xs text-green-700 dark:text-green-400">
                            ✓ {importSuccess}
                        </div>
                    )}

                    <div className="flex items-center justify-between">
                        <p className="text-xs text-on-surface-variant/50">
                            💡 已匯入者預設略過不覆蓋
                        </p>
                        <div className="flex gap-3">
                            <button
                                onClick={onClose}
                                className="px-5 py-2 rounded-xl border border-outline-variant/30 text-sm font-bold hover:bg-surface-container-high transition-all"
                            >
                                取消
                            </button>
                            <button
                                onClick={handleImport}
                                disabled={selected.size === 0 || isImporting}
                                className="flex items-center gap-2 px-5 py-2 rounded-xl bg-primary text-on-primary text-sm font-bold hover:opacity-90 transition-all disabled:opacity-50"
                            >
                                {isImporting ? (
                                    <Loader2 size={14} className="animate-spin" />
                                ) : (
                                    <Download size={14} />
                                )}
                                批次匯入所選 ({selected.size})
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
