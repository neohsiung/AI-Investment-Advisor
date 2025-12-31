# 樣板方法模式 (Template Method Pattern)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 樣板方法模式 (Template Method Pattern)

### 1. 我們遇到了什麼問題？ (The Problem)

> **"Defines the skeleton of an algorithm in the superclass but lets subclasses override specific steps of the algorithm without changing its structure."** — *GoF*

我們需要實作 `DailyWorkflow` (日報) 和 `WeeklyWorkflow` (週報)。這兩者有 80% 的流程是一樣的：

### 什麼是 Template Method?
Template Method 是一種 **行為型模式**。它解決了 "兩個流程大同小異，只有特定步驟不同" 的問題。透過在父類別定義 `run()` (樣板)，並預留 `abstractmethod` 或 `hook` 給子類別實作，達到代碼復用。

### 業界應用案例 (Real World Examples)
1.  **Airflow DAGs**: 定義通用的 Operator 流程，讓不同的 DAG 繼承並填入具體 Task。
2.  **Django Class Based Views**: `ListView` 定義了 `get_queryset` -> `get_context_data` -> `render` 的標準流程。
3.  **Unittest**: Python 的 `unittest` 使用 `setUp` -> `test` -> `tearDown` 的固定樣板。
1.  準備資料 (初始化 DB, 載入 User)。
2.  執行分析 (日報跑動能，週報跑總經)。
3.  綜合結果。
4.  發送 Email 或儲存報告。

#### ❌ 重構前 (Before)
如果我們寫兩個獨立的 class，會有大量重複的代碼 (Code Duplication)，例如 Error Handling、Logging、Email 發送邏輯。一旦邏輯要改 (例如 Email 標題格式調整)，要改兩個地方，容易漏掉。

### 2. 我們選擇了什麼模式？ (The Solution)

我們選擇了 **Template Method Pattern**。在父類別中定義演算法的 "骨架" (Skeleton)，將具體步驟延遲到子類別中實作。

#### ✅ 重構後 (After)

父類別 (`BaseWorkflow`):
```python
class BaseWorkflow(ABC):
    def run(self):
        # 1. 通用步驟
        self.collect_data() 
        
        # 2. 變化步驟 (Hook Method)
        if self.execute_analysis(): 
            
            # 3. 變化步驟
            report = self.synthesize_results()
            
            # 4. 通用步驟
            self.distribute_report(report)
```

子類別 (`WeeklyWorkflow`):
```python
class WeeklyWorkflow(BaseWorkflow):
    def execute_analysis(self):
        # 只有這裡不同：執行總經分析
        self.macro_agent.run(...)
        return True
```

### 3. 為什麼選擇 Template Method？ (Why?)

| 評估維度 | 樣板方法的優勢 |
| :--- | :--- |
| **代碼復用 (Reuse)** | 錯誤處理、日誌記錄、基礎設施連接等代碼只寫一次。 |
| **強制結構 (Structure)** | 強制所有 Workflow 都要遵循標準流程 (Init -> Analyze -> Report)，避免開發者漏掉步驟。 |
| **易於擴展 (Extensible)** | 未來若要加入 `MonthlyWorkflow`，只需專注於分析邏輯即可。 |

### 4. 學習資源 (References)
- [Refactoring.guru - Template Method](https://refactoring.guru/design-patterns/template-method)
- `src/services/workflow_service.py` (本專案原始碼)

## 🔗 相關連結 (See Also)
- [設計模式導讀](設計模式導讀-Design-Patterns-Intro)
- [系統概觀 (System Overview)](系統概觀-System-Overview)

---

<a id="en"></a>

## 🇺🇸 Template Method Pattern

### 1. The Problem

We needed to implement `DailyWorkflow` and `WeeklyWorkflow`. They share 80% of the process:
1.  Prepare data (Init DB, Load User).
2.  Execute Analysis (Daily runs Momentum, Weekly runs Macro).
3.  Synthesize Results.
4.  Distribute Report (Email/Save).

#### ❌ Before Refactoring
Writing two independent classes led to massive **Code Duplication** (Error handling, Logging, Email logic). Changing logic (e.g., Email subject format) required updates in two places, leading to bugs.

### 2. The Solution

We chose the **Template Method Pattern**. We define the "skeleton" of the algorithm in a base class and defer specific steps to subclasses.

#### ✅ After Refactoring

Base Class (`BaseWorkflow`):
```python
class BaseWorkflow(ABC):
    def run(self):
        # 1. Common Step
        self.collect_data() 
        
        # 2. Variant Step (Hook Method)
        if self.execute_analysis(): 
            
            # 3. Variant Step
            report = self.synthesize_results()
            
            # 4. Common Step
            self.distribute_report(report)
```

Subclass (`WeeklyWorkflow`):
```python
class WeeklyWorkflow(BaseWorkflow):
    def execute_analysis(self):
        # Only this part differs: Run Macro Analysis
        self.macro_agent.run(...)
        return True
```

### 3. Why Template Method?

| Dimension | Advantages of Template Method |
| :--- | :--- |
| **Reuse** | Write Error handling/Logging once. |
| **Structure** | Enforces a standard process (Init -> Analyze -> Report) for all workflows. |
| **Extensibility** | Adding `MonthlyWorkflow` only requires focusing on the analysis logic. |

### 4. References
- [Refactoring.guru - Template Method](https://refactoring.guru/design-patterns/template-method)
- `src/services/workflow_service.py` (Source Code)
