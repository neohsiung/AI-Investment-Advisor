# 自動化排程設定 (Cron Setup Guide)

本指南說明如何在 macOS/Linux 環境下使用 `cron` 設定定期執行 AI 投資顧問的掃描與報告任務。

## 1. 腳本概覽

專案提供了兩個主要的自動化腳本 (位於 `scripts/` 目錄)：

- `run_daily_check.sh`: **每日動能掃描 (Daily Momentum Scan)**
    - 執行模式: `Flash` (快速)
    - 目的: 檢測市場是否有顯著動能變化，若有則觸發 CIO Agent。
    - 建議時間: 每日美股收盤後 (e.g. 台北時間 05:30 或 06:30)。

- `run_weekly_report.sh`: **每週投資報告 (Weekly Investment Report)**
    - 執行模式: `Deep` (深入)
    - 目的: 執行完整的 Macro + Fundamental + Momentum 分析，並生成 CIO 總結報告。
    - 建議時間: 每週六早晨 (e.g. 台北時間 10:00)。

## 2. 設定步驟

### 步驟 1: 開啟 Crontab 編輯器
在終端機輸入：
```bash
crontab -e
```

### 步驟 2: 加入排程設定
請根據您的專案路徑修改以下指令 (假設專案位於 `/Users/yourname/Work/go/投資策略建議`)。

```cron
# 每天台北時間 06:30 (美股收盤後) 執行每日掃描
30 06 * * 1-5 /Users/yourname/Work/go/投資策略建議/scripts/run_daily_check.sh >> /tmp/ai_advisor_daily.log 2>&1

# 每週六台北時間 10:00 執行完整週報
00 10 * * 6 /Users/yourname/Work/go/投資策略建議/scripts/run_weekly_report.sh >> /tmp/ai_advisor_weekly.log 2>&1
```

### 步驟 3: 驗證
儲存並退出編輯器後，您可以使用以下指令查看目前的排程：
```bash
crontab -l
```

## 3. 注意事項
- **權限**: 確保 `.sh` 腳本具有執行權限 (`chmod +x scripts/*.sh`)。
- **環境變數**: 腳本中已設定 `PYTHONPATH`，但若依賴特定虛擬環境 (pipenv/conda)，可能需要在腳本中先 `source activate`。
- **通知**: 目前腳本設定為使用 macOS `osascript` 發送桌面通知，若在無頭伺服器 (Headless Server) 執行可能會報錯，建議修改腳本移除通知部分或改用 Email 通知。
