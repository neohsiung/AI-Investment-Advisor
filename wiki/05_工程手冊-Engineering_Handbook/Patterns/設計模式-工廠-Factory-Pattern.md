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

````carousel
```python
# ❌ Before: 手動分散創建 (分散在 WorkflowService)
agent = MomentumAgent(
    name="Momentum",
    prompt_path="prompts/momentum.txt",
    user_id=uid,
    repo=SqliteRepo()
)
```
<!-- slide -->
```python
# ✅ After: 透過工廠統一生產
# 詳見 src/agents/factory.py
agent = AgentFactory.create_momentum_agent(user_id=uid)
```
<!-- slide -->
> [!TIP]
> **為什麼好？**: 
> 1. 初始化邏輯（如加載 Prompt 路徑）被封裝在單一位置。
> 2. 變更依賴（例如換成 PostgresRepo）只需修改工廠，不影響調用端。
````

### 3. 非功能性要求 (Scalability)
- **並行初始化**: `AgentFactory` 必須支援線程安全，確保在高並發場景下不會重複加載 Prompt 文件，詳見 [環境設定](環境設定與本地開發-Environment-Local-Dev)。

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
