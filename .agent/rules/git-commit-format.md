# Git Commit Message Format Standard

## 強制要求 (Mandatory)

When generating or helping with Git commit messages, **ALWAYS** follow this bilingual detailed format.

Since this project maintains two separate repositories (**Project Repo** and **Wiki Repo**), you must generate **two separate commit messages** when changes affect both source code and documentation.

## 雙 Repo 規範 (Dual-Repo Standard)

**當變更同時涉及代碼與文檔時，必須分別產出以下兩份訊息：**

### 1. 專案 Repo (Project Repo)
- **Scope**: `agents`, `services`, `infrastructure`, `workflow`, `config`, `tests`, `docs` (僅限 README 或非 Wiki 文檔)
- **內容**: 聚焦於程式碼變更、邏輯調整、測試新增。

### 2. Wiki Repo (Wiki Repo)
- **Repo Path**: `wiki/` (本專案做為 submodule 或獨立 repo 管理)
- **Scope**: `wiki`
- **內容**: 聚焦於文檔更新、架構圖調整、規格變更。
- **格式**: 雖然是文檔，仍需遵循相同結構 (Summary + Core Changes)。

## Format Template

```
<type>(<scope>): <short-summary-english>
<short-summary-traditional-chinese>

**核心變更 (Core Changes)**:
- <change-zh> / <change-en>

**<category-zh> (<category-en>)**:
- <detail-zh> / <detail-en>

**<category-zh> (<category-en>)**:
- <detail-zh> / <detail-en>
```

## Type Values

| Type | 使用場景 | 範例 |
|:-----|:---------|:-----|
| `feat` | 新功能 | `feat(analytics): add Leverage Engine` |
| `fix` | 錯誤修復 | `fix(sentinel): correct 4D trigger logic` |
| `refactor` | 代碼重構 | `refactor(agents): extract factory pattern` |
| `test` | 測試相關 | `test(services): add analytics service tests` |
| `docs` | 文檔更新 | `docs(wiki): update roadmap to v3.7` |
| `chore` | 建構/配置 | `chore(deps): upgrade pytest to 8.0` |
| `perf` | 效能優化 | `perf(workflow): optimize agent parallelism` |
| `style` | 代碼格式 | `style(services): apply black formatter` |

## Scope Values

| Scope | 範圍 |
|:------|:-----|
| `agents` | Agent 相關 |
| `services` | 服務層 |
| `infrastructure` | 基礎設施 |
| `data` | 資料層 |
| `repositories` | 倉儲層 |
| `ui` | UI/Pages |
| `workflow` | 工作流 |
| `config` | 配置 |
| `docs` | 文檔 |
| `tests` | 測試 |

## Category Headers (分類標題)

使用以下標準分類（雙語）:

1. **核心變更 (Core Changes)** - 最重要的變更，必須包含
2. **資料層 (Data Layer)** - 資料庫、倉儲、providers
3. **服務層 (Service Layer)** - 業務邏輯服務
4. **基礎設施 (Infrastructure)** - LLM router, channel adapters, etc.
5. **測試覆蓋 (Test Coverage)** - 測試相關變更
6. **文檔更新 (Documentation)** - Wiki、README 更新
7. **配置 (Configuration)** - 環境變數、settings

**規則**: 至少包含「核心變更」，其他根據實際情況選擇相關分類。

## 範例 (Examples)

### 範例 1: 新功能 (Feature)

```
feat(analytics): implement Leverage Engine for precise net equity calculation
實現槓桿引擎精確計算淨權益

**核心變更 (Core Changes)**:
- 新增 `calculate_net_equity()` 與 `calculate_loan_value()` 方法 / Added `calculate_net_equity()` and `calculate_loan_value()` methods
- 支援多券商槓桿倍數計算 / Support multi-broker leverage ratio calculation

**服務層 (Service Layer)**:
- 更新 `AnalyticsService` 新增槓桿計算邏輯 / Updated `AnalyticsService` with leverage calculation logic
- 整合 Portfolio 與 Position 數據源 / Integrated Portfolio and Position data sources

**測試覆蓋 (Test Coverage)**:
- 新增 15 個單元測試 / Added 15 unit tests
- 覆蓋率從 74% 提升至 75% / Coverage improved from 74% to 75%

**文檔更新 (Documentation)**:
- 更新 `服務層開發指南` v3.6 章節 / Updated Service Layer Guide v3.6 section
- 補充 Leverage Engine 使用範例 / Added Leverage Engine usage examples
```

