// useTierBindings — SWR-based hooks for Tier Binding CRUD (Phase B)
"use client";

import useSWR, { mutate as globalMutate } from "swr";
import { getTierBindings, updateTierBindings } from "../infra/llmSettingsApi";
import type {
    TierBinding,
    TierBindingsUpdateRequest,
    TierName,
} from "../domain/types";

const TIERS_KEY = "/api/v1/settings/llm/tiers";

// ─── List ─────────────────────────────────────────────────────────────────────

/**
 * SWR hook to fetch all 4 tier bindings for the current user.
 * Returns a map keyed by tier name for easy lookup.
 */
export function useTierBindings() {
    const { data, error, isLoading, mutate } = useSWR<TierBinding[]>(
        TIERS_KEY,
        getTierBindings,
        { revalidateOnFocus: false }
    );

    // Build a map for easy access: { nano: TierBinding, fast: TierBinding, ... }
    const bindingsByTier: Partial<Record<TierName, TierBinding>> = {};
    if (data) {
        for (const b of data) {
            bindingsByTier[b.tier as TierName] = b;
        }
    }

    return {
        bindings: data ?? [],
        bindingsByTier,
        isLoading,
        error,
        refresh: mutate,
    };
}

// ─── Mutations ────────────────────────────────────────────────────────────────

/**
 * Save all tier bindings.
 * Throws on 422 validation errors (caller should handle and display inline).
 */
export async function saveTierBindings(
    body: TierBindingsUpdateRequest
): Promise<TierBinding[]> {
    const result = await updateTierBindings(body);
    await globalMutate(TIERS_KEY);
    return result;
}
