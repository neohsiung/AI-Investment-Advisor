# 代碼提交規範 (Git Commit Standard)

> **[⬅️ Back to Developer Guide](README.md)**

為了確保代碼庫的可維護性與自動化發布的可行性，本專案採用 **Conventional Commits** 規範，並強制執行 **雙語 (Bilingual)** 說明。

To ensure maintainability and enable automated releases, this project adopts **Conventional Commits** with mandatory **Bilingual** descriptions.

## 1. 提交格式 (Commit Format)

```text
<type>(<scope>): <English Subject> | <中文主旨>

[Optional Body - English detailed description]
[Optional Body - 中文詳細說明]

[Optional Footer(s)]
```

### 1.1 Header
*   **Must** be under 72 characters if possible (soft limit), max 100.
*   **Format**: `type(scope): English Summary | 中文摘要`
*   **Example**: `feat(auth): add google login support | 新增 Google 登入支援`
*   **Scope (可選)**: 指明影響的模組 (e.g., `market`, `ui`, `workflow`).

### 1.2 Body
*   Use imperative, present tense: "change" not "changed" nor "changes".
*   Explain **what** and **why** vs. **how**.
*   **Structure**:
    *   English textual description first.
    *   Empty line.
    *   Traditional Chinese textual description.

### 1.3 Footer
*   Referencing issues: `Closes #123`.
*   Breaking Changes: Start with `BREAKING CHANGE:`.

## 2. 提交類型 (Commit Types)

| Type | Description | 中文說明 |
| :--- | :--- | :--- |
| **feat** | A new feature | 新增功能 |
| **fix** | A bug fix | 修復 Bug |
| **docs** | Documentation only changes | 僅修改文件 |
| **style** | Changes that do not affect the meaning of the code (white-space, formatting) | 代碼格式調整 (不影響邏輯) |
| **refactor**| A code change that neither fixes a bug nor adds a feature | 重構 (無新功能/無修復) |
| **perf** | A code change that improves performance | 效能優化 |
| **test** | Adding missing tests or correcting existing tests | 測試相關 |
| **build** | Changes that affect the build system or external dependencies | 建置系統/依賴調整 |
| **ci** | Changes to our CI configuration files and scripts | CI/CD 設定調整 |
| **chore** | Other changes that don't modify src or test files | 雜項/維護 |
| **revert** | Reverts a previous commit | 還原提交 |

## 3. 範例 (Examples)

### Feature (新增功能)
```text
feat(market): implement connection to Fred API | 實作 Fred API 串接

Added FredService to fetch macro economic data (GDP, CPI).
新增 FredService 以獲取總體經濟數據 (GDP, CPI)。

Closes #45
```

### Bug Fix (修復)
```text
fix(auth): resolve token refresh 401 error | 修復 Token 刷新 401 錯誤

Fixed logic in AuthManager where refresh token was not sent in header.
修正 AuthManager 中未在標頭發送刷新 Token 的邏輯錯誤。
```

### Breaking Change (重大變更)
```text
refactor(api): remove v1 legacy endpoints | 移除 v1 舊版端點

BREAKING CHANGE: All API calls must now use /api/v2 prefix.
重大變更：所有 API 呼叫現在必須使用 /api/v2 前綴。
```

## 4. Emoji (Optional but Recommended)

| Emoji | Code | Commit Type |
| :--- | :--- | :--- |
| ✨ | `:sparkles:` | feat |
| 🐛 | `:bug:` | fix |
| 📚 | `:books:` | docs |
| 💎 | `:gem:` | style |
| 🔨 | `:hammer:` | refactor |
| 🚀 | `:rocket:` | perf |
| 🚨 | `:rotating_light:` | test |
| 📦 | `:package:` | build |
| 👷 | `:construction_worker:` | ci |
| 🔧 | `:wrench:` | chore |
