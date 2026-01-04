# 樣板方法模式 (Template Method Pattern)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 樣板方法 (Behavioral Pattern)

本手冊依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，闡述如何透過 Template Method 統一 Daily 與 Weekly 工作流的演算法骨架。

### 1. 願景與設計動機 (Problem & Goals - ADR-005)
- **挑戰**: DailyWorkflow 與 WeeklyWorkflow 存在 >60% 的重複程式碼（初始化、報告發送、日誌記錄等）。
- **決策**: 在 `BaseWorkflow` 中定義 `run()` 方法作為樣板。
- **目標**: 確保所有非同步任務具備一致的 [可觀測性與錯誤處理機制](測試與外部服務整合-Testing-External-Services)。

### 2. 情境對比 (Good vs. Bad)

#### ❌ 模式不當用 (Bad)
手動複製流程邏輯，容易導致漏掉步驟：
```python
class DailyWorkflow:
    def run(self):
        # 初始化、資料獲取、報告發送等邏輯全寫在此，與 WeeklyWorkflow 高度重複
        pass
```

#### ✅ 專業實作 (Good)
父類別控制流程，子類別僅實作變化點：
```python
# BaseWorkflow 定義骨架
def run(self):
    self.init_env()
    if self.should_analyze():
        report = self.execute_specific_logic() # Hook method
        self.dispatch_report(report)
```

### 3. 非功能性要求 (Workflow NFR)
- **彈性 (Resilience)**: 核心樣板必須包含 Retry 機制，詳見 [底層通信協議](底層通信協議-Agent-Mesh-Protocols)。
- **可觀測性 (Observability)**: 每個樣板步驟必須自動產生結構化日誌（Trace ID 流轉）。

---

<a id="en"></a>

## 🇺🇸 Template Method Pattern

### 1. Vision & Goals (ADR-005)
Standardize the "skeleton" of automated workflows while allowing Daily/Weekly variations in analysis logic.

### 2. Good vs. Bad Comparison
- **Bad**: Cloning boilerplate code across multiple workflow scripts, leading to maintenance debt.
- **Good**: Inheriting from `BaseWorkflow` ensures all tasks share the same robust error-handling and telemetry.

### 3. Workflow NFR
- **Reliability**: Auto-retry logic embedded in the base template.
- **Telemetry**: Mandatory step-level logging for all subclasses.

## 🔗 Bidirectional Links
- **Handbook Intro**: [設計模式導讀-Design-Patterns-Intro]
- **PM Specs**: [核心系統規格-Core-System-Specs]
- **Dev Guide**: [環境設定與本地開發-Environment-Local-Dev]
