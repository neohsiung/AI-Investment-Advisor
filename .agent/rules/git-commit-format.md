# Git Commit Message Format Standard

## 强制要求 (Mandatory)

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

| Type | 使用场景 | 示例 |
|:-----|:---------|:-----|
| `feat` | 新功能 | `feat(analytics): add Leverage Engine` |
| `fix` | 错误修复 | `fix(sentinel): correct 4D trigger logic` |
| `refactor` | 代码重构 | `refactor(agents): extract factory pattern` |
| `test` | 测试相关 | `test(services): add analytics service tests` |
| `docs` | 文档更新 | `docs(wiki): update roadmap to v3.7` |
| `chore` | 构建/配置 | `chore(deps): upgrade pytest to 8.0` |
| `perf` | 性能优化 | `perf(workflow): optimize agent parallelism` |
| `style` | 代码格式 | `style(services): apply black formatter` |

## Scope Values

| Scope | 范围 |
|:------|:-----|
| `agents` | Agent相关 |
| `services` | 服务层 |
| `infrastructure` | 基础设施 |
| `data` | 数据层 |
| `repositories` | 仓储层 |
| `ui` | UI/Pages |
| `workflow` | 工作流 |
| `config` | 配置 |
| `docs` | 文档 |
| `tests` | 测试 |

## Category Headers (分类标题)

使用以下标准分类（双语）:

1. **核心變更 (Core Changes)** - 最重要的变更，必须包含
2. **資料層 (Data Layer)** - 数据库、仓储、providers
3. **服務層 (Service Layer)** - 业务逻辑服务
4. **基礎設施 (Infrastructure)** - LLM router, channel adapters, etc.
5. **測試覆蓋 (Test Coverage)** - 测试相关变更
6. **文檔更新 (Documentation)** - Wiki、README更新
7. **配置 (Configuration)** - 环境变量、settings

**规则**: 至少包含"核心變更"，其他根据实际情况选择相关分类。

## 示例 (Examples)

### 示例1: 新功能 (Feature)

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

### 示例2: Channel Adapter重构

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

### 示例3: 测试覆盖率提升

```
test(services): add comprehensive error handling tests for Polygon and FMP providers
新增 Polygon 與 FMP Provider 完整錯誤處理測試

**核心變更 (Core Changes)**:
- 覆蓋率從 74% 提升至 75% (-68 missed statements) / Coverage improved from 74% to 75% (-68 missed statements)
- 新增 33 個 Provider 測試 (Polygon 15, FMP 18) / Added 33 Provider tests (Polygon 15, FMP 18)

**測試覆蓋 (Test Coverage)**:
- 測試 API 錯誤處理 (401, 403, 429, 500) / Tested API error handling (401, 403, 429, 500)
- 測試網路超時與 Malformed JSON / Tested network timeouts and malformed JSON
- 覆蓋 prev_close fallback 邏輯 / Covered prev_close fallback logic

**服務層 (Service Layer)**:
- 驗證 PolygonProvider.fetch_history() 錯誤路徑 / Validated PolygonProvider.fetch_history() error paths
- 驗證 FMPProvider 新聞與價格 API / Validated FMPProvider news and price APIs
```

### 示例4: 文档更新

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

## 规则细节 (Detailed Rules)

### 1. Summary行

- **第一行**: 英文，遵循 Conventional Commits `<type>(<scope>): <summary>`
- **第二行**: 繁体中文，简洁描述
- **字数**: 英文 ≤ 72字符，中文 ≤ 30字

### 2. 核心变更 (必须)

- 至少包含 1-3 项核心变更
- 每项使用中文 / 英文格式
- 描述最重要的变更内容

### 3. 分类sections (按需)

- 根据实际变更选择1-3个相关分类
- 每个分类下列举具体变更
- 保持双语格式

### 4. 格式要求

- 使用markdown格式
- 中英文使用 ` / ` 分隔
- 使用bullet points (`-`)
- 代码元素使用backticks (`` `AnalyticsService` ``)

### 5. 长度控制

- 总长度: 150-300行为佳
- 核心变更: 1-3项
- 每个分类: 2-5项细节

## 违规示例与修正

### ❌ 错误: 只有英文
```
feat(analytics): add leverage calculation

Added new methods for calculating net equity and loan values.
```

### ✅ 正确: 双语+详细分类
```
feat(analytics): implement Leverage Engine for precise net equity calculation
實現槓桿引擎精確計算淨權益

**核心變更 (Core Changes)**:
- 新增槓桿計算邏輯 / Added leverage calculation logic

**服務層 (Service Layer)**:
- 更新 `AnalyticsService` / Updated `AnalyticsService`
```

### ❌ 错误: 缺少分类
```
feat: update roadmap

更新產品藍圖

Made changes to roadmap file.
```

### ✅ 正确: 清晰分类
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

## 工具集成 (Tool Integration)

### 生成雙份 Commit Message
```bash
# 1. Check status
git status

# 2. Project Repo Commit
git add src/ .agent/ README.md
git commit -m "<Project-Repo-Message>"

# 3. Wiki Repo Commit
cd wiki
git add .
git commit -m "<Wiki-Repo-Message>"
```

## 参考 (References)

- Conventional Commits: https://www.conventionalcommits.org/
- Git commit best practices: https://chris.beams.io/posts/git-commit/
