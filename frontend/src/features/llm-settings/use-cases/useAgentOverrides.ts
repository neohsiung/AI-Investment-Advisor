"use client";

/**
 * useAgentOverrides — React hook for Agent Override CRUD (Phase C).
 *
 * Manages local state for the agent overrides list and provides
 * save / delete operations backed by the API.
 */

import { useState, useEffect, useCallback } from "react";
import type { AgentOverride, AgentOverrideUpdate } from "../domain/types";
import { getAgentOverrides, updateAgentOverrides } from "../infra/llmSettingsApi";

export interface UseAgentOverridesReturn {
    /** Current list of agent overrides */
    overrides: AgentOverride[];
    /** True while loading from API */
    isLoading: boolean;
    /** True while saving to API */
    isSaving: boolean;
    /** Last error message, if any */
    error: string | null;
    /** Reload overrides from API */
    reload: () => Promise<void>;
    /**
     * Save (bulk-upsert) a list of overrides.
     * Replaces the entire list on the server.
     */
    saveOverrides: (updates: AgentOverrideUpdate[]) => Promise<void>;
}

export function useAgentOverrides(): UseAgentOverridesReturn {
    const [overrides, setOverrides] = useState<AgentOverride[]>([]);
    const [isLoading, setIsLoading] = useState(false);
    const [isSaving, setIsSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const reload = useCallback(async () => {
        setIsLoading(true);
        setError(null);
        try {
            const data = await getAgentOverrides();
            setOverrides(data);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            setError(msg);
        } finally {
            setIsLoading(false);
        }
    }, []);

    useEffect(() => {
        reload();
    }, [reload]);

    const saveOverrides = useCallback(async (updates: AgentOverrideUpdate[]) => {
        setIsSaving(true);
        setError(null);
        try {
            const updated = await updateAgentOverrides({ overrides: updates });
            setOverrides(updated);
        } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : String(err);
            setError(msg);
            throw err; // Re-throw so callers can handle
        } finally {
            setIsSaving(false);
        }
    }, []);

    return {
        overrides,
        isLoading,
        isSaving,
        error,
        reload,
        saveOverrides,
    };
}
