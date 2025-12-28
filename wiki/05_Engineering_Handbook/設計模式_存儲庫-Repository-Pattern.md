# 存儲庫模式 (Repository Pattern)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 存儲庫模式 (Repository Pattern)

### 1. 我們遇到了什麼問題？ (The Problem)

在早期版本中，我們的業務邏輯層 (Agents & Services) 直接包含了 SQL 查詢語句。

#### ❌ 重構前 (Before)
`SystemEngineerAgent` 中直接寫 SQL：

```python
def check_performance(self):
    conn = get_db_connection()
    # 業務邏輯與 SQL 糾纏不清
    rows = conn.execute("SELECT outcome_score FROM recommendations WHERE date > '2023-01-01'").fetchall()
    # ... 計算邏輯
```

這導致了：
1.  **無法測試**: 為了測試 `check_performance`，我們必須準備一個真實的資料庫，或者極其痛苦地 Mock `get_db_connection`。
2.  **資料庫綁定**: 如果想從 SQLite 遷移到 PostgreSQL，所有 SQL 語句都要檢查一遍 (語法差異)。
3.  **語意不明**: `SELECT ...` 沒有表達出 "查詢最近績效" 的業務意圖。

### 2. 我們選擇了什麼模式？ (The Solution)

我們採用 **Repository Pattern**，在業務邏輯與數據層之間建立一個抽象層。Repository 就像一個 "記憶體中的物件集合"，讓業務邏輯感覺不到資料庫的存在。

#### ✅ 重構後 (After)

Client Code (Agent):
```python
# 語意清晰，看不到 SQL
scores = self.repo.get_recent_scores(days=30)
```

Repository 實作 (`src/repositories/recommendation_repository.py`):
```python
class SqliteRecommendationRepository:
    def get_recent_scores(self, days):
        date_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        # SQL 藏在這裡
        return self.conn.execute(..., {"date": date_limit})
```

### 3. 為什麼選擇 Repository？ (Why?)

| 評估維度 | Repository 模式的優勢 |
| :--- | :--- |
| **可測試性 (Testability)** | 這是最大的好處。我們可以輕鬆創建一個 `MockRepo` 來進行單元測試。 |
| **單一職責 (SRP)** | Agent 專注於分析，Repository 專注於存取。 |
| **易於切換 (Switchable)** | 支援同時存在 `SqliteRepo` 和 `PostgresRepo`，透過設定切換。 |

### 4. 學習資源 (References)
- [Microsoft - Repository Pattern](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/infrastructure-persistence-layer-design)
- `src/repositories/` (本專案原始碼)

## 🔗 相關連結 (See Also)
- [設計模式導讀](wiki/05_Engineering_Handbook/設計模式導讀-Design-Patterns-Intro.md)
- [依賴注入 (Dependency Injection)](wiki/05_Engineering_Handbook/設計模式_依賴注入-Dependency-Injection.md)
- [資料層定義 (Data Layer)](wiki/02_Product_Manager_Corner/Specs/資料層定義-Data-Layer.md)

---

<a id="en"></a>

## 🇺🇸 Repository Pattern

### 1. The Problem

In early versions, our business logic layer (Agents & Services) contained direct SQL queries.

#### ❌ Before Refactoring
Direct SQL usage in `SystemEngineerAgent`:

```python
def check_performance(self):
    conn = get_db_connection()
    # Business logic entangled with SQL
    rows = conn.execute("SELECT outcome_score FROM recommendations WHERE date > '2023-01-01'").fetchall()
    # ... calculation logic
```

This led to:
1.  **Untestability**: Testing `check_performance` required a real DB or painful mocking of connections.
2.  **Database Coupling**: Migrating to PostgreSQL required rewriting SQL queries due to syntax differences.
3.  **Unclear Semantics**: `SELECT ...` does not express the intent "get recent performance".

### 2. The Solution

We adopted the **Repository Pattern** to create an abstraction layer between business logic and data. The Repository acts like an "in-memory collection of objects," hiding database details.

#### ✅ After Refactoring

Client Code (Agent):
```python
# Clear intent, no SQL visible
scores = self.repo.get_recent_scores(days=30)
```

Repository Implementation (`src/repositories/recommendation_repository.py`):
```python
class SqliteRecommendationRepository:
    def get_recent_scores(self, days):
        date_limit = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        # SQL is hidden here
        return self.conn.execute(..., {"date": date_limit})
```

### 3. Why Repository?

| Dimension | Advantages of Repository Pattern |
| :--- | :--- |
| **Testability** | The biggest benefit. We can easily create a `MockRepo` for unit testing. |
| **Single Responsibility (SRP)** | Agent focuses on analysis, Repository focuses on access. |
| **Switchability** | Supports co-existence of `SqliteRepo` and `PostgresRepo` via configuration. |

### 4. References
- [Microsoft - Repository Pattern](https://learn.microsoft.com/en-us/dotnet/architecture/microservices/microservice-ddd-cqrs-patterns/infrastructure-persistence-layer-design)
- `src/repositories/` (Source Code)
