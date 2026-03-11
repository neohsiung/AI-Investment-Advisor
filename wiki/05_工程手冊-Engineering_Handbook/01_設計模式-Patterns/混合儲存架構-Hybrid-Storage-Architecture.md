# 混合儲存架構 (Hybrid Storage Architecture)

本文件詳細說明專案中針對不同資料特性所採用的 **混合儲存策略 (Hybrid Storage Strategy)**。透過結合 SQLAlchemy ORM 與 Raw SQL (SQLAlchemy Core)，我們能在開發效率、系統效能與查詢靈活性之間取得最佳平衡。

## 1. 架構總覽 (Architecture Overview)

本專案將資料庫操作劃分為兩個主要層級：
- **ORM 管理層 (ORM Admin Layer)**: 處理結構簡單、關聯性強且操作頻率低的實體 (如使用者配置、系統設定、系統日誌)。
- **高效能數據層 (Raw SQL Performance Layer)**: 處理高併發寫入、巨量歷史資料讀取、複雜向量搜尋等場景 (如市場行情、金融時間序列、Agent 效能指標、向量知識庫)。

```mermaid
graph TD
    A[Application Services] --> B{Storage Strategy}
    
    B -->"|User, Settings, Logs| C[ORM Admin Layer<br>SQLAlchemy ORM]"
    B -->"|Market Data, Vectors, Analytics| D[Performance Layer<br>Raw SQL / Core]"
    
    C -->"E[""(SQLite / PostgreSQL")]
    D --> E
    
    classDef orm fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef raw fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    
    class C orm;
    class D raw;
```

---

## 2. 核心技術比較 (ORM vs Raw SQL)

以下為本專案中兩大技術路線的優缺點分析與適用場景：

| 特性 / 技術 | SQLAlchemy ORM | Raw SQL (SQLAlchemy Core) / Safe-SQL |
| :--- | :--- | :--- |
| **定義** | 透過 Python 類別 (Class) 映射資料表結構。 | 直接使用 SQL 語法字串，並搭配參數化查詢 (`:param`)。 |
| **主要優點** | 1. **開發極快**: 內建 CRUD，程式碼具備高可讀性。<br>2. **關聯處理**: 輕鬆處理一對多、多對多關聯 (`relationship`)。<br>3. **自動遷移**: 結合 Alembic 容易進行 Schema 管理。 | 1. **極致效能**: 繞過物件實例化開銷，適合海量資料批次插入 (Batch Insert)。<br>2. **豐富語法**: 可徹底發揮 PostgreSQL 專屬特性 (如 Window Functions, CTE, `pgvector`)。<br>3. **記憶體極低**: 讀取時不需轉換為龐大的 ORM 物件。 |
| **主要缺點** | 1. **效能瓶頸**: 大量迴圈生成物件 (N+1 Query Issue) 時極度消耗記憶體與 CPU。<br>2. **隱蔽的查詢**: 自動生成的 SQL 有時並非最佳化，針對複雜查詢難以介入調整。 | 1. **維護成本**: SQL 語意分散，需開發者確保 Schema 與 SQL 同步。<br>2. **資安風險**: 若未使用參數化查詢，存在 SQL Injection 風險。 |
| **本案適用場景** | **使用者設定 (Settings)、全域配置、Webhook 金鑰管理、系統狀態監控紀錄。** | **歷史 K 線資料 (Transactions)、即時報價快取、向量相似度搜尋 (`pgvector`)、Agent 效能聚合指標。** |

---

## 3. 實務範例與規範 (Implementation Guidelines)

根據 [Rule #10 (Safe-SQL-Only)](engineering-standards)，在撰寫 Raw SQL 時，**嚴禁使用 f-string 或字串拼接**。必須使用參數化綁定：

### ❌ 錯誤示範 (SQL Injection 風險)
```python
# 嚴禁用於 Raw SQL Performance Layer
ticker = "AAPL"
query = f"SELECT * FROM market_data WHERE ticker = '{ticker}'"
cursor.execute(query)
```

### ✅ 正確示範 (Safe-SQL)
```python
from sqlalchemy import text

# 使用 named parameters (:ticker)
query = text("SELECT * FROM market_data WHERE ticker = :ticker ORDER BY date DESC LIMIT 100")
result = session.execute(query, {"ticker": "AAPL"}).fetchall()
```

### ✅ SQLAlchemy ORM 範例 (Admin Layer)
```python
# 適用於設定存取
user_setting = session.query(Settings).filter(Settings.key == "SLACK_WEBHOOK").first()
user_setting.value = "https://hooks.slack.com/..."
session.commit()
```

## 4. 總結 (Conclusion)
混合儲存架構確保了 Advisor 在面對高頻的歷史回測與行情分析時，不會被 ORM 的效能拖垮；同時在開發管理後台 UI 時，能享有高度封裝的便捷性。開發者應在規劃階段，依據資料吞吐量與關聯複雜度，為新的 Entity 選擇合適的儲存層級。
