# HRM 優化 Week 1 設計文檔
## Sonnet 3.5 升級路徑 + AST 複雜度檢測

**日期**: April 27, 2026  
**策略**: Gamma (優先推理優化和架構修復)  
**目標**: 30-40% token 成本節省 ($129 → $77-90/month)

---

## 目錄
1. [現狀分析](#1-現狀分析)
2. [Sonnet 3.5 升級路徑](#2-sonnet-35-升級路徑)
3. [AST 複雜度檢測系統](#3-ast-複雜度檢測系統)
4. [SettingsAwareModelRouter 集成](#4-settingsawaremodelrouter-集成)
5. [實施時間表](#5-實施時間表)
6. [成本估算](#6-成本估算)

---

## 1. 現狀分析

### 1.1 Current Architecture Overview

**已部署基礎設施**:
- `SettingsAwareModelRouter` (tier_config.py)
  - ✅ 4層 tier system: nano, fast, smart, advanced
  - ✅ 認知層級映射 (System 0→2+)
  - ✅ DB-first 模型解析 (禁止硬編碼 fallback)
  - ✅ 成本計算和預算追蹤

- `EnterpriseModelRouter` (enterprise_router.py)
  - ✅ 自動 fallback chain: Smart → Fast → Nano
  - ✅ Timeout handling with exponential backoff
  - ✅ ModelFallbackStrategy for error classification
  - ⚠️ 硬編碼 tier config (需優化為 DB-driven)

- `SemanticComplexityDetector` (complexity_detector.py)
  - ✅ 基於長度、關鍵詞、實體的複雜度分析
  - ✅ 4層認知層級分類
  - ✅ 可信度計算 (0.0-1.0)
  - ⚠️ AST 分析缺失 (僅表面特徵)

- `BudgetAwareModelRouter` (budget_aware_model_router.py)
  - ✅ 週預算軟/硬限制 ($16/$20)
  - ✅ config_chain() 支援
  - ✅ 代理覆蓋解析

### 1.2 Current Model Tiers & Costs (March 2026)

| Tier | Model | Input $/MTok | Output $/MTok | Max Tokens | Use Case |
|------|-------|-------------|---------------|-----------|----------|
| **nano** | claude-3-haiku | $0.10 | $0.40 | 512 | 分類、路由 |
| **fast** | claude-3.5-sonnet | $0.30 | $2.50 | 2048 | 總結、提取 |
| **smart** | claude-3-opus | $1.25 | $10.00 | 8192 | 分析、推理 |
| **advanced** | (TBD) | $3.00 | $15.00 | 8192 | CIO 決策 |

**Monthly Spend Breakdown** (目前):
- Baseline: $129/month = ~$31/week = ~$4.40/day
- Per cognitive layer budget:
  - DeepResearch (smart/advanced): $30
  - MemoryDig (smart/haiku): $40
  - FastThink (fast/haiku): $40
  - Reflexive (nim-free): $19

### 1.3 OpenRouter Integration

**已集成**:
- Provider spec (provider_catalog.py, provider_spec.py)
- LLMGateway with OpenRouter backend
- Cost tracking and logging
- Resilient pipeline with retry logic

**現有路由模式**:
```
User Request
  ↓
SettingsAwareModelRouter (fetch from DB)
  ↓
BudgetAwareModelRouter (check spend)
  ↓
EnterpriseModelRouter (fallback chain)
  ↓
LLMGateway (call OpenRouter)
  ↓
Response + Cost Attribution
```

---

## 2. Sonnet 3.5 升級路徑

### 2.1 策略

**核心洞察**:
- Sonnet 3.5 在 speed/cost tradeoff 中提供最佳性能
- 可以將 "smart" 層從 Opus 降級為 Sonnet 3.5 (50% 成本節省)
- 保留 "advanced" 層用於高風險決策 (仍需 Opus 或 o1)

### 2.2 Proposed Tier Reconfiguration (Week 1)

| Tier | Old Model | New Model | Savings | Impact |
|------|-----------|-----------|---------|--------|
| nano | haiku | haiku | — | ✅ 無變 |
| fast | sonnet 3.5 | sonnet 3.5 | — | ✅ 無變 |
| smart | opus | **sonnet 3.5** | ~50% | ⚠️ 需驗證 |
| advanced | (future) | opus / o1 | — | ⚠️ 保留高端 |

**驗證標準**:
```
FOR each cognitive layer (MemoryDig, DeepResearch):
  IF Sonnet 3.5 accuracy ≥ 95% of Opus THEN
    Migrate to Sonnet 3.5
  ELSE
    Keep Opus for that layer
```

### 2.3 Implementation Steps

**Step 1: Create DB Settings Override**
```sql
-- llm_tier_bindings or user_settings
INSERT INTO settings (user_id, key, value)
VALUES 
  ('default', 'AI_MODEL_SMART', 'anthropic/claude-3.5-sonnet@20241022'),
  ('default', 'AI_MODEL_ADVANCED', 'anthropic/claude-opus@20250514');
```

**Step 2: Update TierSpec**
```python
# tier_config.py
"smart": TierSpec(
    name="smart",
    env_key="AI_MODEL_SMART",
    input_cost_per_mtok=0.7,      # from 1.25 (Sonnet input)
    output_cost_per_mtok=3.0,     # from 10.00 (Sonnet output)
    max_tokens=8192,
    description="Sonnet 3.5 analytical layer (Opus fallback for high-stakes)",
    cognitive_mapping="System 2 — 慢想 (Slow Thinking) — Sonnet 3.5",
)
```

**Step 3: Test Complexity Detector with Sonnet**
```python
# Run validation suite against 20+ historical prompts
detector = SemanticComplexityDetector()
for prompt in TEST_SUITE:
    result = detector.analyze(prompt)
    tier = detector.recommend_tier(result)
    # Ensure tier recommendations unchanged
```

**Step 4: Monitor Metrics**
- Token cost per request (comparison Opus vs Sonnet 3.5)
- Latency (should be 10-20% faster)
- Error rates (should be <1% regression)
- User satisfaction (if available)

### 2.4 Fallback Strategy (SettingsAwareModelRouter compatible)

```python
# enterprise_router.py — NO HARDCODING
class EnterpriseModelRouter(SettingsAwareModelRouter):
    async def get_model_with_fallback(self, user_id, stage=None):
        """
        1. Fetch user tier preference from DB (via SettingsAwareModelRouter)
        2. Try primary model (e.g., Sonnet 3.5 for smart tier)
        3. If timeout/quota → fallback to alternate in tier chain
        4. All models come from DB, NO hardcoded defaults
        """
        # Get primary model from DB
        primary_model = self.get_model(user_id, "smart")  # Calls SettingsAwareModelRouter
        
        # Get fallback chain from config_chain()
        chain = self.config_chain(user_id, "smart")  # [Sonnet 3.5, Opus, Sonnet 3-Haiku]
        
        # Try each in chain
        for candidate in chain:
            try:
                response = await self.call_llm_with_auto_fallback(...)
                return response
            except TimeoutError:
                continue  # Try next candidate
        
        # All exhausted → error
        raise RuntimeError("All models in fallback chain failed")
```

---

## 3. AST 複雜度檢測系統

### 3.1 目標

**當前狀態**:
- 基於表面特徵 (長度、關鍵詞、實體)
- 無法處理隱含複雜度

**改進目標**:
- AST 分析 (Abstract Syntax Tree)
- 邏輯複雜度 (條件分支、循環、遞歸)
- 語義複雜度 (概念依賴、因果鏈)
- 準確度 >90% on historical test set

### 3.2 Architecture

```
┌─────────────────────────────────────────┐
│  SemanticComplexityDetector v2          │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  1. Text Normalization & AST Parsing    │
│     - Remove noise (punctuation, links) │
│     - Tokenize by clauses/sentences     │
│     - Build dependency tree             │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  2. Feature Extraction (7 categories)   │
│     • Structural: depth, branching      │
│     • Semantic: concepts, relations     │
│     • Temporal: ranges, sequences       │
│     • Numerical: operations, precision  │
│     • Domain: financial terms, entities │
│     • Intent: action type, risk level   │
│     • Context: dependencies, history    │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  3. Scoring Engine                      │
│     - Weight each feature (0.0-1.0)     │
│     - Combine non-linearly              │
│     - Apply layer transitions           │
└─────────────────────────────────────────┘
         ↓
┌─────────────────────────────────────────┐
│  4. Classification & Confidence         │
│     - Assign to cognitive layer         │
│     - Compute confidence (0.0-1.0)      │
│     - Recommend tier + fallback         │
└─────────────────────────────────────────┘
```

### 3.3 AST Feature Categories

#### A. Structural Features
```python
@dataclass
class StructuralFeatures:
    """語法結構複雜度"""
    clause_depth: int           # Max nesting of conditionals/loops
    condition_count: int        # IF/THEN/ELSE branches
    loop_count: int            # FOR/WHILE/REPEAT patterns
    nested_queries: int        # Multi-level sub-queries
    reference_count: int       # Cross-references to entities/concepts
    
    def complexity_score(self) -> float:
        """0.0 (simple) to 1.0 (very complex)"""
        # Exponential scoring (depth has highest impact)
        return min(1.0, 
            self.clause_depth * 0.3 +
            math.log(self.condition_count + 1) * 0.2 +
            self.nested_queries * 0.3 +
            self.reference_count * 0.1
        )
```

#### B. Semantic Features
```python
@dataclass
class SemanticFeatures:
    """語義複雜度"""
    concept_count: int         # Unique financial/domain concepts
    causal_chains: int         # A→B→C dependencies
    uncertainty_markers: int   # "may", "could", "might", "uncertain"
    multi_step_logic: int      # Multi-part reasoning
    
    def complexity_score(self) -> float:
        """0.0 to 1.0"""
        return min(1.0,
            math.log(self.concept_count + 1) * 0.3 +
            self.causal_chains * 0.3 +
            self.uncertainty_markers * 0.2 +
            self.multi_step_logic * 0.2
        )
```

#### C. Temporal Features
```python
@dataclass
class TemporalFeatures:
    """時間跨度和序列複雜度"""
    time_spans: int            # Number of distinct time periods
    sequence_length: int       # Length of time series
    frequency_changes: int     # Number of frequency shifts
    
    def complexity_score(self) -> float:
        """0.0 to 1.0"""
        return min(1.0,
            self.time_spans * 0.25 +
            math.log(self.sequence_length + 1) * 0.5 +
            self.frequency_changes * 0.25
        )
```

#### D. Numerical Features
```python
@dataclass
class NumericalFeatures:
    """數值精度和操作複雜度"""
    precision_level: float     # Decimal places needed
    operation_complexity: int  # Count of +,-,*,/,%
    comparison_chains: int     # A < B < C chains
    
    def complexity_score(self) -> float:
        return min(1.0,
            math.log(self.precision_level + 1) * 0.2 +
            math.log(self.operation_complexity + 1) * 0.4 +
            self.comparison_chains * 0.4
        )
```

#### E. Domain Features (Financial)
```python
@dataclass
class DomainFeatures:
    """投資領域特定複雜度"""
    ticker_count: int
    market_indices: int        # S&P, VIX, etc.
    derivative_types: int      # Options, futures, swaps
    risk_factor_count: int     # Market, credit, liquidity, etc.
    regulatory_refs: int       # SEC, Fed, etc.
    
    def complexity_score(self) -> float:
        return min(1.0,
            math.log(self.ticker_count + 1) * 0.2 +
            self.derivative_types * 0.3 +
            self.risk_factor_count * 0.3 +
            self.regulatory_refs * 0.2
        )
```

#### F. Intent Features
```python
@dataclass
class IntentFeatures:
    """動作類型和風險程度"""
    is_portfolio_decision: bool
    is_trade_execution: bool
    is_risk_assessment: bool
    is_optimization: bool
    portfolio_size: float      # Dollar amount involved
    
    def complexity_score(self) -> float:
        base = 0.1 if not any([
            self.is_portfolio_decision,
            self.is_trade_execution,
            self.is_risk_assessment
        ]) else 0.5
        
        # High-risk decisions get boost
        if self.is_trade_execution or self.is_risk_assessment:
            base += 0.3
        
        if self.portfolio_size > 1_000_000:
            base += 0.1
            
        return min(1.0, base)
```

#### G. Context Features
```python
@dataclass
class ContextFeatures:
    """上文依賴和歷史"""
    conversation_turn: int     # How deep is the conversation?
    referenced_entities: int   # Prior mentioned entities
    contradictions: int        # Conflicting statements
    
    def complexity_score(self) -> float:
        return min(1.0,
            math.log(self.conversation_turn + 1) * 0.4 +
            math.log(self.referenced_entities + 1) * 0.3 +
            self.contradictions * 0.3
        )
```

### 3.4 Classification Logic

```python
def _compute_complexity_score(self, 
                              structural: StructuralFeatures,
                              semantic: SemanticFeatures,
                              temporal: TemporalFeatures,
                              numerical: NumericalFeatures,
                              domain: DomainFeatures,
                              intent: IntentFeatures,
                              context: ContextFeatures) -> float:
    """
    Weighted combination of all feature categories.
    Returns score in [0.0, 1.0].
    """
    weights = {
        'structural': 0.20,
        'semantic': 0.25,
        'temporal': 0.10,
        'numerical': 0.15,
        'domain': 0.15,
        'intent': 0.10,
        'context': 0.05
    }
    
    scores = [
        structural.complexity_score() * weights['structural'],
        semantic.complexity_score() * weights['semantic'],
        temporal.complexity_score() * weights['temporal'],
        numerical.complexity_score() * weights['numerical'],
        domain.complexity_score() * weights['domain'],
        intent.complexity_score() * weights['intent'],
        context.complexity_score() * weights['context'],
    ]
    
    # Clamp final score
    return min(1.0, sum(scores))
```

### 3.5 Layer Assignment

```python
# Decision thresholds (learned from historical data)
COMPLEXITY_THRESHOLDS = {
    # score → layer
    (0.0, 0.2): CognitiveLayer.REFLEXIVE,      # nano
    (0.2, 0.5): CognitiveLayer.FAST_THINK,     # fast
    (0.5, 0.8): CognitiveLayer.MEMORY_DIG,     # smart
    (0.8, 1.0): CognitiveLayer.DEEP_RESEARCH,  # advanced
}

def classify_layer(self, complexity_score: float) -> CognitiveLayer:
    """Assign to cognitive layer based on complexity."""
    for (lower, upper), layer in COMPLEXITY_THRESHOLDS.items():
        if lower <= complexity_score < upper:
            return layer
    return CognitiveLayer.DEEP_RESEARCH
```

---

## 4. SettingsAwareModelRouter 集成

### 4.1 設計原則

**規範**:
1. **No Hardcoded Fallbacks** — 所有模型配置來自數據庫
2. **DB-First** — 優先從 llm_tier_bindings 或 user_settings 讀取
3. **Clean Architecture** — 路由邏輯與配置分離
4. **Modular** — 新增 tier 只需加一行配置

### 4.2 Routing Chain

```
User Request with Context
    ↓
ComplexityDetector.analyze(request)
    ↓ Recommends: nano/fast/smart/advanced
    ↓
SettingsAwareModelRouter.get_model(user_id, tier)
    ↓ Fetches from DB (NO env fallback)
    ↓
BudgetAwareModelRouter.get_config(tier, user_id)
    ↓ Check weekly spend, possibly downgrade
    ↓
BudgetAwareModelRouter.get_config_chain(user_id, tier)
    ↓ Returns full fallback chain [primary, fallback1, fallback2, ...]
    ↓
ResilientLLMPipeline.execute(messages, config_chain)
    ↓ Try each candidate with timeout/error handling
    ↓
LLMGateway.chat(messages, llm_config)
    ↓ Call OpenRouter
    ↓
CostAttribution.record(user_id, model, cost)
    ↓
Response to User
```

### 4.3 Example Integration

```python
# In agent or skill handler
from src.infrastructure.llm.complexity_detector import SemanticComplexityDetector
from src.infrastructure.llm.tier_config import SettingsAwareModelRouter
from src.infrastructure.llm.budget_aware_model_router import BudgetAwareModelRouter

detector = SemanticComplexityDetector()
router = SettingsAwareModelRouter(settings_repo)
budget_router = BudgetAwareModelRouter(settings_service, token_logger)

# 1. Analyze complexity
result = detector.analyze(user_prompt)
recommended_tier = detector.recommend_tier(result)

# 2. Get model from DB settings
model = router.get_model(user_id, recommended_tier)

# 3. Get budget-aware config
config = budget_router.get_config(recommended_tier, user_id)

# 4. Get resilient gateway with fallback chain
gateway = budget_router.get_resilient_gateway(user_id, recommended_tier)

# 5. Execute with automatic fallback
response, metadata = await gateway.execute(messages)
```

### 4.4 Database Schema (Required)

```sql
-- llm_tier_bindings table
CREATE TABLE llm_tier_bindings (
    id INT PRIMARY KEY,
    user_id VARCHAR(255),
    tier VARCHAR(32),           -- nano, fast, smart, advanced
    model_id VARCHAR(255),      -- anthropic/claude-3.5-sonnet@20241022
    priority INT,               -- 1=primary, 2=fallback, 3=fallback2
    is_enabled BOOL DEFAULT TRUE,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    UNIQUE(user_id, tier, priority)
);

-- user_settings table (if used instead)
-- key format: AI_MODEL_SMART, AI_MODEL_FAST, etc.
```

---

## 5. 實施時間表

### Week 1 Tasks (This Week)

**Day 1-2: Analysis & Design**
- ✅ Analyze run_agent.py / current routing logic
- ✅ Document current token usage baseline
- ✅ Design Sonnet 3.5 upgrade path
- **Deliverable**: This document + code framework

**Day 3-4: AST Detector Development**
- Build enhanced SemanticComplexityDetector v2
- Implement 7 feature extractors
- Create scoring engine
- Write 20+ test cases

**Day 5: Integration & Testing**
- Integrate with SettingsAwareModelRouter
- Test fallback chains
- Validate tier recommendations
- **Deliverable**: semantic_complexity_detector.py + unit tests

### Week 2-3: Validation & Monitoring
- Benchmark Sonnet 3.5 vs Opus
- A/B test on production traffic
- Collect accuracy metrics
- Monitor cost impact

### Week 3-4: Rollout & Documentation
- Gradual tier migration
- Dashboard for cost tracking
- Weekly cost report generation
- Final documentation

---

## 6. 成本估算

### 6.1 Token Impact

**Assumption**: Moving "smart" tier from Opus to Sonnet 3.5

```
Current (Opus):
  Input: 1.25 $/MTok
  Output: 10.00 $/MTok
  Blended: (1.25*3 + 10.00)/4 = 1.94 $/MTok

New (Sonnet 3.5):
  Input: 0.70 $/MTok
  Output: 3.00 $/MTok
  Blended: (0.70*3 + 3.00)/4 = 0.93 $/MTok

Savings per smart-tier call: 1.94 - 0.93 = 1.01 $/MTok = 52%
```

### 6.2 Budget Allocation (Proposed)

| Layer | Current | % Calls | New Model | New Cost | Savings |
|-------|---------|---------|-----------|----------|---------|
| DeepResearch | $30 | 5% | Sonnet 3.5 | $14 | $16 (-53%) |
| MemoryDig | $40 | 15% | Sonnet 3.5 | $20 | $20 (-50%) |
| FastThink | $40 | 35% | Haiku | $40 | — |
| Reflexive | $19 | 45% | Nim-free | $19 | — |
| **TOTAL** | **$129** | 100% | — | **$93** | **$36 (-28%)** |

**Conservative estimate**: 28-40% savings based on tier migration speed

### 6.3 Success Metrics

| Metric | Current | Target | Weight |
|--------|---------|--------|--------|
| Monthly cost | $129 | $77-90 | 40% |
| Avg latency | N/A | <3s | 20% |
| Error rate | <1% | <1% | 20% |
| Accuracy (vs Opus) | 100% | >95% | 20% |

---

## 7. Risk Mitigation

### 7.1 Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Sonnet 3.5 accuracy regression | Medium | High | A/B test first, keep Opus as fallback |
| Complexity detector false negatives | High | Medium | Use conservative thresholds initially |
| DB lookup failures | Low | High | Graceful fallback to tier defaults |
| Budget soft-limit triggering | Medium | Low | Monitor weekly, adjust allocation |

### 7.2 Rollback Plan

```
IF monthly cost > $95 THEN
  Revert AI_MODEL_SMART → opus
  Trigger alert for investigation
  
IF accuracy regression > 5% THEN
  Revert tier assignment changes
  Use original complexity detector
```

---

## 8. Success Criteria

✅ **Week 1 完成標誌**:
1. Detailed design document (this file)
2. `semantic_complexity_detector_v2.py` with 7 feature extractors
3. Updated `tier_config.py` with Sonnet 3.5 specs
4. Integration tests passing (>90% accuracy on 20+ test cases)
5. DB schema for `llm_tier_bindings` created
6. Code framework ready for Week 2 A/B testing

---

## 9. 附錄：代碼框架

### A. File Structure
```
src/infrastructure/llm/
├── tier_config.py                      [已有, Week1需更新]
├── complexity_detector.py              [已有]
├── semantic_complexity_detector_v2.py  [NEW - Week 1]
├── enterprise_router.py                [已有, Week1需審查]
├── budget_aware_model_router.py        [已有]
├── llm_config_chain.py                 [既有]
├── provider_catalog.py                 [既有]
└── ...

tests/unit/infrastructure/llm/
├── test_semantic_complexity_detector_v2.py  [NEW]
├── test_tier_config_integration.py          [NEW]
└── ...

docs/
└── HRM_WEEK1_DESIGN_DOCUMENT.md        [this file]
```

### B. Implementation Checklist

**tier_config.py Updates**:
- [ ] Update TierSpec.input_cost_per_mtok for Sonnet 3.5
- [ ] Update TierSpec.output_cost_per_mtok for Sonnet 3.5
- [ ] Add cognitive_mapping documentation
- [ ] Verify resolve_model() DB-only logic

**semantic_complexity_detector_v2.py** (NEW):
- [ ] Implement StructuralFeatures extractor
- [ ] Implement SemanticFeatures extractor
- [ ] Implement TemporalFeatures extractor
- [ ] Implement NumericalFeatures extractor
- [ ] Implement DomainFeatures extractor (financial specific)
- [ ] Implement IntentFeatures extractor
- [ ] Implement ContextFeatures extractor
- [ ] Implement scoring engine
- [ ] Implement layer classification logic
- [ ] Write 20+ test cases
- [ ] Benchmark accuracy on historical prompts

**enterprise_router.py Review**:
- [ ] Verify no hardcoded model names
- [ ] Ensure all config via DB
- [ ] Test fallback chain with 100+ scenarios
- [ ] Document tier selection logic

**Integration Tests**:
- [ ] Test SettingsAwareModelRouter → BudgetAwareModelRouter flow
- [ ] Test complexity detector → tier recommendation
- [ ] Test tier → model resolution (DB only)
- [ ] Test fallback chain execution
- [ ] Test cost attribution logging

---

## 10. References

- **Optimization Plan**: /tmp/hrm_optimization_plan.json
- **Current Issues**: Hardcoded fallbacks, insufficient complexity analysis
- **Key Constraint**: NO environment variable fallbacks (DB-first only)
- **Success Definition**: 30-40% cost savings + >95% accuracy

---

**Document Version**: 1.0  
**Last Updated**: April 27, 2026  
**Status**: 🟢 Ready for Week 1 Implementation

