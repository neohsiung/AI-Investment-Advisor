# 設計模式導讀 (Design Patterns Introduction)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 設計模式導讀 (Architectural Foundation)

本手冊依據 [文件框架定義](文件框架定義-Document-Frameworks) 編寫，旨在解釋本系統選擇特定設計模式的背後動機（ADR）及其帶來的技術優勢。

### 1. 架構願景與挑戰 (Problem & Vision)
- **挑戰**: AI 應用常因模型頻繁更新、資料庫切換與 Prompt 漂移而導致代碼腐化。
- **願景**: 建立一個「模型無關 (Model-Agnostic)」且「高可測試性 (Test-Driven)」的穩定系統。

### 2. 核心架構決策 (ADR - Architectural Decision Records)

| 編號 | 決策 (Decision) | 動機 (Problem) | 後果 (Consequence) |
| :--- | :--- | :--- | :--- |
| **ADR-001** | **Repository Pattern** | 原生 SQL 散落各處，難以進行 Unit Test。 | 資料庫與業務邏輯解耦，達成 >75% 覆蓋率。 |
| **ADR-002** | **Dependency Injection** | 靜態工廠導致類別間強耦合，難以 Mock。 | 可透過 [測試規範](測試與外部服務整合-Testing-External-Services) 輕鬆替換 LLM 與 DB。 |
| **ADR-003** | **Template Method** | Daily 與 Weekly Workflows 重複代碼率 > 60%。 | 流程骨架統一化，新增週期性任務僅需 5 分鐘。 |

### 3. 設計模式深度庫 (Pattern Deep Dives)
每一個模式都具備詳盡的 **Good vs. Bad** 對比與實作規範：
- **[工廠模式 (Factory Pattern)](設計模式_工廠-Factory-Pattern)**: 解決 Agent 初始化爆炸。
- **[存儲庫模式 (Repository Pattern)](設計模式_存儲庫-Repository-Pattern)**: 解決持久層方言問題。
- **[依賴注入 (DI Pattern)](設計模式_依賴注入-DI-Pattern)**: 解決可測試性問題。
- **[樣板方法 (Template Method)](設計模式_樣板方法-Template-Method)**: 解決流程重複問題。

---

<a id="en"></a>

## 🇺🇸 Design Patterns Introduction

### 1. Vision & Challenges
Our goal is to build a **Model-Agnostic** and **Test-Driven** AI Advisor. Design patterns are used to ensure long-term maintainability against fast-evolving AI trends.

### 2. Core ADRs
- **ADR-001 (Repository)**: Decoupling SQL for better unit testing.
- **ADR-002 (DI)**: Using constructor injection to enable easy Mocking of LLM responses.
- **ADR-003 (Template Method)**: Simplifying complex daily/weekly asynchronous workflows.

### 3. Deep Dive Series
- [Factory Pattern](設計模式_工廠-Factory-Pattern)
- [Repository Pattern](設計模式_存儲庫-Repository-Pattern)
- [DI Pattern](設計模式_依賴注入-DI-Pattern)
- [Template Method](設計模式_樣板方法-Template-Method)

## 🔗 Bidirectional Links
- **Standards**: [Database & Git Standards](資料庫設計與代碼規範-Database-Git-Standards)
- **Dev Guide**: [Local Dev Setup](環境設定與本地開發-Environment-Local-Dev)
- **PM Specs**: [Core System Specs](核心系統規格-Core-System-Specs)
