# 策略模式 (Strategy Pattern)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 策略模式 (Behavioral Pattern)

本文件說明如何透過 Strategy Pattern 實作可擴展的資料攝取與分析演算法切換。

### 1. 願景與設計動機 (Problem & Goals - ADR-006)
- **挑戰**: 投資資料來源多樣（CSV 交易紀錄、PDF 財報、網頁 URL），且每種來源的解析與驗證邏輯完全不同。
- **決策**: 將解析邏輯封裝為獨立的策略類別（Strategies）。
- **目標**: 支援「插拔式」攝取，新增資料格式時無須修改 `IngestionService` 主流程。

### 2. 情境對比 (Good vs. Bad)

````carousel
```python
# ❌ Before: 巨大的 If-Else (Mega-function)
def ingest(file):
    if file.endswith(".csv"):
        # 30 lines of CSV logic
    elif file.endswith(".pdf"):
        # 50 lines of PDF/OCR logic
```
<!-- slide -->
```python
# ✅ After: 策略分發 (詳見 src/data/ingestors/factory.py)
strategy = IngestorFactory.get_strategy(file_type)
strategy.process(file)
```
<!-- slide -->
> [!TIP]
> **維護性**: 
> 每個產生的具體策略（如 `EtoroCsvStrategy`）都具備獨立的單元測試，互不干擾。
````

### 3. 主要實作案例
- **資料攝取**: `IngestionService` 根據檔案後綴或標題選擇對應的 `BaseIngestor` 實作。
- **模型路由**: `LLMRouter` 根據任務複雜度決定使用 `flash` 或 `pro` 等級的推理策略。

---

<a id="en"></a>

## 🇺🇸 Strategy Pattern

### 1. Vision & Goals (ADR-006)
Encapsulate different algorithms or processing logics into separate classes to enable dynamic switching at runtime.

### 2. Real-world Examples
- **Data Ingestion**: Specific strategies for CSV parsing, PDF extraction, and URL scraping.
- **Model Toggling**: Switching between high-speed (Flash) and deep-reasoning (Pro) model strategies based on market volatility.

## 🔗 Bidirectional Links
- **Intro**: [Design Patterns Intro](設計模式導讀-Design-Patterns-Intro)
- **DB Standards**: [Database & Git Standards](資料庫設計與代碼規範-Database-Git-Standards)
- **Ingestion Service**: [Service Layer Blueprints](服務層開發指南-Service-Layer-Blueprints)
