// LLM Settings API Client
// Wraps all endpoints under /api/v1/settings/llm/
import { apiClient } from "@/lib/apiClient";
import type {
    LLMProvider,
    LLMModel,
    ProviderCreateRequest,
    ProviderUpdateRequest,
    ProviderTestResult,
    ProviderUsagesResponse,
    ModelCreateRequest,
    ModelUpdateRequest,
    ModelUsagesResponse,
    DiscoveredModel,
    BatchImportRequest,
    TierBinding,
    TierBindingsUpdateRequest,
    AgentOverride,
    AgentOverridesUpdateRequest,
} from "../domain/types";

const BASE = "/api/v1/settings/llm";

// ─── Helper ──────────────────────────────────────────────────────────────────

async function unwrap<T>(promise: Promise<{ data: { data: T } | T }>): Promise<T> {
    const res = await promise;
    // Handle both { data: { data: T } } and { data: T } shapes
    const payload = (res as any).data;
    if (payload && typeof payload === "object" && "data" in payload) {
        return payload.data as T;
    }
    return payload as T;
}

// ─── Provider Endpoints ───────────────────────────────────────────────────────

/**
 * GET /api/v1/settings/llm/providers
 * List all providers for the current user
 */
export async function listProviders(): Promise<LLMProvider[]> {
    const res = await apiClient.get(`${BASE}/providers`);
    const payload = (res as any).data;
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.data)) return payload.data;
    return [];
}

/**
 * POST /api/v1/settings/llm/providers
 * Create a new provider
 */
export async function createProvider(body: ProviderCreateRequest): Promise<LLMProvider> {
    return unwrap(apiClient.post(`${BASE}/providers`, body));
}

/**
 * PATCH /api/v1/settings/llm/providers/{id}
 * Update an existing provider
 */
export async function updateProvider(id: string, body: ProviderUpdateRequest): Promise<LLMProvider> {
    return unwrap(apiClient.patch(`${BASE}/providers/${id}`, body));
}

/**
 * DELETE /api/v1/settings/llm/providers/{id}
 * Delete a provider (409 if models reference it)
 */
export async function deleteProvider(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/providers/${id}`);
}

/**
 * POST /api/v1/settings/llm/providers/{id}/test
 * Test provider connectivity
 */
export async function testProvider(id: string): Promise<ProviderTestResult> {
    return unwrap(apiClient.post(`${BASE}/providers/${id}/test`, {}));
}

/**
 * GET /api/v1/settings/llm/providers/{id}/usages
 * Get provider usages (for delete pre-check)
 */
export async function getProviderUsages(id: string): Promise<ProviderUsagesResponse> {
    return unwrap(apiClient.get(`${BASE}/providers/${id}/usages`));
}

// ─── Model Endpoints ──────────────────────────────────────────────────────────

/**
 * GET /api/v1/settings/llm/models
 * List all models, optionally filtered by provider_id
 */
export async function listModels(providerId?: string): Promise<LLMModel[]> {
    const url = providerId
        ? `${BASE}/models?provider_id=${encodeURIComponent(providerId)}`
        : `${BASE}/models`;
    const res = await apiClient.get(url);
    const payload = (res as any).data;
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.data)) return payload.data;
    return [];
}

/**
 * POST /api/v1/settings/llm/models
 * Create a model manually
 */
export async function createModel(body: ModelCreateRequest): Promise<LLMModel> {
    return unwrap(apiClient.post(`${BASE}/models`, body));
}

/**
 * PATCH /api/v1/settings/llm/models/{id}
 * Update a model
 */
export async function updateModel(id: string, body: ModelUpdateRequest): Promise<LLMModel> {
    return unwrap(apiClient.patch(`${BASE}/models/${id}`, body));
}

/**
 * DELETE /api/v1/settings/llm/models/{id}
 * Delete a model (409 if tier/agent references it)
 */
export async function deleteModel(id: string): Promise<void> {
    await apiClient.delete(`${BASE}/models/${id}`);
}

/**
 * GET /api/v1/settings/llm/models/{id}/usages
 * Get model usages (for delete pre-check)
 */
export async function getModelUsages(id: string): Promise<ModelUsagesResponse> {
    return unwrap(apiClient.get(`${BASE}/models/${id}/usages`));
}

// ─── Discovery Endpoints ──────────────────────────────────────────────────────

/**
 * POST /api/v1/settings/llm/providers/{id}/discover-models
 * Discover available models from a provider
 */
export async function discoverModels(providerId: string): Promise<DiscoveredModel[]> {
    const res = await apiClient.post(`${BASE}/providers/${providerId}/discover-models`, {});
    const payload = (res as any).data;
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.data)) return payload.data;
    if (payload && Array.isArray(payload.models)) return payload.models;
    return [];
}

/**
 * POST /api/v1/settings/llm/models/batch-import
 * Batch import discovered models
 */
export async function batchImportModels(body: BatchImportRequest): Promise<LLMModel[]> {
    const res = await apiClient.post(`${BASE}/models/batch-import`, body);
    const payload = (res as any).data;
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.data)) return payload.data;
    return [];
}

// ─── Tier Binding Endpoints (Phase B) ────────────────────────────────────────

/**
 * GET /api/v1/settings/llm/tiers
 * List all tier bindings for the current user (with expanded model details)
 */
export async function getTierBindings(): Promise<TierBinding[]> {
    const res = await apiClient.get(`${BASE}/tiers`);
    const payload = (res as any).data;
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.data)) return payload.data;
    return [];
}

/**
 * PUT /api/v1/settings/llm/tiers
 * Bulk-update tier bindings. Returns 422 with errors on validation failure.
 */
export async function updateTierBindings(body: TierBindingsUpdateRequest): Promise<TierBinding[]> {
    const res = await apiClient.put(`${BASE}/tiers`, body);
    const payload = (res as any).data;
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.data)) return payload.data;
    return [];
}

// ─── Agent Override Endpoints (Phase C) ──────────────────────────────────────

/**
 * GET /api/v1/settings/llm/agent-overrides
 * List all agent overrides for the current user (with expanded model details)
 */
export async function getAgentOverrides(): Promise<AgentOverride[]> {
    const res = await apiClient.get(`${BASE}/agent-overrides`);
    const payload = (res as any).data;
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.data)) return payload.data;
    return [];
}

/**
 * PUT /api/v1/settings/llm/agent-overrides
 * Bulk-upsert agent overrides. Returns 422 with errors on validation failure.
 */
export async function updateAgentOverrides(body: AgentOverridesUpdateRequest): Promise<AgentOverride[]> {
    const res = await apiClient.put(`${BASE}/agent-overrides`, body);
    const payload = (res as any).data;
    if (Array.isArray(payload)) return payload;
    if (payload && Array.isArray(payload.data)) return payload.data;
    return [];
}
