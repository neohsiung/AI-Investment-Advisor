# 工廠模式 (Factory Pattern)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 工廠模式 (Creational Pattern)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，詳細說明 `AgentFactory` 如何解決 Agent 初始化爆炸與依賴管理問題。

### 1. 願景與設計動機 (Problem & Goals - ADR-003)
- **挑戰**: 每個 Agent (Momentum, Macro, CIO) 都有複雜且重疊的初始化邏輯（如 Prompt 路徑檢查、Cache 設定等）。
- **決策**: 實作一個中心化的 `AgentFactory`。
- **目標**: 達成物件創建與使用的完全解耦，並支持 [環境設定](環境設定與本地開發-Environment-Local-Dev) 的一鍵實例化。

### 2. 情境對比 (Good vs. Bad)

#### ❌ 模式不當用 (Bad)
直接調用建構子，導致依賴洩漏：
```python
# 業務邏輯中夾雜路徑管理與依賴實例化
agent = MomentumAgent(
    prompt_path="prompts/momentum_agent.txt",
    settings_repo=SqliteSettingsRepository(),
    use_cache=True
)
```

#### ✅ 專業實作 (Good)
透過工廠封裝所有黑盒細節：
```python
# Client 端極簡化
agent = AgentFactory.create_momentum_agent(user_id="user123")
```

### 3. 非功能性要求 (Performance & Flexibility)
- **初始化性能**: 每個 Agent 創建耗時目標 < 10ms。
- **靈活性**: 工廠支持透過 `kwargs` 覆蓋預設 [LLM 分級設定](底層通信協議-Agent-Mesh-Protocols)。

---

<a id="en"></a>

## 🇺🇸 Factory Pattern

### 1. Vision & Goals (ADR-003)
Encapsulate complex agent dependencies (Prompts, Repos, Caches) within a single entry point: `AgentFactory`.

### 2. Good vs. Bad Comparison
- **Bad**: Deeply nested constructor calls inside business logic, leaking path constants and DB details.
- **Good**: `AgentFactory.create_...()` hides all boilerplate, facilitating easier refactoring.

### 3. Performance & NFR
- **Latency**: Sub-10ms instantiation.
- **Flexibility**: Runtime override of model tiers for testing.

## 🔗 Bidirectional Links
- **Intro**: [Design Patterns Intro](設計模式導讀-Design-Patterns-Intro)
- **DI Pattern**: [Dependency Injection](設計模式_依賴注入-DI-Pattern)
- **Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
