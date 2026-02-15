---
description: 自动检查测试覆盖率并提供改进建议
---

# Test Coverage Check Workflow

## 目的 (Purpose)

在重大功能完成或PR提交前，自动检查测试覆盖率并识别需要补充测试的代码区域。

## 触发时机 (When to Run)

- ✅ 完成新功能开发后
- ✅ 提交PR前
- ✅ 定期检查（建议每周）
- ✅ 覆盖率低于CI门槛（70%）时

## 执行步骤 (Steps)

### 1. 运行完整测试套件

```bash
pytest --cov=src --cov-report=term --cov-report=html tests/
```

**输出**: 
- 终端覆盖率报告
- HTML详细报告 (`htmlcov/index.html`)

### 2. 比较基准线

当前基准:
- **目标**: > 75%
- **CI门槛**: > 70% (pytest.ini: fail_under = 70)
- **v3.6达成**: 75% (513+ tests, 1757 missed statements)

检查命令:
```bash
# 查看当前覆盖率
pytest --cov=src --cov-report=term-missing tests/ | grep "TOTAL"

# 识别未覆盖文件
pytest --cov=src --cov-report=term-missing tests/ | grep -A 100 "TOTAL"
```

### 3. 识别未覆盖代码

**优先级排序**:

| 优先级 | 模块类型 | 目标覆盖率 | 原因 |
|:-------|:---------|:-----------|:-----|
| P0 | Services层 | > 80% | 核心业务逻辑 |
| P0 | Error handling | 100% | 关键错误路径 |
| P1 | Repositories | > 75% | 数据持久化 |
| P1 | Agents | > 70% | Agent逻辑 |
| P2 | UI/Pages | > 50% | Streamlit组件（可选） |

### 4. 生成测试建议

根据未覆盖代码，建议创建:

**Service层** (if coverage < 80%):
```python
# tests/test_{service_name}.py
- 正常流程测试 (happy path)
- 错误处理测试 (error paths)
  - API failures (401, 403, 429, 500)
  - Network timeouts
  - Malformed responses
- Edge cases (empty data, null values)
```

**Provider层** (if coverage < 75%):
```python
# tests/test_{provider_name}.py
- Mocked API responses
- Rate limit handling
- Data validation
- Fallback mechanisms
```

### 5. 更新覆盖率状态

如果跨越重要门槛（如75% → 76%），更新文档:

- [ ] `wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md`
  - 更新版本纪录
  - 更新当前覆盖率数值

- [ ] `README.md` (if milestone achieved)
  - 更新测试覆盖率徽章
  - 添加里程碑说明

## 成功标准 (Success Criteria)

- ✅ 总覆盖率 ≥ 70% (CI通过)
- ✅ Services层覆盖率 ≥ 80%
- ✅ 错误处理路径已测试
- ✅ 新功能有对应测试

## 工具提示 (Tool Tips)

### 快速查看覆盖率缺口
```bash
# 只显示覆盖率<75%的文件
pytest --cov=src --cov-report=term tests/ | awk '$NF < 75 {print}'
```

### 分析特定模块
```bash
pytest --cov=src/services --cov-report=term-missing tests/
```

### 生成HTML报告供查看
```bash
pytest --cov=src --cov-report=html tests/
open htmlcov/index.html  # macOS
```

## 参考 (References)

- [测试覆盖率指南](../wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md)
- [V3.6 75%达成Walkthrough](../brain/walkthrough.md)
- pytest文档: https://docs.pytest.org/en/stable/how-to/coverage.html
