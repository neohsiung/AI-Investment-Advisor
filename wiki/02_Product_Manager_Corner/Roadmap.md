# 專案藍圖 (Project Roadmap)

> 返回 [[Home]]

## 目標 (Goal)
清晰規劃專案的長期發展方向，確保資源投入在最具價值的優化項目上，並提供開發團隊明確的執行指引。

## 為什麼 (Why)
- **持續迭代**: 投資市場與 AI 技術瞬息萬變，系統需持續進化。
- **品質控管**: 透過規劃 Clean Architecture 重構與測試覆蓋率，償還技術債。
- **透明溝通**: 讓所有利害關係人了解下一個里程碑。

## 做了什麼 (What)
我們將未來的開發計畫分為四大階段：架構優化、雲端遷移、Agent 增強與社群開源。目前已完成 v1.0.0 的核心功能開發與 SaaS 架構轉型。

## 如何進行 (How)

### 🟢 Phase 1: 架構重構 (Refactoring)
*目標：提升程式碼可測試性與模組化。*
- [ ] **Repository Pattern 實作**: 將數據存取層 (Data Access) 與業務邏輯完全分離。
- [ ] **Dependency Injection**: 導入依賴注入容器，解耦 Service 與 Agent。
- [ ] **Domain-Driven Design (DDD)**: 重新定義 Entity 與 Value Object，強化業務邏輯核心。

### 🔵 Phase 2: 效能與擴展 (Scalability)
*目標：支援更多使用者與更大量數據。*
- [ ] **AlloyDB / Cloud SQL 優化**: 導入 Connection Pooling 與 Read Replica。
- [ ] **Redis 快取層**: 快取熱門的市場數據與即時股價，減少外部 API 呼叫。
- [ ] **Celery / Cloud Tasks**: 將耗時的 AI 分析任務從主執行緒分離，改為異步隊列處理。

### 🟣 Phase 3: AI 智慧增強 (AI Enhancement)
*目標：提供更精確且個人化的投資建議。*
- [ ] **RAG (Retrieval-Augmented Generation)**: 整合向量資料庫，讓 Agent 能檢索歷史財報與新聞。
- [ ] **User Persona Learning**: 根據使用者的操作行為 (查看哪些股票、風險偏好)，動態調整 Prompt。
- [ ] **Multi-Agent Debate**: 引入「辯論模式」，讓 Bull/Bear Agent 互相挑戰觀點。

### 🟠 Phase 4: 開源與社群 (Open Source)
*目標：建立生態系與貢獻者社群。*
- [ ] **Plugin System**: 開放介面，允許開發者撰寫自定義的 Signal Generator。
- [ ] **Documentation Site**: 建立獨立的文檔網站 (如 MkDocs/Docusaurus)。
- [ ] **CI/CD Templates**: 提供標準化的 GitHub Actions 範本供社群使用。

---
> 追蹤最新進度，請查看專案的 Issues 與 Pull Requests。
