---
description: 自動檢查測試覆蓋率並提供改進建議 (Automatically check test coverage and provide improvement suggestions)
---

# Test Coverage Check Workflow

## 目的 (Purpose)

在重大功能完成或 PR 提交前，自動檢查測試覆蓋率並識別需要補充測試的代碼區域。

## 觸發時機 (When to Run)

- ✅ 完成新功能開發後
- ✅ 提交 PR 前
- ✅ 定期檢查（建議每週）
- ✅ 覆蓋率低於 CI 門檻（70%）時

## 執行步驟 (Steps)

### 1. 執行完整測試套件

```bash
pytest --cov=src --cov-report=term --cov-report=html tests/
```

**輸出**: 
- 終端覆蓋率報告
- HTML 詳細報告 (`htmlcov/index.html`)

### 2. 比較基準線

當前基準:
- **目標**: > 75%
- **CI 門檻**: > 70% (pytest.ini: fail_under = 70)
- **v3.6 達成**: 75% (513+ tests, 1757 missed statements)

檢查指令:
```bash
# 查看當前覆蓋率
pytest --cov=src --cov-report=term-missing tests/ | grep "TOTAL"

# 識別未覆蓋檔案
pytest --cov=src --cov-report=term-missing tests/ | grep -A 100 "TOTAL"
```

### 3. 識別未覆蓋代碼

**優先順序排列**:

| 優先級 | 模組類型 | 目標覆蓋率 | 原因 |
|:-------|:---------|:-----------|:-----|
| P0 | Services 層 | > 80% | 核心業務邏輯 |
| P0 | Error handling | 100% | 關鍵錯誤路徑 |
| P1 | Repositories | > 75% | 資料持久化 |
| P1 | Agents | > 70% | Agent 邏輯 |
| P2 | UI/Pages | > 50% | Streamlit 元件（可選） |

### 4. 產出測試建議

根據未覆蓋代碼，建議建立:

**Service 層** (if coverage < 80%):
```python
# tests/test_{service_name}.py
- 正常流程測試 (happy path)
- 錯誤處理測試 (error paths)
  - API failures (401, 403, 429, 500)
  - Network timeouts
  - Malformed responses
- 邊界案例 (empty data, null values)
```

**Provider 層** (if coverage < 75%):
```python
# tests/test_{provider_name}.py
- Mocked API responses
- Rate limit handling
- Data validation
- Fallback mechanisms
```

### 5. 更新覆蓋率狀態

如果跨越重要門檻（如 75% → 76%），更新文檔:

- [ ] `wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md`
  - 更新版本紀錄
  - 更新當前覆蓋率數值

- [ ] `README.md` (if milestone achieved)
  - 更新測試覆蓋率徽章
  - 新增里程碑說明

## 成功標準 (Success Criteria)

- ✅ 總覆蓋率 ≥ 70% (CI 通過)
- ✅ Services 層覆蓋率 ≥ 80%
- ✅ 錯誤處理路徑已測試
- ✅ 新功能有對應測試

## 工具提示 (Tool Tips)

### 快速查看覆蓋率缺口
```bash
# 只顯示覆蓋率 < 75% 的檔案
pytest --cov=src --cov-report=term tests/ | awk '$NF < 75 {print}'
```

### 分析特定模組
```bash
pytest --cov=src/services --cov-report=term-missing tests/
```

### 產出 HTML 報告供查看
```bash
pytest --cov=src --cov-report=html tests/
open htmlcov/index.html  # macOS
```

## 參考 (References)

- [測試覆蓋率指南](../wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md)
- pytest 文檔: https://docs.pytest.org/en/stable/how-to/coverage.html
