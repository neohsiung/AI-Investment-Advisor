# 🧪 測試指南 (Testing Guide)

## 📊 測試覆蓋率狀態 (Coverage Status)
截至 **v3.2** Release:
- **總體覆蓋率**: **76%** (Target: >75%)
- **總測試數**: 219 (All Passing)
- **Critical Paths**: Auth (89%), Utils (100%), Services (80%+)

## 🛠️ 測試架構
我們使用 `pytest` 作為主要框架，配合 `pytest-cov` 進行覆蓋率分析。

### 1. Fixtures (`tests/conftest.py`)
為了避免全域模組污染 (Test Pollution)，我們在 v3.2 引入了 `mock_streamlit_module` fixture。
**重要**: 所有涉及 Streamlit 的單元測試 **必須** 使用此 fixture，嚴禁直接在檔案開頭 `sys.modules['streamlit'] = MagicMock()`。

```python
def test_example(mock_streamlit_module):
    # Safe to use streamlit logic
    pass
```

### 2. Mocking Strategy
- **Service Layer**: 使用 `unittest.mock.patch` 隔離 Repository。
- **UI Layer**: 使用 `mock_streamlit_module` 模擬 Session State 與 Interaction。
- **Auth**: 使用 `mock_streamlit_module` 並透過 `importlib.reload` 確保模組讀取正確的 Mock。

## 🏃 執行測試
```bash
# 執行所有測試
pytest

# 產生覆蓋率報告
pytest --cov=src 

# 執行特定模組
pytest tests/test_auth_manager.py
```

### 前置準備 (Prerequisites)

確保您已安裝開發依賴套件：

```bash
pip install -r requirements.txt
pip install pytest pytest-mock pytest-cov
```

### CI/CD 整合

測試會在每次 Push 到 `main` 分支時透過 GitHub Actions 自動觸發。請查看 `.github/workflows` 以了解詳細設定。

---

<a id="en"></a>

## 🇺🇸 Testing Guide

## 📊 Coverage Status
As of **v3.2** Release:
- **Total Coverage**: **76%** (Target: >75%)
- **Total Tests**: 219 (All Passing)
- **Critical Paths**: Auth (89%), Utils (100%), Services (80%+)

## 🛠️ Testing Architecture
We use `pytest` as the main framework with `pytest-cov`.

### 1. Fixtures (`tests/conftest.py`)
To avoid **Test Pollution**, we introduced `mock_streamlit_module` fixture in v3.2.
**Important**: All unit tests involving Streamlit **MUST** use this fixture. DO NOT globally mock `sys.modules['streamlit']` at the top of files.

```python
def test_example(mock_streamlit_module):
    # Safe to use streamlit logic
    pass
```

### 2. Mocking Strategy
- **Service Layer**: Use `unittest.mock.patch` to isolate Repositories.
- **UI Layer**: Use `mock_streamlit_module` to simulate Session State.
- **Auth**: Use `mock_streamlit_module` and `importlib.reload` to ensure correct Mock injection.

## 🏃 Running Tests
```bash
# Run all tests
pytest

# Generate Coverage
pytest --cov=src

# Run specific module
pytest tests/test_auth_manager.py
```

### Prerequisites

Ensure you have installed the development dependencies:

```bash
pip install -r requirements.txt
pip install pytest pytest-mock pytest-cov
```

### CI/CD Integration

Tests are automatically triggered on every push to the `main` branch via GitHub Actions. Check `.github/workflows` for the configuration.
