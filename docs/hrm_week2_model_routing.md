# HRM Week 2: SettingsAwareModelRouter 實現

**日期**: 2026-04-27T23:37:47.897534

## 完整 Model 配置

### Providers

- **ollama**: 4 models, free (local)
- **nvidia_nim**: 4 models, free (cloud)
- **openrouter**: 4 models, paid (cloud)

### 按層級路由 (主 + 3 Fallback)

#### DeepResearch

| 類型 | 配置 | 成本 |
|------|------|------|
| 主 | openrouter/claude-3.5-sonnet | $0.020 |
| F1 | nvidia_nim/llama-3.1-70b | 包含 |
| F2 | ollama/deepseek-r1 | 包含 |
| F3 | openrouter/gpt-4-turbo | 包含 |

#### MemoryDig

| 類型 | 配置 | 成本 |
|------|------|------|
| 主 | nvidia_nim/mixtral-8x22b | $0.003 |
| F1 | openrouter/claude-3.5-haiku | 包含 |
| F2 | ollama/llama2:70b | 包含 |
| F3 | openrouter/gpt-4-turbo | 包含 |

#### FastThink

| 類型 | 配置 | 成本 |
|------|------|------|
| 主 | ollama/mistral:7b | $0.000 |
| F1 | nvidia_nim/mistral-7b | 包含 |
| F2 | openrouter/claude-3.5-haiku | 包含 |
| F3 | ollama/phi | 包含 |

#### Reflexive

| 類型 | 配置 | 成本 |
|------|------|------|
| 主 | ollama/phi:2.7b | $0.000 |
| F1 | nvidia_nim/qwen-2.5-7b | 包含 |
| F2 | openrouter/llama-3.1-8b | 包含 |
| F3 | openrouter/claude-3.5-haiku | 包含 |

