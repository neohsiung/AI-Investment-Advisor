# 技術債與待辦清單 (Technical Debt & Todos)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-18 | v1.1.1 | Mark Test Coverage Gaps as completed | Antigravity |
| 2026-02-18 | v1.1.0 | Mark AsyncIO integration as completed | Antigravity |
| 2026-02-17 | v1.0.0 | Initial Release | Neo |

---

<a id="zh"></a>

## 🇹🇼 技術債與待辦清單 (v1.0)

本文件追踪系統當前的技術債 (Technical Debt) 與未來待辦的技術優化事項。

### 1. 基礎設施優化 (Infrastructure)

- [ ] **Redis 標準化**: 
    - 描述: 當前 Redis 主要用於快取，需進一步標準化其在 `MemoryManager` 中的 Role，確保 TTL 與淘汰策略 (Eviction) 符合金融數據特性。
    - 優先級: 中
- [ ] **ElasticSearch 整合集 (Phase 2)**: 
    - 描述: 當資料量增長至臨界點時，實作 `ElasticsearchSearchEngine` 以提供更強大的日誌分析能力。
    - 優先級: 低
- [ ] **時序資料優化**:
    - 描述: 評估將市場日誌 (OHLCV) 遷移至 `TimescaleDB` 擴充，以利用其自動分區與壓縮機制。
    - 優先級: 低
- [ ] **智能體集群篩選邏輯**:
    - 描述: 在 `role_swarm.py` 中實作動態的智能體選擇與過濾邏輯，優化集群決策效率。
    - 優先級: 低

### 2. 代碼與架構 (Code & Architecture)

- [ ] **ORM 進一步覆蓋**:
    - 描述: 將剩餘的管理類 Repository (如 `FeedbackRepository`) 遷移至 SQLAlchemy ORM。
    - 優先級: 中
- [x] **非同步 (AsyncIO) 深度導入**: 
    - 描述: 確保所有 Network I/O (如 `NotificationService` 的 Adapter 發送) 完全非同步化，防止單點延遲阻塞整體工作流。
    - 狀態: 已於 2026-02-18 完成 (Refactored Notification & Interaction Services).
    - 優先級: 高
- [x] **測試覆蓋率缺口**:
    - 描述: 補齊新導入的 `models.py` 與 `BaseRepository` 的 Edge Case 測試，維持整體覆蓋率 > 75%。
    - 狀態: 已於 2026-02-18 完成 (Added tests/test_infra_models_repo.py).
    - 優先級: 高
- [ ] **多使用者排程優化**:
    - 描述: 優化 `SchedulerService` 以從所有使用者投資組合中取得不重複的標的，減少重複抓取。
    - 優先級: 中
- [ ] **精準績效評估**:
    - 描述: 在 `PerformanceService` 中實作複雜的準確度計算（對比信號價格與出場價格）。
    - 優先級: 中

### 3. 安全性 (Security)

- [ ] **SQL 靜態分析自動化**:
    - 描述: 將 `Safe-SQL-Only` 規範整合至 CI，使用檢索工具 (如 `grep` 或 `ast` 分析) 自動攔截拼接 SQL 的代碼。
    - 優先級: 中

---

<a id="en"></a>

## 🇺🇸 Technical Debt & Todos (v1.0)

This document tracks current technical debt and planned technical optimizations.

### 1. Infrastructure Optimization

- [ ] **Redis Standardization**: 
    - Description: Standardize Redis roles in `MemoryManager`, ensuring TTL and Eviction policies align with financial data requirements.
    - Priority: Medium
- [ ] **ElasticSearch Integration (Phase 2)**: 
    - Description: Implement `ElasticsearchSearchEngine` for advanced log analytics as data scales.
    - Priority: Low
- [ ] **Time-Series Optimization**:
    - Description: Evaluate migrating market logs (OHLCV) to `TimescaleDB` for improved partitioning and compression.
    - Priority: Low
- [ ] **Agent Swarm Swarm Filtering**:
    - Description: Implement dynamic selection/filtering logic in `role_swarm.py` for better decision efficiency.
    - Priority: Low

### 2. Code & Architecture

- [ ] **ORM Coverage Expansion**:
    - Description: Migrate remaining administrative repositories (e.g., `FeedbackRepository`) to SQLAlchemy ORM.
    - Priority: Medium
- [x] **Deep AsyncIO Integration**: 
    - Description: Ensure all network I/O (e.g., `NotificationService` adapters) is fully asynchronous to prevent blocking the workflow.
    - Status: Completed on 2026-02-18 (Refactored Notification & Interaction Services).
    - Priority: High
- [x] **Test Coverage Gaps**: 
    - Description: Add edge-case tests for new `models.py` and `BaseRepository` to maintain > 75% coverage.
    - Status: Completed on 2026-02-18 (Added tests/test_infra_models_repo.py).
    - Priority: High
- [ ] **Multi-user Scheduler Optimization**:
    - Description: Optimize `SchedulerService` to collect distinct tickers from all user portfolios to avoid redundant fetches.
    - Priority: Medium
- [ ] **Precision Performance Metrics**:
    - Description: Implement complex accuracy calculations in `PerformanceService` (comparing signal price vs entry/exit).
    - Priority: Medium

### 3. Security

- [ ] **Automated SQL Static Analysis**:
    - Description: Integrate `Safe-SQL-Only` checks into CI using AST analysis to block non-parameterized SQL.
    - Priority: Medium

## 🔗 Bidirectional Links
- **Standards**: [Database & Git Standards](資料庫設計與代碼規範-Database-Git-Standards)
- **Architecture**: [System Landscape](系統全景圖-System-Landscape)
