
# Testing Guide

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 English

### Test Structure

The `tests/` directory mirrors the `src/` directory structure. We use `pytest` as our testing framework.

*   **Unit Tests**: Located in `tests/`, covering individual modules (e.g., `test_agents.py`, `test_utils.py`).
*   **Integration Tests**: Tests that involve multiple components (e.g., `test_workflow.py`).
*   **Smoke Tests**: Quick tests to verify critical paths (e.g., `test_dashboard_smoke.py`).
*   **Coverage**: We aim for high code coverage, tracked via `test_coverage_final.py` (which acts as a suite runner or specific coverage verification).

### Prerequisites

Ensure you have installed the development dependencies:

```bash
pip install -r requirements.txt
pip install pytest pytest-mock pytest-cov
```

### Running Tests

#### 1. Run All Tests
To run the entire test suite:

```bash
pytest tests/
```

#### 2. Run Specific Test File
 To run tests for a specific component, e.g., the Agents:

```bash
pytest tests/test_agents.py
```

#### 3. Run with Coverage Report
To see how much of the code is covered by tests:

```bash
pytest --cov=src tests/
```

### Mocking Strategy

We use `unittest.mock` extensively to isolate the system from external dependencies during testing.

*   **External APIs**: Calls to Google Gemini, OpenAI, and FRED are mocked.
*   **Database**: SQLite connections are mocked or use an in-memory database.
*   **Streamlit**: The `streamlit` and `extra_streamlit_components` libraries are mocked globally in `tests/conftest.py` or specific test headers (e.g., `test_coverage_final.py`) to prevent UI rendering errors during CLI testing.

**Important**: When writing new tests involving Streamlit, ensure you verify the global mocks in `tests/test_coverage_final.py` or apply similar patching to avoid `RuntimeError`.

### CI/CD Integration

Tests are automatically triggered on every push to the `main` branch via GitHub Actions. Check `.github/workflows` for the configuration.

---

<a id="traditional-chinese"></a>

## 🇹🇼 繁體中文 (Traditional Chinese)

### 測試結構 (Test Structure)

`tests/` 目錄結構對應 `src/` 目錄。我們使用 `pytest` 作為測試框架。

*   **單元測試 (Unit Tests)**: 位於 `tests/`，覆蓋個別模組 (例如 `test_agents.py`, `test_utils.py`)。
*   **整合測試 (Integration Tests)**: 涉及多個組件的測試 (例如 `test_workflow.py`)。
*   **冒煙測試 (Smoke Tests)**: 快速驗證關鍵路徑的測試 (例如 `test_dashboard_smoke.py`)。
*   **覆蓋率 (Coverage)**: 我們致力於高程式碼覆蓋率，透過 `test_coverage_final.py` 追蹤。

### 前置準備 (Prerequisites)

確保您已安裝開發依賴套件：

```bash
pip install -r requirements.txt
pip install pytest pytest-mock pytest-cov
```

### 執行測試 (Running Tests)

#### 1. 執行所有測試
執行整個測試套件：

```bash
pytest tests/
```

#### 2. 執行特定測試檔案
例如，只測試 Agents 組件：

```bash
pytest tests/test_agents.py
```

#### 3. 執行並產生覆蓋率報告
查看程式碼測試覆蓋率：

```bash
pytest --cov=src tests/
```

### Mocking 策略 (Mocking Strategy)

我們大量使用 `unittest.mock` 來在測試期間隔離外部依賴。

*   **外部 API**: Mock Google Gemini, OpenAI, 和 FRED 的 API 呼叫。
*   **資料庫**: Mock SQLite 連線或使用記憶體資料庫。
*   **Streamlit**: `streamlit` 與 `extra_streamlit_components` 套件在 `tests/conftest.py` 或特定測試檔頭 (如 `test_coverage_final.py`) 進行全域 Mock，以避免在 CLI 測試時發生 UI 渲染錯誤。

**重要**: 當撰寫涉及 Streamlit 的新測試時，請確保參考 `tests/test_coverage_final.py` 中的 Mock 設定，或應用類似的 Patch 以避免 `RuntimeError`。

### CI/CD 整合

測試會在每次 Push 到 `main` 分支時透過 GitHub Actions 自動觸發。請查看 `.github/workflows` 以了解詳細設定。
