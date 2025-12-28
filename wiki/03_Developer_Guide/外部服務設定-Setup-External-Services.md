# External Services Setup Guide

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 External Services Setup Guide

### 1. FRED API (Macro Data)
Used by Macro Agent to fetch GDP, CPI, etc.

#### Steps
1.  Request Key: [FRED API Page](https://fred.stlouisfed.org/docs/api/api_key.html).
2.  Description: "Developing a personal Python tool for quantitative investment research."
3.  Set Env: Add `FRED_API_KEY` to `.env`.

### 2. LLM APIs (OpenAI / Gemini / OpenRouter)
Get your API key from the respective provider and set `API_KEY` in `.env`.

---

<a id="traditional-chinese"></a>

## 🇹🇼 外部服務設定指南 (External Services Setup Guide)

### 1. FRED API (總體經濟數據)
本專案使用 **FRED** API 來獲取關鍵總體經濟指標 (如 GDP, CPI)。

#### 步驟 1: 申請 API Key
前往 [FRED API Key Request](https://fred.stlouisfed.org/docs/api/api_key.html) 申請。

#### 步驟 2: 設定環境變數
將 Key 加入 `.env`：
```bash
FRED_API_KEY=your_key_here
```

### 2. LLM API (OpenAI / Gemini)
請至對應服務商取得 API Key，並在 `.env` 中設定 `API_KEY` 與 `AI_PROVIDER`。
