# 工廠模式 (Factory Pattern)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 工廠模式 (Factory Pattern)

### 1. 我們遇到了什麼問題？ (The Problem)

> **"Factories decouple the creation of objects from their usage."** — *Real Python*

在 v3.0 版本初期，要創建一個 `MomentumAgent` (動能分析師) 非常麻煩。你需要知道它依賴哪些組件，還需要正確設定 `Prompts` 的路徑、`ResponseCache` 的 TTL 時間以及 `User ID`。

### 什麼是 Factory Pattern? (What is Factory Pattern?)
工廠模式是一種 **創建型模式 (Creational Pattern)**。它提供了一種創建對象的介面，但允許子類別決定實例化哪一個類別。在 Python 中，它常被用來解決 "複雜初始化邏輯散落在各處" 的問題。

### 業界應用案例 (Real World Examples)
1.  **Game Development**: 根據玩家輸入動態生成 `Orc`, `Elf`, `Dragon` 等不同屬性的敵人實例。
2.  **Payment Gateways**: 根據地區自動選擇創建 `StripePayment`, `PayPalPayment` 或 `ECPayPayment` 物件。
3.  **Data Exporters**: 根據用戶選擇傳回 `PDFExporter`, `CSVExporter` 或 `JSONExporter`。

#### ❌ 重構前 (Before)
在 `WorkflowService` 或測試程式碼中，我們經常看到這樣的程式碼：

```python
# 散落在各處的初始化邏輯
prompt_path = "prompts/momentum_agent.txt"
if not os.path.exists(prompt_path):
    raise Error(...)

# 為了測試還要手動管理 Cache
cache = ResponseCache(ttl_hours=24) 

# Strong Coupling: 直接依賴具體類別
agent = MomentumAgent(
    name="Momentum", 
    prompt_path=prompt_path, 
    user_id="user123", 
    cache=cache
)
```

這導致了：
1.  **重複代碼**: 每個使用 Agent 的地方都要寫這堆初始化邏輯。
2.  **修改困難**: 如果 `MomentumAgent` 新增了一個參數 (例如 `state_repo`)，所有調用點都要改。
3.  **依賴洩漏**: Client 用戶端被迫知道 `prompt_path` 的具體位置。

### 2. 我們選擇了什麼模式？ ( The Solution)

我們選擇了 **Static Factory Method (靜態工廠方法)** 模式。創建一個專門的 `AgentFactory` 類別，負責封裝所有 Agent 的創建細節。

#### ✅ 重構後 (After)

```python
# Client 只需要一句話
agent = AgentFactory.create_momentum_agent(user_id="user123")
```

`AgentFactory` 內部實作：

```python
class AgentFactory:
    @staticmethod
    def create_momentum_agent(user_id, use_cache=True, ttl_hours=24):
        # 1. 集中管理路徑
        prompt_path = os.path.join("prompts", "momentum_agent.txt")
        
        # 2. 自動處理依賴注入
        settings_repo = SqliteSettingsRepository()
        
        # 3. 返回實例
        return MomentumAgent(
            name="Momentum",
            prompt_path=prompt_path,
            user_id=user_id,
            settings_repo=settings_repo,
            use_cache=use_cache,
            ttl_hours=ttl_hours
        )
```

### 3. 為什麼選擇 Factory？ (Why?)

| 評估維度 | 工廠模式的優勢 |
| :--- | :--- |
| **封裝性 (Encapsulation)** | 隱藏了 Agent 複雜的創建過程 (路徑、依賴、設定)。 |
| **一致性 (Consistency)** | 確保全系統創建出的 Agent 設定一致 (例如預設 TTL)。 |
| **解耦 (Decoupling)** | Client 不再直接 `new Agent()`，只依賴 Factory 介面。 |

### 4. 學習資源 (References)
- [Refactoring.guru - Factory Method](https://refactoring.guru/design-patterns/factory-method)
- `src/agents/factory.py` (本專案原始碼)

## 🔗 相關連結 (See Also)
- [設計模式導讀](設計模式導讀-Design-Patterns-Intro)
- [依賴注入 (Dependency Injection)](設計模式_依賴注入-Dependency-Injection)

---

<a id="en"></a>

## 🇺🇸 Factory Pattern

### 1. The Problem

In the early stages of v3.0, creating a `MomentumAgent` was cumbersome. You needed to know its dependencies, configure correct `Prompts` paths, set `ResponseCache` TTL, and pass the `User ID`.

#### ❌ Before Refactoring
In `WorkflowService` or test code, we often saw:

```python
# Scattered initialization logic
prompt_path = "prompts/momentum_agent.txt"
if not os.path.exists(prompt_path):
    raise Error(...)

# Manual cache management for testing
cache = ResponseCache(ttl_hours=24) 

# Strong Coupling: Direct dependency on concrete class
agent = MomentumAgent(
    name="Momentum", 
    prompt_path=prompt_path, 
    user_id="user123", 
    cache=cache
)
```

This led to:
1.  **Code Duplication**: Initialization logic repeated everywhere.
2.  **Maintenance Issues**: Adding a parameter (e.g., `state_repo`) required changing all call sites.
3.  **Dependency Leak**: Clients were forced to know implementation details like `prompt_path`.

### 2. The Solution

We chose the **Static Factory Method** pattern. We created a dedicated `AgentFactory` class to encapsulate all agent creation details.

#### ✅ After Refactoring

```python
# Client needs just one line
agent = AgentFactory.create_momentum_agent(user_id="user123")
```

Inside `AgentFactory`:

```python
class AgentFactory:
    @staticmethod
    def create_momentum_agent(user_id, use_cache=True, ttl_hours=24):
        # 1. Centralized path management
        prompt_path = os.path.join("prompts", "momentum_agent.txt")
        
        # 2. Automated Dependency Injection
        settings_repo = SqliteSettingsRepository()
        
        # 3. Return instance
        return MomentumAgent(
            name="Momentum",
            prompt_path=prompt_path,
            user_id=user_id,
            settings_repo=settings_repo,
            use_cache=use_cache,
            ttl_hours=ttl_hours
        )
```

### 3. Why Factory?

| Dimension | Advantages of Factory Pattern |
| :--- | :--- |
| **Encapsulation** | Hides complex creation process (paths, deps, config). |
| **Consistency** | Ensures consistent agent configuration system-wide (e.g., default TTL). |
| **Decoupling** | Client relies on Factory interface, not concrete `new Agent()`. |

### 4. References
- [Refactoring.guru - Factory Method](https://refactoring.guru/design-patterns/factory-method)
- `src/agents/factory.py` (Source Code)
