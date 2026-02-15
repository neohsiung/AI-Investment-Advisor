# Test Coverage Policy

## 目标 (Target)

### 总体要求
- 🎯 **总覆盖率目标**: > 75%
- ⚠️ **CI/CD门槛**: > 70% (`pytest.ini`: `fail_under = 70`)
- ✅ **当前状态 (v3.6)**: **75%** (513+ tests, 1757 missed statements)

### 分层要求

| 代码层 | 目标覆盖率 | 原因 |
|:-------|:-----------|:-----|
| **Services层** | > 80% | 核心业务逻辑，关键路径 |
| **Repositories层** | > 75% | 数据持久化，保证可靠性 |
| **Agents层** | > 70% | Agent逻辑，允许更多灵活性 |
| **Domain层** | > 85% | 领域模型，高度稳定 |
| **Error Handling** | 100% | 错误路径必须测试 |
| **UI/Pages** | > 50% | Streamlit组件，**可选**（ROI低） |

## 强制要求 (Mandatory)

### 1. 新功能必须包含测试

**触发时机**:
- ✅ 新增service/repository/agent
- ✅ 新增public API方法
- ✅ 修改核心业务逻辑

**要求**:
- 正常流程测试（happy path）
- 错误处理测试（error paths）
- Edge cases测试

**示例（Service新增方法）**:
```python
# src/services/analytics_service.py
def calculate_leverage(self, net_equity, loan):
    if net_equity <= 0:
        raise ValueError("Net equity must be positive")
    return loan / net_equity

# tests/test_analytics_service.py
def test_calculate_leverage_happy_path():
    service = AnalyticsService()
    assert service.calculate_leverage(100, 50) == 0.5

def test_calculate_leverage_zero_equity():
    service = AnalyticsService()
    with pytest.raises(ValueError):
        service.calculate_leverage(0, 50)

def test_calculate_leverage_negative_equity():
    service = AnalyticsService()
    with pytest.raises(ValueError):
        service.calculate_leverage(-100, 50)
```

### 2. 错误处理路径必须测试

**强制测试的错误类型**:

#### API/Network错误
- `401 Unauthorized`
- `403 Forbidden`
- `429 Rate Limit`
- `500 Internal Server Error`
- `Network timeout`
- `Malformed JSON response`

**示例**:
```python
@patch('requests.get')
def test_fetch_data_401_error(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_get.return_value = mock_response
    
    provider = DataProvider()
    result = provider.fetch_data('AAPL')
    
    assert len(result) == 0  # or handle gracefully
```

#### 数据验证错误
- `None` values
- Empty lists/dicts
- Invalid types
- Out of range values

#### 数据库错误
- Connection failures
- Constraint violations
- Transaction rollbacks

### 3. Service层覆盖率 > 80%

**检查命令**:
```bash
pytest --cov=src/services --cov-report=term-missing tests/
```

**如果<80%**:
1. 识别未覆盖的方法
2. 优先测试public方法
3. 测试错误处理路径
4. 添加edge case测试

### 4. 覆盖率不得下降

**CI检查**:
- PR提交时运行coverage check
- 如果总覆盖率 < 70% → **CI失败**
- 如果Service层覆盖率 < 80% → **警告**（允许但需说明）

## 可选要求 (Optional)

### UI/Pages测试

**策略**: Best Effort（尽力而为）

**原因**:
- Streamlit mocking复杂度高
- ROI（回报率）低
- 测试脆弱，易受框架变更影响

**如果测试UI**:
- 使用centralized mocking (tests/conftest.py)
- 只测试核心交互逻辑
- 避免测试UI渲染细节

**目标**: > 50% (非强制)

## 测试优先级 (Test Priorities)

### P0 - 必须测试
1. 错误处理路径（所有error paths）
2. Services层核心方法
3. Repository CRUD操作
4. Domain entities业务逻辑

### P1 - 应该测试
1. Agent run()方法主流程
2. Provider API调用（mocked）
3. Workflow关键步骤
4. 配置加载逻辑

### P2 - 可选测试
1. UI pages交互
2. Utility简单函数
3. Infrastructure辅助类

## 最佳实践 (Best Practices)

### 1. 优先测试Service层而非UI

**经验**（来自v3.6 75%达成）:
- Service层测试ROI **高**
- UI测试ROI **低**（complex mocking）
- 54个Service层测试 = -34 missed statements

### 2. Real Integration > Mocks（适用场景）

**适合真实集成测试**:
- SQLite database operations
- File I/O operations
- In-memory caches

**适合Mock**:
- 外部API调用（Polygon, FMP）
- Network requests
- LLM调用（昂贵）

### 3. 测试错误路径，而非仅happy path

**经验**: 错误处理代码往往0%覆盖率，但容易测试

**示例**:
```python
# 只测happy path → 覆盖率50%
def test_fetch_data():
    result = provider.fetch_data('AAPL')
    assert len(result) > 0

# 加上error path → 覆盖率90%
def test_fetch_data_api_error():
    # mock 500 error
    with pytest.raises(APIError):
        provider.fetch_data('INVALID')
```

## 覆盖率报告 (Coverage Reports)

### 生成报告
```bash
# Terminal report
pytest --cov=src --cov-report=term-missing tests/

# HTML report (详细)
pytest --cov=src --cov-report=html tests/
open htmlcov/index.html
```

### 识别Gap
```bash
# 只显示<75%的文件
pytest --cov=src --cov-report=term tests/ | awk '$NF < 75 {print}'
```

### 更新文档

当跨越重要门槛时（如74% → 75%），更新:
- `wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md`
- `README.md`（如达成新milestone）

## CI/CD配置

`pytest.ini`:
```ini
[pytest]
addopts = --cov=src --cov-report=term-missing
testpaths = tests
filterwarnings = ignore::DeprecationWarning

[coverage:run]
omit = 
    */tests/*
    */__pycache__/*
    */venv/*

[coverage:report]
fail_under = 70  # CI门槛
precision = 2
```

## 例外情况 (Exceptions)

### 允许低覆盖率的情况

1. **Legacy code**（待废弃代码）- 标注`# pragma: no cover`
2. **Debug utilities** - 调试工具
3. **UI-only components** - 纯Streamlit组件（无业务逻辑）

**标注方式**:
```python
def debug_helper():  # pragma: no cover
    # This is only for manual debugging
    ...
```

### 暂时豁免

如果新功能暂时无法达到80%覆盖率:
1. 在PR中说明原因
2. 创建TODO item跟踪
3. 计划在下一个sprint补充

## 参考 (References)

- [v3.6 Test Coverage Walkthrough](../brain/walkthrough.md)
- [测试与外部服务整合指南](../wiki/03_開發者指南-Developer_Guide/測試與外部服務整合-Testing-External-Services.md)
- pytest coverage docs: https://pytest-cov.readthedocs.io/
