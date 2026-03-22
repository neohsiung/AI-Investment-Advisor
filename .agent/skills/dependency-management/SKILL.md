---
name: dependency-management
description: 自動更新並審計專案依賴項 (Automatically update and audit project dependencies)
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

## 核心原則 (Core Principles)

- **嚴禁批次更新**: 必須逐一更新與測試，嚴禁一次性自動化更新所有套件。
- **Rule #11 遵循**: 所有變更必須符合精確版本鎖定 (Exact Version Pinning)。
- **原子提交**: 每個依賴項的重大版本更新建議獨立 commit。
