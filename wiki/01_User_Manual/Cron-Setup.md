# Cron Setup Guide

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Cron Setup Guide

### 1. Overview
This guide explains how to set up `cron` jobs on macOS/Linux to run AI Investment Advisor scans and reports regularly.

### 2. Scripts
Located in `scripts/`:
- **`run_daily_check.sh`**: Daily Momentum Scan. Runs in `Flash` mode. Detects significant changes.
- **`run_weekly_report.sh`**: Weekly Investment Report. Runs in `Deep` mode. Full analysis + Email.

### 3. Setup Steps
1.  Open Editor: `crontab -e`
2.  Add Schedule (Example):
    ```cron
    # Daily Check at 06:30 AM (Taipei Time)
    30 06 * * 1-5 /path/to/project/scripts/run_daily_check.sh >> /tmp/daily.log 2>&1

    # Weekly Report at 10:00 AM Sat
    00 10 * * 6 /path/to/project/scripts/run_weekly_report.sh >> /tmp/weekly.log 2>&1
    ```
3.  Verify: `crontab -l`

### 4. Notes
- Ensure scripts are executable (`chmod +x`).
- Check environment variables in scripts.

---

<a id="traditional-chinese"></a>

## 🇹🇼 自動化排程設定 (Cron Setup Guide)

### 1. 腳本概覽
專案提供了兩個主要的自動化腳本 (位於 `scripts/` 目錄)：

- `run_daily_check.sh`: **每日動能掃描 (Daily Momentum Scan)**
    - 執行模式: `Flash` (快速)
    - 目的: 檢測市場是否有顯著動能變化，若有則觸發 CIO Agent。
    - 建議時間: 每日美股收盤後 (e.g. 台北時間 05:30 或 06:30)。

- `run_weekly_report.sh`: **每週投資報告 (Weekly Investment Report)**
    - 執行模式: `Deep` (深入)
    - 目的: 執行完整的 Macro + Fundamental + Momentum 分析，並生成 CIO 總結報告。
    - 建議時間: 每週六早晨 (e.g. 台北時間 10:00)。

### 2. 設定步驟

#### 步驟 1: 開啟 Crontab 編輯器
在終端機輸入：
```bash
crontab -e
```

#### 步驟 2: 加入排程設定
請根據您的專案路徑修改以下指令：

```cron
# 每天台北時間 06:30 (美股收盤後) 執行每日掃描
30 06 * * 1-5 /Users/yourname/Work/go/投資策略建議/scripts/run_daily_check.sh >> /tmp/ai_advisor_daily.log 2>&1

# 每週六台北時間 10:00 執行完整週報
00 10 * * 6 /Users/yourname/Work/go/投資策略建議/scripts/run_weekly_report.sh >> /tmp/ai_advisor_weekly.log 2>&1
```

#### 步驟 3: 驗證
儲存並退出編輯器後，使用以下指令查看：
```bash
crontab -l
```

### 3. 注意事項
- **權限**: 確保 `.sh` 腳本具有執行權限 (`chmod +x scripts/*.sh`)。
- **環境變數**: 若依賴特定虛擬環境 (pipenv/conda)，需在腳本中設定。