### 範例 2: Channel Adapter 重構

```
refactor(infrastructure): implement Channel Adapter pattern for notification decoupling
實現 Channel Adapter 模式解耦通知邏輯

**核心變更 (Core Changes)**:
- 引入 `IChannelAdapter` 介面統一通道抽象 / Introduced `IChannelAdapter` interface for unified channel abstraction
- 重構 NotificationService 使用 Adapter 模式 / Refactored NotificationService to use Adapter pattern

**基礎設施 (Infrastructure)**:
- 新增 `EmailAdapter`, `LineAdapter`, `WebAdapter` / Added `EmailAdapter`, `LineAdapter`, `WebAdapter`
- 從 DB settings 動態載入通道配置 / Dynamically load channel config from DB settings

**測試覆蓋 (Test Coverage)**:
- 新增 Channel Adapter 單元測試 18 個 / Added 18 unit tests for Channel Adapters
- Mock 外部服務整合測試 / Mocked external service integration tests
```

### 範例 3: 測試覆蓋率提升

```
test(services): add comprehensive error handling tests for Polygon and FMP providers
新增 Polygon 與 FMP Provider 完整錯誤處理測試

**核心變更 (Core Changes)**:
- 覆蓋率從 74% 提升至 75% (-68 missed statements) / Coverage improved from 74% to 75% (-68 missed statements)
- 新增 33 個 Provider 測試 (Polygon 15, FMP 18) / Added 33 Provider tests (Polygon 15, FMP 18)

**測試覆蓋 (Test Coverage)**:
- 測試 API 錯誤處理 (401, 403, 429, 500) / Tested API error handling (401, 403, 429, 500)
- 測試網路逾時與 Malformed JSON / Tested network timeouts and malformed JSON
- 覆蓋 prev_close fallback 邏輯 / Covered prev_close fallback logic

**服務層 (Service Layer)**:
- 驗證 PolygonProvider.fetch_history() 錯誤路徑 / Validated PolygonProvider.fetch_history() error paths
- 驗證 FMPProvider 新聞與價格 API / Validated FMPProvider news and price APIs
```

### 範例 4: 文檔更新

```
docs(wiki): update roadmap with v3.7-v4.0 Multi-Tier Agent architecture
更新產品藍圖新增 v3.7-v4.0 Multi-Tier Agent 架構規劃

**核心變更 (Core Changes)**:
- 詳細規劃 Role × Multi-Tier Agents 架構 (Advanced/Smart/Fast) / Detailed planning for Role × Multi-Tier Agents architecture (Advanced/Smart/Fast)
- 補充 v3.7-v4.0 實現細節與時間預估 / Added v3.7-v4.0 implementation details and time estimates

**文檔更新 (Documentation)**:
- 更新 `產品演進藍圖-Evolutionary-Roadmap.md` v3.6.1 / Updated Evolutionary Roadmap v3.6.1
- 同步更新 `架構哲學-Architectural-Philosophies.md` / Synced updates to Architectural Philosophies
- 同步更新 `研究與最佳實踐-Research-Best-Practices.md` / Synced updates to Research & Best Practices
```

## 規則細節 (Detailed Rules)

### 1. Summary 行

- **第一行**: 英文，遵循 Conventional Commits `<type>(<scope>): <summary>`
- **第二行**: 繁體中文，簡潔描述
- **字數**: 英文 ≤ 72 字元，中文 ≤ 30 字

### 2. 核心變更 (必須)

- 至少包含 1-3 項核心變更
- 每項使用中文 / 英文格式
- 描述最重要的變更內容

### 3. 分類 Sections (按需)

- 根據實際變更選擇 1-3 個相關分類
- 每個分類下列舉具體變更
- 保持雙語格式

### 4. 格式要求

