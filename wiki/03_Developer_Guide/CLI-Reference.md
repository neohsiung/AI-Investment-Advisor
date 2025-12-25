# CLI Reference Guide (CLI 參照指南)

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 CLI Reference Guide

The `src/cli.py` is the main entry point for the application, replacing the legacy `scheduler.py` and `workflow.py` scripts. It provides a unified interface for running various system components.

### Usage

```bash
python src/cli.py --mode <MODE> [OPTIONS]
```

### Modes

#### 1. Scheduler (`scheduler`)
Runs the long-running daemon that executes daily checks, weekly reports, and validation jobs based on the schedule configuration.

```bash
python src/cli.py --mode scheduler
```

#### 2. Daily Check (`daily`)
Manually triggers the daily portfolio scan for a specific user.

```bash
python src/cli.py --mode daily --user_id <EMAIL>
```

#### 3. Weekly Report (`weekly`)
Manually triggers the weekly analysis report generation.

- **Dry Run**: Generates the report and saves logs but does NOT send email.
- **Normal**: Generates and emails the report.

```bash
# Dry Run (Safe)
python src/cli.py --mode weekly --user_id <EMAIL> --dry-run

# Production Run
python src/cli.py --mode weekly --user_id <EMAIL>
```

#### 4. Backtest (`backtest`)
Runs the backtest simulation for a specific ticker to generate performance metrics and feedback data.

```bash
python src/cli.py --mode backtest --ticker <TICKER> [days_back]
```

#### 5. Optimizer (`optimize`)
Triggers the DSPy optimization pipeline to refine agent prompts based on accumulated feedback.

```bash
python src/cli.py --mode optimize
```

### Environment Variables
Ensure `.env` is loaded or variables are set:
- `DB_TYPE`: `sqlite` or `postgres`
- `OPENAI_API_KEY` (or Google/OpenRouter keys)
- `SMTP_SERVER`, `SENDER_EMAIL` (for reports)

---

<a id="traditional-chinese"></a>

## 🇹🇼 CLI 參照指南 (CLI Reference Guide)

`src/cli.py` 是本應用程式的主要進入點 (Entry Point)，它取代了舊有的 `scheduler.py` 與 `workflow.py` 腳本，提供了一個統一的介面來執行各種系統元件。

### 使用語法 (Usage)

```bash
python src/cli.py --mode <MODE> [OPTIONS]
```

### 模式 (Modes)

#### 1. 排程器 (`scheduler`)
執行長駐型守護進程 (Background Daemon)，根據設定的排程時間自動執行每日檢查、每週報告與驗證任務。

```bash
python src/cli.py --mode scheduler
```

#### 2. 每日檢查 (`daily`)
手動觸發針對特定用戶的每日投資組合掃描 (Daily Portfolio Scan)。

```bash
python src/cli.py --mode daily --user_id <EMAIL>
```

#### 3. 每週報告 (`weekly`)
手動觸發每週分析報告的生成流程。

- **Dry Run**: 僅生成報告並儲存日誌，**不會**發送 Email。
- **Normal**: 生成並發送 Email 報告。

```bash
# 試跑 (安全模式)
python src/cli.py --mode weekly --user_id <EMAIL> --dry-run

# 正式執行
python src/cli.py --mode weekly --user_id <EMAIL>
```

#### 4. 回測 (`backtest`)
針對特定股票代碼 (Ticker) 執行回測模擬，生成績效指標與反饋數據。

```bash
python src/cli.py --mode backtest --ticker <TICKER> [days_back]
```

#### 5. 優化器 (`optimize`)
觸發 DSPy 優化管道 (Optimizer Pipeline)，根據累積的反饋數據來優化 Agent 的提示詞 (Prompts)。

```bash
python src/cli.py --mode optimize
```

### 環境變數 (Environment Variables)
請確保已載入 `.env` 或已設定以下變數：
- `DB_TYPE`: `sqlite` 或 `postgres`
- `OPENAI_API_KEY` (或 Google/OpenRouter keys)
- `SMTP_SERVER`, `SENDER_EMAIL` (用於發送報告)
