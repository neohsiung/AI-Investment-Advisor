# AI 投資顧問 (AI Investment Advisor) - Wiki

## 目標 (Goal)
建立一個全方位的專案知識庫，提供從系統架構、部署運維到使用者操作的完整指引，確保團隊成員與使用者能快速上手並深入理解系統。

## 為什麼 (Why)
- **降低認知負荷**: 透過結構化文件，將複雜的 AI 量化系統化繁為簡。
- **確保可維護性**: 記錄部署細節與架構決策，避免知識斷層。
- **促進協作**: 統一專案語言與開發標準，並依照不同角色切分關注點。

## 做了什麼 (What)
本 Wiki 依照**使用者角色**進行重新編排：

1.  **使用者手冊 (User Manual)**: 給終端使用者的操作指引。
2.  **產品經理專區 (PM Corner)**: 給 PM 的產品規劃與藍圖。
3.  **開發者指南 (Developer Guide)**: 給工程師的安裝、API 與實作細節。
4.  **架構師視角 (Architect View)**: 給架構師的系統設計與決策紀錄。
5.  **存檔 (Archive)**: 歷史文件與過時規格。

## 如何進行 (How)
請根據您的角色，點擊下方連結進入對應專區：

### � 01. 使用者手冊 (User Manual)
- [[User-Guide]] - 系統操作完整教學。
- [[Cron-Setup]] - 自動化排程設定教學。
- [[Deployment-Options]] - 選擇適合您的部署方式 (Local vs Cloud)。

### 📅 02. 產品經理專區 (Product Manager)
- [[Roadmap]] - 產品發展藍圖與里程碑。

### � 03. 開發者指南 (Developer)
- **環境設定**:
    - [[Deployment-Local-SQLite]] - 本地開發環境搭建。
    - [[Deployment-GCP-CloudRun]] - 生產環境部署指南。
    - [[Setup-External-Services]] - 外部服務 API (FRED, LLM) 設定。
    - [[Google-OAuth-Setup]] - Google 登入設定。
- **數據與遷移**:
    - [[Database-Migration-Guide]] - 資料庫遷移指南 (SQLite <-> Cloud SQL)。
- **技術規格 (Specs)**:
    - [[01_data_layer]] - 資料層規格。
    - [[02_analytics]] - 分析引擎規格。
    - [[03_agents]] - AI 代理人規格。

### 🏗️ 04. 架構師視角 (Architect)
- [[System-Overview]] - 系統全貌、架構圖與核心流程。
- [[AI-Agent-Swarm]] - AI 代理人集群協作機制。
- [[System-Migration-Plan]] - 系統架構遷移計畫 (v1 -> v3)。
- [[Clean-Architecture-Review]] - 架構檢討與重構建議。
- [[Security-Audit-Report]] - 安全性審計與建議。

### 📦 Archive (歷史存檔)
- [[Archive/README|Archive Index]] - 查閱過時文件與歷史決策。

---
> *本文件遵循「黃金圈法則 (Golden Circle)」撰寫：先說明目標 (Goal) 與理由 (Why)，再介紹內容 (What) 與執行細節 (How)。*
