---
name: dependency-management
description: |
  自動更新並審計專案依賴項。
  觸發時機：(1) 升級任何 pip 套件前（尤其是 litellm / streamlit / qdrant-client / openai 等核心套件）
  (2) 從 requirements.txt 移除任何套件前
  (3) 遭遇 ResolutionImpossible / pip-compile 衝突時
  (4) Dependabot / pip-audit 回報安全漏洞，需要升級依賴版本時
  (5) 新增含外部服務整合的模組（如 OAuth、LLM gateway），需確認配套套件完整
---

# Dependency Management Skill

本技能旨在確保專案的所有依賴項持續處於安全且最新的版本，並符合精確版本鎖定要求。

## 核心流程 (Core Workflow)

1. **檢查過時套件**:

   ```bash
   pip list --outdated
   ```

2. **更新與審計 (逐一執行)**:

   - 執行更新：`pip install --upgrade <package_name>`
   - 審核漏洞：執行 `ci-test` 中的安全掃描段落或 `pip-audit`。
   - 重新鎖定：更新 `requirements.txt` 以 `==` 鎖定版本。

3. **穩定性驗證**:

   - 執行 `pytest` 確保無破壞性變更。

## ⚠️ 核心套件升級：傳遞依賴預掃描 (Transitive Dependency Pre-Scan)

> **適用時機**：升級 `litellm`, `streamlit`, `qdrant-client`, `openai` 等核心套件前，**必須**執行以下步驟，避免 CI 上反覆調試依賴衝突。

```bash
# Step 1: 查看新版本的所有直接依賴與版本要求
pip show <new-package> | grep -E "Requires|Version"

# Step 2: 逐一確認衝突風險套件的可用版本
pip index versions <dep-package-name>

# Step 3: 乾跑 pip-compile，確認整體解析可通過（CI 用相同工具）
pip install pip-tools --quiet
pip-compile requirements.txt --dry-run 2>&1 | grep -E "conflict|Cannot install|ResolutionImpossible"

# Step 4: 若 Step 3 有衝突 → 立即對齊衝突套件版本，再重覆 Step 3
# 直到 pip-compile --dry-run 無任何 ERROR 輸出，才可 commit
```

**原則**：「核心套件升級時，禁止在 CI 上調試依賴衝突。所有衝突必須在本地 dry-run 階段解決。」

## ⚠️ 套件移除：安全檢查清單 (Removal Safety Checklist)

> **適用時機**：從 `requirements.txt` 移除任何套件前，必須按順序執行以下 3 個步驟。

```bash
# Step 1: 全域掃描（含 services/, tests/, scripts/ 所有子目錄）
grep -rn "import <package_name>\|from <package_name>" . \
  --include="*.py" \
  --exclude-dir=".git" \
  --exclude-dir="__pycache__"

# Step 2: 確認無其他套件依賴它（間接依賴）
pip show <package_name> | grep "Required-by"
# 若 Required-by 非空 → 不可直接移除，改為不顯式鎖定（讓父套件管理）

# Step 3: 移除後立即執行 collection dry-run，確保無 ImportError
python3 -m pytest --collect-only -q 2>&1 | grep -E "ERROR|ImportError|ModuleNotFoundError"
# 必須無任何輸出，才可 commit 刪除
```

**特別注意**：掃描必須包含 `services/` 目錄，該目錄內可能有 transitive import（e.g., `services/mcp_server/src/app/__init__.py` 會 import `src/` 的模組）。

## 核心原則 (Core Principles)

- **嚴禁批次更新**: 必須逐一更新與測試，嚴禁一次性自動化更新所有套件。
- **Rule #11 遵循**: 所有變更必須符合精確版本鎖定 (Exact Version Pinning)。
- **原子提交**: 每個依賴項的重大版本更新建議獨立 commit。
- **升級前預掃描**: 核心套件升級必須先執行 `pip-compile --dry-run`，不在 CI 上調試衝突。
- **移除前三步驟**: 移除套件必須完成全域掃描 → Required-by 確認 → collection dry-run。

## ⚠️ 配套套件檢查清單 (Paired Package Checklist)

> **適用時機**：新增具外部服務整合的功能模組時

某些套件存在「主套件 + 配套擴充」結構，只裝一半會在 **runtime** 才出現 `ModuleNotFoundError`（不在 pip install 階段報錯）：

| 主套件 | 必須配套 | 常見疏漏場景 |
|---|---|---|
| `google-auth` | `google-auth-oauthlib` | OAuth flow `_get_flow()` 發出 `No module named google_auth_oauthlib` |
| `litellm` | `openai`、`anthropic` | LLM gateway 初始化失敗 |
| `asyncpg` | `psycopg2-binary` | DB 連接失敗（async vs sync driver 混用）|

```bash
# 新增套件後，確認其 Requires 是否有尚未安裝的配套
pip show <new-package> | grep Requires
# 逐一確認 Requires 清單中的套件是否在 requirements.txt 中
```

## ⚠️ npm / Frontend 套件安全 (Frontend Package Security)

> **適用時機**：Dependabot 對 `frontend/package-lock.json` 回報 CVE，或新增/變更 Next.js plugin 時

```bash
# 找出傳遞依賴 CVE 的根源套件
npm ls <vulnerable-package>
# 若根源是某個 plugin（如 next-pwa），優先考慮「移除 plugin」而非加 overrides

# 確認修復後零暴露
npm ls <vulnerable-package>  # 必須零輸出才算修復
```

**原則**：
- `npm overrides` 屬於治標不治本，優先確認能否移除根源套件
- 任何使用 `withXxx()` 包裝 `next.config` 的 plugin，必須先確認支援 Turbopack（Next.js 16+）
- 移除 plugin 後必須同步清除 `package.json` 中的對應 `overrides` 段落
