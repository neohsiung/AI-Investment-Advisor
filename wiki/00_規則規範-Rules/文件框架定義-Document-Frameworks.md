# 文件框架定義 | Document Frameworks

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


本文件定義了 Wiki 中各類文檔的詳細結構標準，確保所有內容達到專業產品規格 (Product Spec) 的深度。

This document defines the detailed structural standards for each category in the Wiki, ensuring all content reaches professional Product Spec depth.
It also mandates the inclusion of a specialized "Iteration Record" for tracking major document updates.

---

## 0. 通用規範 (General Standards)

所有類型文件均需包含：
*   **版本紀錄 (Iteration Record)**: 位於文件頂部，記錄最近 5 次迭代原因與內容。**每次變動文件（不論大小）均必須新增一筆紀錄。** (Mandatory entry for every change).
*   **微幅增量原則 (Incremental Updates)**: 除非文件結構完全崩壞或過時，否則應優先在現有框架下進行微調與資料新增，**嚴禁隨意進行大範圍重寫**。必須找到最合適的插入點以保留歷史脈絡。 (Minimize major rewrites; prefer surgical additions to preserve context).
*   **雙語並列 (Bilingual Structure)**: 中文在上，英文在下。

---

## 1. 產品規格書 (PM Department - Product Specs)
適用於：核心系統規格、未來演進規格。

| 章節 (Section) | 內容描述 (Description) |
| :--- | :--- |
| **問題與目標 (Problem & Goals)** | 解決什麼痛點？業務目標是什麼？ (What problem does it solve? Business objectives?) |
| **功能描述 (Features & Functionality)** | 詳細的功能邏輯、狀態機、處理流程。 (Detailed logic, state machines, processing flows.) |
| **用戶體驗 (UX & User Stories)** | **核心：** 完整的 User Flow，包含每個步驟的操作細節與欄位定義。 (Complete User Flow with step-by-step operation details and field definitions.) |
| **技術要求 (Technical Requirements)** | 架構設計、資料模型 (DB Schema)、API 定義、性能需求與安全規範。 (Architecture, Data models, APIs, performance, security.) |
| **非功能性需求 (Non-Functional)** | 可擴展性、兼容性、無障礙性、災難復原。 (Scalability, compatibility, accessibility, DR.) |
| **成功指標 (Success Metrics)** | 如何衡量成功？ (KPIs, engagement, precision metrics.) |
| **時程與預算 (Timeline & Budget)** | 階段性開發時程與資源評估。 (Project schedule and cost logic.) |

---

## 2. 開發者指南 (Dev Department - Developer Guide)
適用於：環境設定、資料庫設計、代碼規範。

- **快速導航 (Quick Nav)**: 5 分鐘跑起來的步驟。
- **架構深挖 (Deep Dive)**: 核心模組的設計模式 (Design Patterns) 與 UML。
- **最佳實踐 (Best Practices)**: 引用外部來源 (e.g., Google/Uber Style Guides) 的代碼標準。
- **引用與來源 (References)**: 每個技術決策的 RFC 或外部引用。

---

## 3. 架構觀點 (Architect Views)
適用於：系統全景圖、通信協議。

- **C4 模型 (C4 Model)**: Context, Container, Component, Code。
- **通信協議 (Protocols)**: 詳細的 Request/Response 結構、錯誤處理 (Retries, Circuit Breaker)。
- **基礎設施 (Infrastructure)**: Docker/K8s 配置邏輯、快取策略。

---

## 4. 使用者手冊 (User Manual)
適用於：快速啟動、操作指南、疑難排解。

- **任務驅動 (Task-Oriented)**: 以「我想要...」開始的操作路徑。
- **欄位手冊 (Field Glossary)**: UI 上每個輸入框、顯示值的詳細解釋。
- **視覺化引導**: 截圖與標註。

---

## 5. 變更紀錄 (Technical Decision Records - ADR)
適用於：所有架構決策。

- **背景 (Context)**: 為什麼要做這個決定？
- **方案對比 (Alternatives)**: 考慮過哪些方案？為什麼放棄？
- **後果 (Consequences)**: 採用的代價與獲益。
