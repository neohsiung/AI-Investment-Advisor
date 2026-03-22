---
name: ci-test
description: 預提交檢查工具，包含測試覆蓋率、安全掃描、Wiki 完整性與授權合規性。
---

# CI Test (Pre-Commit Check)

> 本技能為 **Agent Dev Skill**，用於在執行 `git commit` 前，確保程式碼品質與安全性符合專案要求。

## 適用時機 (When to Use)

- **在任何 `git commit` 前**：確保本次變更沒有破壞現有測試、引入安全漏洞或破壞 Wiki 連結。
- 當 Agent 完成一個階段性的功能開發或重構時。

## 核心測試項目 (Core Test Items)

1. **Run tests with coverage**: 執行 `pytest --cov=src`，確保新代碼有足夠的測試覆蓋。
   - **目標**: 總覆蓋率 > 75% | Services 層 > 80% | Error handling = 100% | CI 門檻 (fail_under = 70)
2. **Security Scan (Bandit & Grep Checks)**: 執行 `bandit -r src/`、`safety` 等指令，並檢查非法字串（如 hardcoded secrets, SQLi）。
3. **Wiki Integrity Check (Flat-Linking)**: 驗證 Wiki 內部連結的有效性，確保遵循扁平化連結規範。
4. **License Compliance Check**: 檢查第三方套件的授權合規性。

## 使用指南 (Usage Guide)

Agent 應在準備 commit 前執行一鍵檢查腳本：

```bash
python .agent/skills/ci-test/scripts/ci_test.py
```

### 測試與覆蓋率 (Coverage Checks)

```bash
# 1. 執行並輸出缺失行號
pytest --cov=src --cov-report=term-missing

# 2. 快速抓出低於 75% 的模組
pytest --cov=src --cov-report=term tests/ | awk '$NF < 75 {print}'
```

**優先覆蓋目標**：

- `P0`: Services 層 (> 80%)，錯誤處理 (100%)
- `P1`: Repositories (> 75%)，Agents (> 70%)

### 安全與依賴項掃描 (Security Audits)

```bash
# 1. Bandit 代碼掃描 (重點檢查 B324, B608)
bandit -r src/

# 2. 依賴項漏洞審查
safety check -r requirements.txt
pip-audit -r requirements.txt

# 3. 硬編碼與潛在風險檢查
grep -r "os.getenv" src/ | grep -vE "test_|conftest"
grep -r "hashlib.md5" src/
grep -r "execute(f\"" src/
grep -rE "(key|token|password|secret)\s*=\s*['\"][a-zA-Z0-9]{10,}['\"]" src/
```

### Wiki 檢查

```bash
python .agent/skills/wiki-maintainer/scripts/verify_wiki_links.py
```

### 授權檢查

```bash
pip-licenses
```

## 注意事項 (Precautions)

- 若任何一項檢查失敗，**嚴禁執行 commit**，必須先修復問題。
- 對於 Bandit 的警告，若確認為 False Positive，應使用 `# nosec` 標註而非直接忽略。
- Wiki 連結若失效，應參考 `wiki-maintainer` 技能進行修復。
