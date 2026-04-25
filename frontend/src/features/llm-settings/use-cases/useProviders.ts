// useProviders — SWR-based hooks for Provider CRUD
"use client";

import useSWR, { mutate as globalMutate } from "swr";
import {
    listProviders,
    createProvider,
    updateProvider,
    deleteProvider,
    testProvider,
    getProviderUsages,
} from "../infra/llmSettingsApi";
import type {
    LLMProvider,
    ProviderCreateRequest,
    ProviderUpdateRequest,
    ProviderTestResult,
    ProviderUsagesResponse,
} from "../domain/types";

const PROVIDERS_KEY = "/api/v1/settings/llm/providers";

// ─── List ─────────────────────────────────────────────────────────────────────

export function useProviders() {
    const { data, error, isLoading, mutate } = useSWR<LLMProvider[]>(
        PROVIDERS_KEY,
        listProviders,
        { revalidateOnFocus: false }
    );

    return {
        providers: data ?? [],
        isLoading,
        error,
        refresh: mutate,
    };
}

// ─── Mutations ────────────────────────────────────────────────────────────────

export async function createProviderMutation(
    body: ProviderCreateRequest
): Promise<LLMProvider> {
    const result = await createProvider(body);
    await globalMutate(PROVIDERS_KEY);
    return result;
}

export async function updateProviderMutation(
    id: string,
    body: ProviderUpdateRequest
): Promise<LLMProvider> {
    const result = await updateProvider(id, body);
    await globalMutate(PROVIDERS_KEY);
    return result;
}

export async function deleteProviderMutation(id: string): Promise<void> {
    await deleteProvider(id);
    await globalMutate(PROVIDERS_KEY);
}

export async function testProviderMutation(id: string): Promise<ProviderTestResult> {
    const result = await testProvider(id);
    // Refresh providers list to update health_status
    await globalMutate(PROVIDERS_KEY);
    return result;
}

export async function getProviderUsagesMutation(
    id: string
): Promise<ProviderUsagesResponse> {
    return getProviderUsages(id);
}
