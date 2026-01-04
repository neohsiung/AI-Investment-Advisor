# 依賴注入 (Dependency Injection)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 依賴注入 (Dependency Injection)

### 1. 我們遇到了什麼問題？ (The Problem)

> **"Dependency Injection is a technique whereby one object supplies the dependencies of another object."** — *Martin Fowler*

#### ❌ 重構前 (Before)
在早期的 Agent 設計中，Agent "知道太多了"。它知道要使用 `SqliteSettingsRepository`，並且知道如何實例化它。

### 什麼是 Dependency Injection? (What is DI?)
DI 是一種 **控制反轉 (IoC)** 的實踐。物件不再負責創建自己的依賴，而是由外部 (Assembler/Container) 注入。這極大提升了模組的獨立性。

### 著名的 Python DI 框架
1.  **Dependency Injector**: 結構嚴謹，提供 Container 與 Providers，適合大型專案。
2.  **Injector**: 類似 Java Guice 的風格。
3.  **FastAPI Depends**: 現代 Web 框架內建的 DI 系統，極大簡化了 Request Scope 的依賴管理。

```python
class BaseAgent:
    def __init__(self, ...):
        # ❌ Hardcoded Dependency (硬編碼依賴)
        self.settings_repo = SqliteSettingsRepository()
```

這導致了：
1.  **測試惡夢**: 單元測試時，我們希望注入一個 "假" 的設定庫 (MockSettingsRepo)，但程式碼寫死了 Sqlite 版本，導致測試會真的去讀寫資料庫，速度慢且容易失敗。
2.  **違反 DIP**: Agent (高層模組) 依賴了 SqliteRepo (低層模組)。應該兩者都依賴抽象介面。

### 2. 我們選擇了什麼模式？ (The Solution)

我們選擇了 **Constructor Injection (建構子注入)**。這意味著 Agent 不再自己創建依賴，而是 "請求" 外部將依賴傳進來。

#### ✅ 重構後 (After)

```python
class BaseAgent:
    # 透過參數傳入，預設值僅作為便利 (Composability)
    def __init__(self, settings_repo=None, ...):
        self.settings_repo = settings_repo or SqliteSettingsRepository()
```

測試程式碼現在可以這樣寫：

```python
# 測試可以輕鬆注入假的 Repo
mock_repo = Mock(spec=SettingsRepository)
agent = BaseAgent(settings_repo=mock_repo)
```

### 3. 為什麼選擇 DI？ (Why?)

| 評估維度 | 依賴注入的優勢 |
| :--- | :--- |
| **鬆耦合 (Loose Coupling)** | Agent 不再綁定任何具體的資料庫實作。 |
| **可測試性 (Testability)** | 用 Mock 替換真物件變得輕而易舉。 |
| **並行開發 (Parallel Dev)** | 一個人寫 Agent 邏輯，一個人寫 Repository 實作，介面定義好即可互不干擾。 |

### 4. 學習資源 (References)
- [Python Dependency Injection Guide](https://python-dependency-injector.ets-labs.org/introduction/di_in_python.html)
- `src/agents/base_agent.py` (本專案原始碼)

## 🔗 相關連結 (See Also)
- [設計模式導讀](設計模式導讀-Design-Patterns-Intro)
- [工廠模式 (Factory Pattern)](設計模式_工廠-Factory-Pattern)
- [存儲庫模式 (Repository Pattern)](設計模式_存儲庫-Repository-Pattern)

---

<a id="en"></a>

## 🇺🇸 Dependency Injection

### 1. The Problem

#### ❌ Before Refactoring
In early Agent designs, the Agent "knew too much." It knew it had to use `SqliteSettingsRepository` and how to instantiate it.

```python
class BaseAgent:
    def __init__(self, ...):
        # ❌ Hardcoded Dependency
        self.settings_repo = SqliteSettingsRepository()
```

This led to:
1.  **Testing Nightmare**: During unit testing, we wanted to inject a "fake" repository (`MockSettingsRepo`). But since the SQLite implementation was hardcoded, tests hit the real database—slow and brittle.
2.  **DIP Violation**: Agents (High-level module) depended on SqliteRepo (Low-level module). Both should depend on abstractions.

### 2. The Solution

We chose **Constructor Injection**. This means the Agent no longer creates its own dependencies but "requests" them to be passed in from the outside.

#### ✅ After Refactoring

```python
class BaseAgent:
    # Passed via parameters
    def __init__(self, settings_repo=None, ...):
        self.settings_repo = settings_repo or SqliteSettingsRepository()
```

Test code can now be written as:

```python
# Easily inject a mock repo
mock_repo = Mock(spec=SettingsRepository)
agent = BaseAgent(settings_repo=mock_repo)
```

### 3. Why DI?

| Dimension | Advantages of Dependency Injection |
| :--- | :--- |
| **Loose Coupling** | Agents are not bound to any specific Database implementation. |
| **Testability** | Replacing real objects with Mocks becomes trivial. |
| **Parallel Dev** | One dev works on Agent logic, another on Repository implementation. |

### 4. References
- [Python Dependency Injection Guide](https://python-dependency-injector.ets-labs.org/introduction/di_in_python.html)
- `src/agents/base_agent.py` (Source Code)
