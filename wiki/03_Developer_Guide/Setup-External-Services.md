# 外部服務設定指南 (External Services Setup Guide)

本指南說明如何申請與設定專案所需的外部服務 API Key，包括 FRED (總體經濟數據) 與其他潛在服務。

## 1. FRED API (總體經濟數據)

本專案使用 **FRED (Federal Reserve Economic Data)** API 來獲取關鍵總體經濟指標 (如 GDP, CPI, 失業率, 公債殖利率)，以供 Macro Agent 進行市場週期判斷。

### 步驟 1: 申請 API Key
1.  前往 [FRED API Key Request](https://fred.stlouisfed.org/docs/api/api_key.html) 頁面。
2.  若尚未登入，請先註冊一個免費的 FRED 帳號。
3.  在申請頁面填寫您的應用程式資訊。

### 步驟 2: 填寫申請表 (建議範本)
在 "Describe the application or program you intend to write" 欄位中，您可以參考以下範本 (請視情況修改)：

> **Application Description Suggestion:**
>
> "I am developing a personal investment analysis tool using Python. This application will fetch macroeconomic data (such as GDP, CPI, and Treasury Yields) to perform quantitative analysis and visualize economic trends for educational and personal research purposes. The data will not be redistributed."

### 步驟 3: 設定環境變數
取得 API Key 後，請將其加入專案根目錄的 `.env` 檔案中：

```bash
# .env file
FRED_API_KEY=your_fred_api_key_here
```

### 步驟 4: 驗證設定
您可以使用以下 Python 腳本測試 API Key 是否生效：

```python
from fredapi import Fred
fred = Fred(api_key='your_api_key_here')
data = fred.get_series('SP500')
print(data.tail())
```

---

## 2. Google Cloud (Optional)
(TBD: 未來補充 Google Cloud Project 與 OAuth 設定細節)

## 3. OpenAI / Gemini (Optional)
(TBD: 未來補充 LLM API Key 設定細節)
