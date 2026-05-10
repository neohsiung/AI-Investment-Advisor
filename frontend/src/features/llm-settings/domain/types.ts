// LLM Settings Domain Types
// Mirrors src/api/v1/schemas/llm_settings_schemas.py

// ─── Capabilities ────────────────────────────────────────────────────────────

export interface ProviderCapabilities {
    tool_calling: boolean;
    streaming: boolean;
    vision: boolean;
    json_mode: boolean;
    embeddings: boolean;
    local: boolean;
}

export interface ModelCapabilities {
    tool_calling: boolean;
    vision: boolean;
    json_mode: boolean;
    streaming: boolean;
    embeddings: boolean;
}

// ─── Provider ────────────────────────────────────────────────────────────────

export type ProviderCode =
    | "openai"
    | "openrouter"
    | "gemini"
    | "anthropic"
    | "ollama"
    | "groq"
    | "nvidia";

export type HealthStatus = "healthy" | "unhealthy" | "unknown" | "ok" | "error";

export interface LLMProvider {
    id: string;
    provider_code: ProviderCode;
    display_name: string;
    base_url: string | null;
    api_key_masked: string | null;
    enabled: boolean;
    extra_config: Record<string, unknown>;
    default_capabilities: ProviderCapabilities;
    health_status: HealthStatus | null;
    health_detail: Record<string, unknown> | null;
    last_checked_at: string | null;
    model_count: number;
}

export interface ProviderCreateRequest {
    provider_code: ProviderCode;
    display_name: string;
    base_url?: string | null;
    api_key?: string | null;
    enabled: boolean;
    extra_config?: Record<string, unknown>;
}

export interface ProviderUpdateRequest {
    display_name?: string | null;
    base_url?: string | null;
    api_key?: string | null;
    enabled?: boolean | null;
    extra_config?: Record<string, unknown> | null;
}

export interface ProviderTestResult {
    success: boolean;
    latency_ms: number | null;
    error: string | null;
    checked_at: string;
}

// ─── Model ───────────────────────────────────────────────────────────────────

export type ModelSource = "manual" | "auto_discovered" | "seed";

export interface LLMModel {
    id: string;
    provider_id: string;
    provider_code: ProviderCode;
    provider_display_name: string;
    model_code: string;
    display_name: string;
    capabilities: ModelCapabilities;
    context_window: number | null;
    input_cost_per_1k: number | null;
    output_cost_per_1k: number | null;
    source: ModelSource;
    enabled: boolean;
    notes: string | null;
    usages_count: number;
}

export interface ModelCreateRequest {
    provider_id: string;
    model_code: string;
    display_name: string;
    capabilities: ModelCapabilities;
    context_window?: number | null;
    input_cost_per_1k?: number | null;
    output_cost_per_1k?: number | null;
    notes?: string | null;
}

export interface ModelUpdateRequest {
    display_name?: string | null;
    capabilities?: ModelCapabilities | null;
    context_window?: number | null;
    input_cost_per_1k?: number | null;
    output_cost_per_1k?: number | null;
    enabled?: boolean | null;
    notes?: string | null;
}

// ─── Discovered Model ────────────────────────────────────────────────────────

export interface DiscoveredModel {
    model_code: string;
    display_name: string;
    context_window: number | null;
    input_cost_per_1k: number | null;
    output_cost_per_1k: number | null;
    capabilities: ModelCapabilities | null;
    already_imported: boolean;
    existing_model_id: string | null;
}

export interface BatchImportRequest {
    provider_id: string;
    items: DiscoveredModel[];
}

// ─── Usages ──────────────────────────────────────────────────────────────────

export interface TierUsageItem {
    tier: string;
    role: "primary" | "fallback";
    index: number | null;
    user_id: string;
}

export interface AgentOverrideUsageItem {
    agent_name: string;
    role: "primary" | "fallback";
    index: number | null;
    user_id: string;
}

export interface ModelUsagesResponse {
    model_id: string;
    model_code: string;
    provider_code: string;
    usages: {
        tier_bindings?: TierUsageItem[];
        agent_overrides?: AgentOverrideUsageItem[];
    };
    total_references: number;
    can_delete: boolean;
}

// ─── Tier Bindings (Phase B) ─────────────────────────────────────────────────

export type TierName = "nano" | "fast" | "smart" | "advanced";

export interface PerCandidateConfig {
    max_retries: number;
    timeout_seconds: number;
    conditions?: Record<string, unknown> | null;
}

export interface ModelOut {
    id: string;
    model_code: string;
    display_name: string;
    provider_id: string;
    provider_code: string;
    provider_display_name: string;
    enabled: boolean;
    input_cost_per_1k: number | null;
    output_cost_per_1k: number | null;
    capabilities: ModelCapabilities;
}

