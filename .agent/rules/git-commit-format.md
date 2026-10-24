# Git Commit Message Format Standard

## 強制要求 (Mandatory)

產生或協助撰寫 commit 訊息時，**一律用繁體中文**（2026-10-25 起，創辦人決定）。`type` 與 `scope` 維持英文關鍵字；指令、路徑、識別名稱、錯誤訊息保持原文。
Commit messages are written in Traditional Chinese; `type`/`scope` keywords, commands, paths and identifiers stay as-is.

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
<type>(<scope>): <繁中摘要>

**核心變更**:
- <變更>

**<分類>**:
- <細節>
```

## Type Values

| Type | 使用場景 | 範例 |
|:-----|:---------|:-----|
| `feat` | 新功能 | `feat(analytics): 新增槓桿引擎` |
| `fix` | 錯誤修復 | `fix(sentinel): 修正 4D 觸發邏輯` |
| `refactor` | 代碼重構 | `refactor(agents): 抽出 factory 模式` |
| `test` | 測試相關 | `test(services): 補 analytics service 測試` |
| `docs` | 文檔更新 | `docs(wiki): 路線圖更新到 v3.7` |
| `chore` | 建構/配置 | `chore(deps): pytest 升到 8.0` |
| `perf` | 效能優化 | `perf(workflow): 提高 agent 平行度` |
| `style` | 代碼格式 | `style(services): 套用 black 格式` |

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

使用以下標準分類:

1. **核心變更** - 最重要的變更，必須包含
2. **資料層** - 資料庫、倉儲、providers
3. **服務層** - 業務邏輯服務
4. **基礎設施** - LLM router, channel adapters, etc.
5. **測試覆蓋** - 測試相關變更
6. **文檔更新** - Wiki、README 更新
7. **配置** - 環境變數、settings

**規則**: 至少包含「核心變更」，其他根據實際情況選擇相關分類。

### 範例: 新功能 (Feature)

```
feat(analytics): 實作槓桿引擎，精確計算淨權益

**核心變更**:
- 新增 `calculate_net_equity()` 與 `calculate_loan_value()` 方法

**服務層**:
- `AnalyticsService` 加入槓桿計算邏輯

**測試覆蓋**:
- 補上淨權益與借款金額的單元測試
```

## 違規範例與修正

### ❌ 錯誤: 英文摘要、缺少分類
```
feat(analytics): add leverage calculation
Added new methods for calculating net equity.
```

### ✅ 正確: 繁中 + 分類
```
feat(analytics): 實作槓桿引擎，精確計算淨權益

**核心變更**:
- 新增槓桿計算邏輯

**服務層**:
- 更新 `AnalyticsService`
```

## 規則細節 (Detailed Rules)

1. **Summary 行**: 第一行 `<type>(<scope>): <繁中摘要>`，摘要 ≤ 40 字
2. **核心變更** (必須): 1-3 項
3. **分類 Sections**: 根據實際變更選擇 1-3 個相關分類
4. **格式**: Markdown、`-` bullets、程式元素用 backticks
5. **長度**: 核心變更 1-3 項，每分類 2-5 項

## 原子提交原則 (Atomic Commits Principle)

**強制要求**: 嚴禁混合不同性質的變更於同一 Commit。必須依照修改時序與邏輯脈絡拆分為原子化提交。

## Agent 行為準則 (Agent Behavior Guidelines)

**強制要求**: Agent **嚴禁**在未獲得使用者明確 `commit` 指令的情況下自動執行 `git commit`。Agent 的職責是執行研發、測試與驗證，並將變更處於待提交狀態。

## Wiki 提交規範 (Wiki Commit Convention)

- **「wiki commit」**: 僅針對 `wiki/` Repo 執行 `git -C wiki add/commit/push`。
- **「commit」**: 僅針對主專案 Repo（wiki 已在 `.gitignore` 中排除）。
- **「commit & wiki commit」**: 依序執行兩個 Repo 的原子化提交。

## 參考 (References)

- Conventional Commits: https://www.conventionalcommits.org/
- Git commit best practices: https://chris.beams.io/posts/git-commit/

