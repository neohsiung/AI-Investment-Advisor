"use client";

import React, { useState, useEffect } from "react";
import { X, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type {
    LLMModel,
    LLMProvider,
    ModelCreateRequest,
    ModelUpdateRequest,
    ModelCapabilities,
} from "../domain/types";
import { DEFAULT_MODEL_CAPABILITIES } from "../domain/types";
import { CapabilityCheckboxes } from "./CapabilityChips";
import { createModelMutation, updateModelMutation } from "../use-cases/useModels";

interface ModelFormModalProps {
    /** null = create mode, LLMModel = edit mode */
    model: LLMModel | null;
    providers: LLMProvider[];
    defaultProviderId?: string;
    onClose: () => void;
    onSuccess: (model: LLMModel) => void;
}

interface FormState {
    provider_id: string;
    model_code: string;
    display_name: string;
    capabilities: ModelCapabilities;
    context_window: string;
    input_cost_per_1k: string;
    output_cost_per_1k: string;
    notes: string;
}

function makeInitialForm(
    model: LLMModel | null,
    defaultProviderId?: string
): FormState {
    if (model) {
        return {
            provider_id: model.provider_id,
            model_code: model.model_code,
            display_name: model.display_name,
            capabilities: { ...model.capabilities },
            context_window: model.context_window != null ? String(model.context_window) : "",
            input_cost_per_1k: model.input_cost_per_1k != null ? String(model.input_cost_per_1k) : "",
            output_cost_per_1k: model.output_cost_per_1k != null ? String(model.output_cost_per_1k) : "",
            notes: model.notes ?? "",
        };
    }
    return {
        provider_id: defaultProviderId ?? "",
        model_code: "",
        display_name: "",
        capabilities: { ...DEFAULT_MODEL_CAPABILITIES },
        context_window: "",
        input_cost_per_1k: "",
        output_cost_per_1k: "",
        notes: "",
    };
}

export function ModelFormModal({
    model,
    providers,
    defaultProviderId,
    onClose,
    onSuccess,
}: ModelFormModalProps) {
    const isEdit = model !== null;
    const [form, setForm] = useState<FormState>(() =>
        makeInitialForm(model, defaultProviderId)
    );
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        setForm(makeInitialForm(model, defaultProviderId));
        setError(null);
    }, [model, defaultProviderId]);

    const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
        setForm((p) => ({ ...p, [key]: value }));

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);
        setIsSubmitting(true);

        try {
            let result: LLMModel;
            if (isEdit) {
                const body: ModelUpdateRequest = {
                    display_name: form.display_name || undefined,
                    capabilities: form.capabilities,
                    context_window: form.context_window ? parseInt(form.context_window, 10) : null,
                    input_cost_per_1k: form.input_cost_per_1k ? parseFloat(form.input_cost_per_1k) : null,
                    output_cost_per_1k: form.output_cost_per_1k ? parseFloat(form.output_cost_per_1k) : null,
                    notes: form.notes || null,
                };
                result = await updateModelMutation(model!.id, body);
            } else {
                const body: ModelCreateRequest = {
                    provider_id: form.provider_id,
                    model_code: form.model_code,
                    display_name: form.display_name,
                    capabilities: form.capabilities,
                    context_window: form.context_window ? parseInt(form.context_window, 10) : null,
                    input_cost_per_1k: form.input_cost_per_1k ? parseFloat(form.input_cost_per_1k) : null,
                    output_cost_per_1k: form.output_cost_per_1k ? parseFloat(form.output_cost_per_1k) : null,
                    notes: form.notes || null,
                };
                result = await createModelMutation(body);
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
            <div className="bg-surface-container-low rounded-3xl border border-outline-variant/20 shadow-2xl w-full max-w-xl mx-4 overflow-hidden max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between px-8 py-6 border-b border-outline-variant/10 flex-shrink-0">
                    <h2 className="text-lg font-bold tracking-tight">
                        {isEdit ? "編輯 Model" : "手動新增 Model"}
                    </h2>
                    <button
                        onClick={onClose}
                        className="p-2 rounded-xl hover:bg-surface-container-high transition-colors text-on-surface-variant"
                    >
                        <X size={18} />
                    </button>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="px-8 py-6 space-y-5 overflow-y-auto flex-1 custom-scrollbar">
                    {/* Provider */}
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                            Provider <span className="text-error">*</span>
                        </label>
                        {isEdit ? (
                            <div className="px-4 py-3 bg-surface-container-high rounded-xl text-sm font-mono text-on-surface-variant/70">
                                {model?.provider_display_name} ({model?.provider_code})
                            </div>
                        ) : (
                            <select
                                required
                                value={form.provider_id}
                                onChange={(e) => set("provider_id", e.target.value)}
                                className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm focus:border-primary/50 transition-all outline-none"
                            >
                                <option value="">選擇 Provider...</option>
                                {providers.map((p) => (
                                    <option key={p.id} value={p.id}>
                                        {p.display_name} ({p.provider_code})
                                    </option>
                                ))}
                            </select>
                        )}
                    </div>

                    {/* Model Code */}
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                            Model Code <span className="text-error">*</span>
                        </label>
                        <input
                            type="text"
                            required
                            disabled={isEdit}
                            value={form.model_code}
                            onChange={(e) => set("model_code", e.target.value)}
                            placeholder="e.g. google/gemini-2.5-pro"
                            className={cn(
                                "w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm font-mono focus:border-primary/50 transition-all outline-none",
                                isEdit && "opacity-60 cursor-not-allowed"
                            )}
                        />
                    </div>

                    {/* Display Name */}
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                            顯示名稱 <span className="text-error">*</span>
                        </label>
                        <input
                            type="text"
                            required
                            value={form.display_name}
                            onChange={(e) => set("display_name", e.target.value)}
                            placeholder="e.g. Gemini 2.5 Pro"
                            className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm focus:border-primary/50 transition-all outline-none"
                        />
                    </div>

                    {/* Capabilities */}
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                            能力
                        </label>
                        <div className="bg-surface-container rounded-xl px-4 py-3">
                            <CapabilityCheckboxes
                                value={form.capabilities}
                                onChange={(v) => set("capabilities", v)}
                            />
                        </div>
                    </div>

                    {/* Context Window + Costs */}
                    <div className="grid grid-cols-3 gap-4">
                        <div className="space-y-2">
                            <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                                Context Window
                            </label>
                            <input
                                type="number"
                                min="0"
                                value={form.context_window}
                                onChange={(e) => set("context_window", e.target.value)}
                                placeholder="128000"
                                className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm font-mono focus:border-primary/50 transition-all outline-none"
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                                Input $/1K
                            </label>
                            <input
                                type="number"
                                min="0"
                                step="0.000001"
                                value={form.input_cost_per_1k}
                                onChange={(e) => set("input_cost_per_1k", e.target.value)}
                                placeholder="0.00"
                                className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm font-mono focus:border-primary/50 transition-all outline-none"
                            />
                        </div>
                        <div className="space-y-2">
                            <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                                Output $/1K
                            </label>
                            <input
                                type="number"
                                min="0"
                                step="0.000001"
                                value={form.output_cost_per_1k}
                                onChange={(e) => set("output_cost_per_1k", e.target.value)}
                                placeholder="0.00"
                                className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm font-mono focus:border-primary/50 transition-all outline-none"
                            />
                        </div>
                    </div>

                    {/* Notes */}
                    <div className="space-y-2">
                        <label className="block text-[10px] font-black uppercase text-on-surface-variant tracking-widest">
                            備註 <span className="text-on-surface-variant/40 normal-case font-normal">(可選)</span>
                        </label>
                        <textarea
                            value={form.notes}
                            onChange={(e) => set("notes", e.target.value)}
                            rows={2}
                            placeholder="自訂備註..."
                            className="w-full bg-surface-container-high border-2 border-outline-variant/20 rounded-xl px-4 py-3 text-sm focus:border-primary/50 transition-all outline-none resize-none"
                        />
                    </div>

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