export interface TierBinding {
    tier: TierName;
    primary_model_id: string;
    primary_model: ModelOut | null;
    fallback_model_ids: string[];
    fallback_models: ModelOut[];
    per_candidate_config: Record<string, PerCandidateConfig>;
    budget_aware: boolean;
    estimated_daily_cost: number | null;
}

export interface TierBindingUpdate {
    tier: TierName;
    primary_model_id: string;
    fallback_model_ids: string[];
    per_candidate_config?: Record<string, PerCandidateConfig>;
    budget_aware?: boolean;
}

export interface TierBindingsUpdateRequest {
    bindings: TierBindingUpdate[];
}

export interface TierBindingsResponse {
    status: string;
    data: TierBinding[];
}

export const TIER_DESCRIPTIONS: Record<TierName, { label: string; description: string }> = {
    nano: {
        label: "Nano",
        description: "快速分類 — 意圖識別、路由、是否判斷（System 0 反射層）",
    },
    fast: {
        label: "Fast",
        description: "一般分析 — 摘要、提取、快速回應（System 1 快思層）",
    },
    smart: {
        label: "Smart",
        description: "深度推理 — 分析、推論、複雜判斷（System 2 慢想層）",
    },
    advanced: {
        label: "Advanced",
        description: "最終決策 — 複雜策略、CIO 決策、深度研究（System 2+ 深思層）",
    },
};

// ─── Provider Usages (for delete pre-check) ──────────────────────────────────

export interface ProviderUsagesResponse {
    provider_id: string;
    provider_code: string;
    model_count: number;
    models: Array<{ id: string; model_code: string; display_name: string }>;
    can_delete: boolean;
}

// ─── API Response Wrapper ────────────────────────────────────────────────────

export interface ApiListResponse<T> {
    data: T[];
    total: number;
}

export interface ApiItemResponse<T> {
    data: T;
}

// ─── Form State Helpers ──────────────────────────────────────────────────────

export const DEFAULT_MODEL_CAPABILITIES: ModelCapabilities = {
    tool_calling: false,
    vision: false,
    json_mode: false,
    streaming: true,
    embeddings: false,
};

export const PROVIDER_CODES: ProviderCode[] = [
    "openai",
    "openrouter",
    "gemini",
    "anthropic",
    "ollama",
    "groq",
    "nvidia",
];

export const PROVIDER_DEFAULT_URLS: Partial<Record<ProviderCode, string>> = {
    ollama: "http://localhost:11434/v1",
    openrouter: "https://openrouter.ai/api/v1",
    nvidia: "https://integrate.api.nvidia.com/v1",
};

// ─── Agent Overrides (Phase C) ───────────────────────────────────────────────

export type AgentName =
    | "cio"
    | "fundamental"
    | "macro"
    | "momentum"
    | "sentiment"
    | "thematic"
    | "risk"
    | "sentinel"
    | "engineer"
    | "conversation"
    | "skill_router";

export const KNOWN_AGENT_NAMES: AgentName[] = [
    "cio",
    "fundamental",
    "macro",
    "momentum",
    "sentiment",
    "thematic",
    "risk",
    "sentinel",
    "engineer",
    "conversation",
    "skill_router",
];

export const AGENT_DISPLAY_NAMES: Record<AgentName, string> = {
    cio: "CIO（首席投資官）",
    fundamental: "Fundamental（基本面分析）",
    macro: "Macro（總體經濟）",
    momentum: "Momentum（動能分析）",
    sentiment: "Sentiment（情緒分析）",
    thematic: "Thematic（主題研究）",
    risk: "Risk（風險管理）",
    sentinel: "Sentinel（哨兵監控）",
    engineer: "Engineer（工程師）",
    conversation: "Conversation（對話）",
    skill_router: "SkillRouter（技能路由）",
};

export interface AgentOverride {
    id: string;
    user_id: string;
    agent_name: string;
    override_tier: TierName | null;
    primary_model_id: string | null;
    primary_model: ModelOut | null;
    fallback_model_ids: string[];
    fallback_models: ModelOut[];
    forbid_local: boolean;
    forbid_fallback: boolean;
    enabled: boolean;
    notes: string | null;
}

export interface AgentOverrideUpdate {
    agent_name: string;
    override_tier?: TierName | null;
    primary_model_id?: string | null;
    fallback_model_ids?: string[];
    forbid_local?: boolean;
    forbid_fallback?: boolean;
    enabled?: boolean;
    notes?: string | null;
}

export interface AgentOverridesUpdateRequest {
    overrides: AgentOverrideUpdate[];
}

export interface AgentOverridesResponse {
    status: string;
    data: AgentOverride[];
}
