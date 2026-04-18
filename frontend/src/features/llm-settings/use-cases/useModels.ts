// useModels — SWR-based hooks for Model CRUD + discover + batch-import
"use client";

import useSWR, { mutate as globalMutate } from "swr";
import {
    listModels,
    createModel,
    updateModel,
    deleteModel,
    getModelUsages,
    discoverModels,
    batchImportModels,
} from "../infra/llmSettingsApi";
import type {
    LLMModel,
    ModelCreateRequest,
    ModelUpdateRequest,
    ModelUsagesResponse,
    DiscoveredModel,
    BatchImportRequest,
} from "../domain/types";

const MODELS_KEY = "/api/v1/settings/llm/models";

function modelsKey(providerId?: string) {
    return providerId ? `${MODELS_KEY}?provider_id=${providerId}` : MODELS_KEY;
}

// ─── List ─────────────────────────────────────────────────────────────────────

export function useModels(providerId?: string) {
    const key = modelsKey(providerId);
    const { data, error, isLoading, mutate } = useSWR<LLMModel[]>(
        key,
        () => listModels(providerId),
        { revalidateOnFocus: false }
    );

    return {
        models: data ?? [],
        isLoading,
        error,
        refresh: mutate,
    };
}

// ─── Model Usages (on-demand) ─────────────────────────────────────────────────

export function useModelUsages(modelId: string | null) {
    const { data, error, isLoading } = useSWR<ModelUsagesResponse>(
        modelId ? `${MODELS_KEY}/${modelId}/usages` : null,
        () => getModelUsages(modelId!),
        { revalidateOnFocus: false }
    );

    return {
        usages: data ?? null,
        isLoading,
        error,
    };
}

// ─── Mutations ────────────────────────────────────────────────────────────────

async function revalidateModels() {
    // Revalidate both the global list and any provider-filtered lists
    await globalMutate(
        (key: string) => typeof key === "string" && key.startsWith(MODELS_KEY),
        undefined,
        { revalidate: true }
    );
}

export async function createModelMutation(body: ModelCreateRequest): Promise<LLMModel> {
    const result = await createModel(body);
    await revalidateModels();
    return result;
}

export async function updateModelMutation(
    id: string,
    body: ModelUpdateRequest
): Promise<LLMModel> {
    const result = await updateModel(id, body);
    await revalidateModels();
    return result;
}

export async function deleteModelMutation(id: string): Promise<void> {
    await deleteModel(id);
    await revalidateModels();
}

export async function getModelUsagesMutation(id: string): Promise<ModelUsagesResponse> {
    return getModelUsages(id);
}

export async function discoverModelsMutation(providerId: string): Promise<DiscoveredModel[]> {
    return discoverModels(providerId);
}

export async function batchImportModelsMutation(
    body: BatchImportRequest
): Promise<LLMModel[]> {
    const result = await batchImportModels(body);
    await revalidateModels();
    return result;
}
