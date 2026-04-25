"use client";

import React, { useState, useEffect } from "react";
import { X, Eye, EyeOff, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
    LLMProvider,
    ProviderCode,
    ProviderCreateRequest,
    ProviderUpdateRequest,
} from "../domain/types";
import { PROVIDER_CODES, PROVIDER_DEFAULT_URLS } from "../domain/types";
import {
    createProviderMutation,
    updateProviderMutation,
} from "../use-cases/useProviders";

interface ProviderFormModalProps {
    /** null = create mode, LLMProvider = edit mode */
    provider: LLMProvider | null;
    onClose: () => void;
    onSuccess: (provider: LLMProvider) => void;
}

interface FormState {
    provider_code: ProviderCode;
    display_name: string;
    base_url: string;
    api_key: string;
    enabled: boolean;
}

const INITIAL_FORM: FormState = {
    provider_code: "openrouter",
    display_name: "",
    base_url: "",
    api_key: "",
    enabled: true,
};

export function ProviderFormModal({ provider, onClose, onSuccess }: ProviderFormModalProps) {
    const isEdit = provider !== null;
    const [form, setForm] = useState<FormState>(INITIAL_FORM);
    const [showKey, setShowKey] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Populate form when editing
    useEffect(() => {
        if (provider) {
            setForm({
                provider_code: provider.provider_code,
                display_name: provider.display_name,
                base_url: provider.base_url ?? "",
                api_key: "", // never pre-fill masked key
                enabled: provider.enabled,
            });
        } else {
            setForm(INITIAL_FORM);
        }
    }, [provider]);

    // Auto-fill base_url when provider_code changes (create mode only)
    const handleProviderCodeChange = (code: ProviderCode) => {
        setForm((prev) => ({
            ...prev,
            provider_code: code,
            base_url: PROVIDER_DEFAULT_URLS[code] ?? prev.base_url,
        }));
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setIsSubmitting(true);

        try {
            let result: LLMProvider;
            if (isEdit) {
                const body: ProviderUpdateRequest = {
                    display_name: form.display_name || undefined,
                    base_url: form.base_url || null,
                    api_key: form.api_key || null, // null = don't change
                    enabled: form.enabled,
                };
                result = await updateProviderMutation(provider!.id, body);
            } else {
                const body: ProviderCreateRequest = {
                    provider_code: form.provider_code,
                    display_name: form.display_name,
                    base_url: form.base_url || null,
                    api_key: form.api_key || null,
                    enabled: form.enabled,
                };
                result = await createProviderMutation(body);
            }
            onSuccess(result);
            onClose();
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "操作失敗，請稍後再試";
            setError(msg);
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div className="bg-surface-container-low rounded-3xl border border-outline-variant/20 shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
                {/* Header */}
                <div className="flex items-center justify-between px-8 py-6 border-b border-outline-variant/10">
                    <h2 className="text-lg font-bold tracking-tight">
                        {isEdit ? "編輯 Provider" : "新增 Provider"}
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-xl hover:bg-surface-container-high transition-colors text-on-surface-variant"
                    >
                        <X size={18} />
                    </button>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="px-8 py-6 space-y-5">
                    {/* Provider Code (create only) */}
                    {!isEdit && (
                        <div className="space-y-2">
                            <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                                Provider 類型
                            </label>
                            <select
                                value={form.provider_code}
                                onChange={(e) => handleProviderCodeChange(e.target.value as ProviderCode)}
                                className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm focus:border-primary/50 transition-all outline-none"
                            >
                                {PROVIDER_CODES.map((code) => (
                                    <option key={code} value={code}>
                                        {code}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}

                    {/* Display Name */}
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                            顯示名稱 <span className="text-error">*</span>
                        </label>
                        <input
                            type="text"
                            required
                            value={form.display_name}
                            onChange={(e) => setForm((p) => ({ ...p, display_name: e.target.value }))}
                            placeholder="e.g. OpenRouter (Main)"
                            className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm focus:border-primary/50 transition-all outline-none"
                        />
                    </div>

                    {/* Base URL */}
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                            Base URL <span className="text-on-surface-variant/40">(可選)</span>
                        </label>
                        <input
                            type="url"
                            value={form.base_url}
                            onChange={(e) => setForm((p) => ({ ...p, base_url: e.target.value }))}
                            placeholder="https://openrouter.ai/api/v1"
                            className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm font-mono focus:border-primary/50 transition-all outline-none"
                        />
                    </div>

                    {/* API Key */}
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                            API Key{" "}
                            {isEdit && (
                                <span className="text-on-surface-variant/40 normal-case font-normal">
                                    (留空 = 不變更)
                                </span>
                            )}
                        </label>
                        <div className="relative">
                            <input
                                type={showKey ? "text" : "password"}
                                value={form.api_key}
                                onChange={(e) => setForm((p) => ({ ...p, api_key: e.target.value }))}
                                placeholder={isEdit ? "••••••••" : "sk-..."}
                                className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl pl-4 pr-12 py-3 text-sm font-mono focus:border-primary/50 transition-all outline-none"
                            />
                            <button
                                type="button"
                                onClick={() => setShowKey((v) => !v)}
                                className="absolute right-4 top-1/2 -translate-y-1/2 text-on-surface-variant/50 hover:text-primary transition-colors"
                            >
                                {showKey ? <EyeOff size={16} /> : <Eye size={16} />}
                            </button>
                        </div>
                    </div>

                    {/* Enabled Toggle */}
                    <div className="flex items-center justify-between bg-surface-container rounded-xl px-4 py-3">
                        <span className="text-sm font-medium">啟用此 Provider</span>
                        <button
                            type="button"
                            onClick={() => setForm((p) => ({ ...p, enabled: !p.enabled }))}
                            className={cn(
                                "relative w-12 h-6 rounded-full transition-all duration-300 outline-none",
                                form.enabled ? "bg-primary shadow-inner" : "bg-surface-container-highest"
                            )}
                        >
                            <div
                                className={cn(
                                    "absolute top-1 left-1 w-4 h-4 rounded-full bg-white transition-all duration-300 shadow-sm",
                                    form.enabled ? "translate-x-6" : "translate-x-0"
                                )}
                            />
                        </button>
                    </div>

                    {/* Ollama hint */}
                    {form.provider_code === "ollama" && (
                        <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl px-4 py-3 text-xs text-amber-700 dark:text-amber-400">
                            💡 本地模型，確保 Ollama 服務已啟動（<code>ollama serve</code>）
                        </div>
                    )}

                    {/* Error */}
                    {error && (
                        <div className="bg-error/10 border border-error/20 rounded-xl px-4 py-3 text-xs text-error">
                            {error}
                        </div>
                    )}

                    {/* Actions */}
                    <div className="flex justify-end gap-3 pt-2">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-6 py-2.5 rounded-xl border border-outline-variant/30 text-sm font-bold hover:bg-surface-container-high transition-all"
                        >
                            取消
                        </button>
                        <button
                            type="submit"
                            disabled={isSubmitting}
                            className="px-6 py-2.5 rounded-xl bg-primary text-on-primary text-sm font-bold hover:opacity-90 transition-all disabled:opacity-50 flex items-center gap-2"
                        >
                            {isSubmitting && <Loader2 size={14} className="animate-spin" />}
                            {isEdit ? "儲存變更" : "建立"}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
