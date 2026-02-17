---
description: 執行完整的安全性審查，包含代碼靜態分析與依賴項漏洞檢查 (Execute security audit including SAST and dependency checks)
---

### [資安審計工作流 (Security Audit Workflow)]

本工作流旨在確保代碼變更符合 **Rule #11 (Managed-Security-Base)**。

1. **靜態代碼分析 (Bandit)**
// turbo
```bash
bandit -r src/ -x tests/
```

2. **依賴項漏洞掃描 (Safety)**
// turbo
```bash
safety check -r requirements.txt
```

3. **依賴項完整性與安全性檢查 (Pip-audit)**
// turbo
```bash
pip-audit -r requirements.txt
```

4. **SQL 注入風險檢查 (Grep Pattern Check)**
// turbo
```bash
# 檢查 Raw SQL 是否使用了 f-string (違反 Rule #10)
grep -r "execute(f\"" src/
grep -r "execute(f'" src/
```

5. **硬編碼屬性/金鑰檢查**
// turbo
```bash
# 檢查是否存在疑似 API Key 的硬編碼字串
grep -rE "(key|token|password|secret)\s*=\s*['\"][a-zA-Z0-9]{10,}['\"]" src/
```

---
**結果處理**:
- 若有任何一項檢查輸出為 **CRITICAL** 或 **HIGH** 漏洞，Agent 必須停止當前任務，優先進行修復。
- 修復後，必須重新執行此工作流直至完全通過。
