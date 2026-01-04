# 測試與外部服務整合 (Testing & External Services)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 測試與外部服務整合指南

本文件詳述如何驗證系統正確性，以及如何配置第三方數據源與身份驗證。

### 1. 測試指南 (Testing Guide)
- **框架**: 使用 `pytest` 與 `pytest-cov`。
- **規範**: 覆蓋率目標為 **>75%**。涉及 Streamlit 的測試必須使用 `mock_streamlit_module` fixture。
- **指令**:
    ```bash
    pytest                # 執行所有測試
    pytest --cov=src      # 產生覆蓋率報告
    ```

### 2. 第三方服務配置 (3rd-Party Setup)
| 服務 | 用途 | 主要環境變數 |
| :--- | :--- | :--- |
| **Polygon.io** | 即時/延遲股價 | `POLYGON_API_KEY` |
| **FMP** | 財報、財經新聞 | `FMP_API_KEY` |
| **FRED** | 總體經濟數據 | `FRED_API_KEY` |
| **Tavily** | AI 搜尋引擎 | `TAVILY_API_KEY` |
| **Gemini** | 核心推理 (LLM) | `GOOGLE_API_KEY` |

**常見問題解決**: 若遇到搜尋超時 (`Timeout`)，請優先確認 `TAVILY_API_KEY` 是否有效。系統預設提供 DuckDuckGo 作為無金鑰備援，但穩定性較低。

### 3. Google OAuth 設定
1.  前往 Google Cloud Console 建立 **OAuth 2.0 用戶端 ID**。
2.  **Redirect URI**: 本地使用 `http://localhost:8501`；雲端使用 Cloud Run 網址。
3.  下載 `client_secret.json` 並放置於專案根目錄。

---

<a id="en"></a>

## 🇺🇸 Testing & External Services

### 1. Testing
- **Goal**: Maintain **>75% coverage**.
- **Strategy**: Use `pytest`. Mock Streamlit using provided fixtures in `conftest.py`.
- **Run**: `pytest --cov=src`

### 2. External Services
- **Data**: Polygon (Price), FMP (Financials), FRED (Macro).
- **Search**: Tavily (Preferred) or DuckDuckGo (Fallback).
- **AI**: Google Gemini 1.5 Pro/Flash via `GOOGLE_API_KEY`.

### 3. Google OAuth
- **Credentials**: Required for user login.
- **URI**: Match exactly in Google Console (`http://localhost:8501` for locally).
- **Secret**: Store `client_secret.json` in root or in env var.

## 🔗 See Also
- [Environment & Local Dev](wiki/03_開發者指南-Developer_Guide/環境設定與本地開發-Environment-Local-Dev.md)
- [Database & Git Standards](wiki/03_開發者指南-Developer_Guide/資料庫設計與代碼規範-Database-Git-Standards.md)
