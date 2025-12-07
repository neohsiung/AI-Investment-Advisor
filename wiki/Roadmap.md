# 專案路線圖 (Project Roadmap)

> 返回 [[Home]]

本文件追蹤專案的未來發展方向與待辦事項 (原 NEXT_STEPS)。

## 🚀 已完成 / 文件化 (Done / Documented)
- [x] **部署指南**: 詳見 [[Deployment-Options]]。
- [x] **資料遷移**: 詳見 [[Database-Migration-Guide]]。
- [x] **架構審查**: 詳見 [[Clean-Architecture-Review]]。
- [x] **資安審計**: 詳見 [[Security-Audit-Report]]。

## 🗓️ 待辦事項 (Backlog)

### 架構重構 (Architecture Refactoring)
- [ ] **實作 Clean Architecture**: 
    - 依據 [[Clean-Architecture-Review]] 的規劃，建立 `src/domain` 與 `src/repositories`。
    - 解耦 Service Layer 與 Database Layer。

### 功能增強 (Feature Enhancements)
- [ ] **多環境支援 (Multi-Environment)**:
    - 設定 GitHub Environments (Dev / Staging / Prod)。
    - 修改 `ci-cd.yml` 支援分支觸發不同環境部署。
- [ ] **進階回測系統**: 提供更詳細的策略回測工具。

### 使用者體驗 (UX)
- [ ] **手機版介面優化**: 針對行動裝置優化 Streamlit 版面配置。
- [ ] **Line/Telegram 通知**: 除了 Email 外，整合即時通訊軟體通知。

## 貢獻指南 (Contribution)
歡迎提交 PR！請確保所有新功能皆包含單元測試，並通過 `bandit` 安全掃描。
