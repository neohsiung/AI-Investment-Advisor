---
description: B2C SaaS 基礎架構準備與 Next.js / K8s / uv 專案轉換設定 (B2C SaaS Tech Stack Evolution Phase 1)
---

# B2C SaaS Tech Stack 演進工作流 (Phase 1 & 2 Transition)

本工作流旨在透過 **AI-Support First** 原則，自動化執行並驗證 B2C SaaS 技術選型計畫中的基礎設施初期轉換，包括移除 `requirements.txt` 轉移至 `uv`，以及前端或文檔切分的前置檢查。

> **觸發時機 (Trigger Conditions)**: 當準備啟動 B2C 演進計畫的第一階段 (Phase 1)，進行 API 解耦、依賴項升級或初始化 Next.js / Docusaurus 時。

## 執行步驟 (Steps)

// turbo-all

### 1. 檢驗目前架構依賴 (Dependency Analysis)
掃描當前根目錄下的 Python 套件依賴與過渡目標：
```bash
# 檢查是否有未被管理的 requirements.txt 需要轉移
ls -la requirements.txt
```

### 2. 初始化 uv 工作區 (Initialization) - (需要使用者確認)
(代理人向使用者提議執行以下指令，將專案升級為 `uv` 或 `Poetry` 依賴結構)
```bash
# 若要初始化 uv：
# uv init 
# uv add -r requirements.txt
echo "準備進行 uv 或 Turborepo 結構轉換，請指示是否執行！"
```

### 3. 多雲部署組態與 IaC 掃描 (Multi-Cloud Configuration Check)
檢查現有 K8s / Docker Compose 配置，標出尚待轉換為 Helm Charts 的實體：
```bash
# 列出現有的 docker-compose 配置，作為未來編寫 K8s Config 的依據
ls -la docker-compose*.yml
```

### 4. 同步與產出文檔 (Sync & Report)
完成初期結構化建立後，自動觸發文檔同步流程，將專案新架構 (Monorepo 或是 uv.lock) 反映至架構文件中：
```bash
/walkthrough-wiki-sync
```

---
**原則**:
- 所有的框架轉換 (如 `uv add` 或 Next.js 初始化) 必須遵守 **AI-Support First**，確保輸出的專案模板簡潔易懂。
- 在刪除舊有的 `requirements.txt` 之前，必須進行測試，確保 `uv.lock` 的依賴解析完全覆蓋所需套件。
- 在任何破壞性建立前，主動提示並詢問使用者是否執行轉換腳本。