- 使用 markdown 格式
- 中英文使用 ` / ` 分隔
- 使用 bullet points (`-`)
- 代碼元素使用 backticks (`` `AnalyticsService` ``)

### 5. 長度控制

- 總長度: 150-300 行為佳
- 核心變更: 1-3 項
- 每個分類: 2-5 項細節

## 違規範例與修正

### ❌ 錯誤: 只有英文
```
feat(analytics): add leverage calculation

Added new methods for calculating net equity and loan values.
```

### ✅ 正確: 雙語 + 詳細分類
```
feat(analytics): implement Leverage Engine for precise net equity calculation
實現槓桿引擎精確計算淨權益

**核心變更 (Core Changes)**:
- 新增槓桿計算邏輯 / Added leverage calculation logic

**服務層 (Service Layer)**:
- 更新 `AnalyticsService` / Updated `AnalyticsService`
```

### ❌ 錯誤: 缺少分類
```
feat: update roadmap

更新產品藍圖

Made changes to roadmap file.
```

### ✅ 正確: 清晰分類
```
docs(wiki): update roadmap with v3.7 Multi-Tier architecture
更新產品藍圖新增 v3.7 Multi-Tier 架構

**核心變更 (Core Changes)**:
- 新增 v3.7 Multi-Tier Agent 規劃 / Added v3.7 Multi-Tier Agent planning

**文檔更新 (Documentation)**:
- 更新版本紀錄至 v3.6.1 / Updated version history to v3.6.1
- 補充技術需求與預估時間 / Added technical requirements and time estimates
```

## 原子提交原則 (Atomic Commits Principle)

**強制要求 (Mandatory)**: 嚴禁將不同性質的變更（如：重構、新功能、錯誤修復、文檔）混合在同一個 Commit 中。必須依照修改時序與邏輯脈絡拆分為原子化的提交。

- **情境 1**: 在開發新功能時發現需要重構舊代碼 -> 先提交重構 Commit，再提交新功能 Commit。
- **情境 2**: 修復 Bug 的同時更新了文檔 -> 拆分為 `fix` 和 `docs` 兩個 Commit。
- **時序性**: Commit 順序應反映真實的開發路徑，避免「一次全加」的行為。

## Agent 行為準則 (Agent Behavior Guidelines)

**強制要求 (Mandatory)**: AI Agent **嚴禁**在未獲得使用者明確 `commit` 指令的情況下自動執行 `git commit`。

- **工作流程**: Agent 的職責是執行研發、測試與驗證，並將變更處於暫存 (Staging) 狀態或待提交狀態。
- **觸發條件**: 僅當使用者明確輸入「commit」指令時，Agent 才可根據上述原子原則執行真正的提交操作。
- **Wiki 同步**: 同樣適用此原則。Agent 應準備好 Wiki 變更，並在使用者指令下執行 Wiki Repo 的提交。

## Wiki 提交規範 (Wiki Commit Convention)

**強制要求 (Mandatory)**: `wiki/` 目錄是一個獨立的 Git Repository（擁有獨立的 `wiki/.git`），與主專案 Repo 分開管理。

- **「wiki commit」指令**: 當使用者說「wiki commit」時，**僅針對 `wiki/` Repo 執行 commit**，不影響主專案 Repo。
  ```bash
  # Wiki Commit 操作
  git -C wiki add <files>
  git -C wiki commit -m "<message>"
  git -C wiki push
  ```
- **「commit」指令**: 僅針對主專案 Repo 執行 commit，不包含 wiki 目錄（wiki 已在 `.gitignore` 中排除）。
- **「commit & wiki commit」指令**: 依序執行兩個 Repo 的原子化提交，分別產出符合格式的 commit message。
- **Push 獨立性**: 兩個 Repo 的 push 操作互相獨立，使用者需分別下達 push 指令或同時指定。

## 工具整合 (Tool Integration)

### 產出雙份 Commit Message
```bash
# 1. Check status
git status

# 2. Project Repo Commit
git add src/ .agent/ README.md
git commit -m "<Project-Repo-Message>"
```

## 參考 (References)

- Conventional Commits: https://www.conventionalcommits.org/
- Git commit best practices: https://chris.beams.io/posts/git-commit/
