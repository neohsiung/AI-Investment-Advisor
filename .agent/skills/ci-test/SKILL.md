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
2. **Security Scan (Bandit)**: 執行 `bandit -r src/`，掃描潛在的安全漏洞（如 hardcoded secrets, insecure functions）。
3. **Wiki Integrity Check (Flat-Linking)**: 驗證 Wiki 內部連結的有效性，確保遵循扁平化連結規範。
4. **License Compliance Check**: 檢查第三方套件的授權合規性。

## 使用指南 (Usage Guide)

Agent 應在準備 commit 前執行一鍵檢查腳本：

```bash
python .agent/skills/ci-test/scripts/ci_test.py
```

若只想單獨執行特定項目：

```bash
# 測試與覆蓋率
pytest --cov=src --cov-report=term-missing

# 安全掃描
bandit -r src/

# Wiki 檢查
python .agent/skills/wiki-maintainer/scripts/verify_wiki_links.py

# 授權檢查
pip-licenses
```

## 注意事項 (Precautions)

- 若任何一項檢查失敗，**嚴禁執行 commit**，必須先修復問題。
- 對於 Bandit 的警告，若確認為 False Positive，應使用 `# nosec` 標註而非直接忽略。
- Wiki 連結若失效，應參考 `wiki-maintainer` 技能進行修復。
