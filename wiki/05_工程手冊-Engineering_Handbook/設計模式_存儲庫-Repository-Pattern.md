# 存儲庫模式 (Repository Pattern)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 存儲庫模式 (Persistence Pattern)

本文件依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，闡述如何透過 Repository 徹底隔離資料庫方言與業務邏輯。

### 1. 願景與設計動機 (Problem & Goals - ADR-001)
- **挑戰**: 業務邏輯中夾雜大量 SQL 語句，導致難以進行單元測試，且無法在 SQLite 與 PostgreSQL 間無縫切換。
- **決策**: 建立一個抽象介面（Abstract Base Class），定義 `get/save` 行為。
- **目標**: 支援「模型優先」開發，讓 Agent 視資料庫為記憶體中的集合。

### 2. 情境對比 (Good vs. Bad)

#### ❌ 模式不當用 (Bad)
業務邏輯直接耦合 SQL：
```python
def get_user_config(self):
    # SQL 語法散落在 Python 邏輯中，難以 Mock
    return self.db.execute("SELECT * FROM settings WHERE key=?", (k,)).fetchone()
```

#### ✅ 專業實作 (Good)
透過介面調用，語意清晰：
```python
# 業務端僅關心語意
config = self.repo.get_setting("api_key")
```

### 3. 非功能性要求 (Persistence NFR)
- **併發控制 (Concurrency)**: 針對 SQLite 必須處理 `Database is locked` 的重試邏輯，詳見 [環境設定](環境設定與本地開發-Environment-Local-Dev)。
- **ACID 規範**: 複雜匯入任務必須透過 `Repository` 的 Session 封裝，詳見 [資料庫規範](資料庫設計與代碼規範-Database-Git-Standards)。

---

<a id="en"></a>

## 🇺🇸 Repository Pattern

### 1. Vision & Goals (ADR-001)
Hide the details of SQL/NoSQL storage behind a "Collection-oriented" interface. This enables seamless switching between SQLite and PostgreSQL.

### 2. Good vs. Bad Comparison
- **Bad**: SQL strings mixed with business reasoning, preventing effective unit testing.
- **Good**: Type-hinted methods returning Pydantic models, decoupling the domain from the DB.

### 3. Persistence NFR
- **Atomic Operations**: Mandatory transaction wrapping for bulk imports.
- **Mockability**: Interfaces must allow 100% memory-based testing.

## 🔗 Bidirectional Links
- **Standards**: [Database & Git Standards](資料庫設計與代碼規範-Database-Git-Standards)
- **Architect View**: [System Landscape](系統全景圖-System-Landscape)
- **DI Pattern**: [Dependency Injection](設計模式_依賴注入-DI-Pattern)
