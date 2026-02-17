---
description: 自動更新並審計專案依賴項 (Automatically update and audit project dependencies)
---

### [依賴項安全更新工作流 (Dependency Update Workflow)]

本工作流旨在確保所有依賴項持續處於安全且最新的版本。

1. **檢查過時套件**
// turbo
```bash
pip list --outdated
```

2. **更新單個套件並審計**
   - 使用者指定套件名稱後，執行：
// turbo
```bash
pip install --upgrade <package_name>
```

3. **重新鎖定版本 (Version Pinning)**
   - 更新 `requirements.txt` 並使用 `==` 鎖定版本。

4. **執行資安審核**
// turbo
```bash
/security-audit
```

5. **執行單元測試**
// turbo
```bash
pytest
```

---
**原則**:
- 嚴禁一次性大規模自動更新所有套件。
- 必須逐一更新、審計、測試，確保無破壞性變更。
- 所有變更必須符合 **Rule #11** 的精確版本鎖定要求。
