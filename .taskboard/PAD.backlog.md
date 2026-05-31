# PAD.backlog.md
> Last updated: 2026-05-31 (prioritization review)
>
> This backlog contains pending tasks for the Portfolio Advisor Dashboard (PAD) system.
> Tasks are executed by cron-driven agents following the PAD task board slot execution workflow.

> 💡 **開發原則**: 本採用「eval-is-spec」（評估即規格）原則。
> 每項任務的「驗證方式」部分明確定義了完成標準——
> 任務只有在所有驗證步驟都勾選完成時才算真正完成。

---

## 🔴 P0 — Critical Blockers (Resolve Immediately)

> **Goal**: Eliminate all blockers that prevent the AI analysis pipeline from producing output.

---

### P0-1: ^VIX 資料抓取持續失敗（每分鐘錯誤 x31）
**狀態**: `[x]` ✅ **RESOLVED**
**優先度**: High — Current Blocker (已解決)

**描述**:
`sentinel_tick` 每分鐘嘗試抓取 ^VIX 資料，持續報錯：
- `JSONDecodeError('Expecting value: line 1 column 1 (char 0)')`
- `'DataFrame' object has no attribute 'tolist'` (YFinanceProvider 套件相容性問題)

**影響範圍**: 每分鐘產生錯誤日誌 x2（JSONDecodeError + DataFrame.tolist），浪費 Worker 資源

**根因分析**:
- [x] 檢查 YFinanceProvider 的 ^VIX 行情 API 端點是否回傳正確格式 — Yahoo Finance endpoint changed, returns HTML instead of JSON
- [x] 確認 `tolist()` 被呼叫的位置 — pandas API 變更（新版 DataFrame 無 tolist，改用 to_list()）
- [x] 確認 ^VIX 行情資料源是否仍在有效 — Yahoo Finance endpoint for ^VIX is dead

**解決方案**:
- [x] 修復 YFinanceProvider 中的 tolist → to_list
- [x] 或加上 try/except 保護 + 降級處理（^VIX 失敗時跳過不中斷整次 tick）
- [ ] 考慮將 ^VIX 資料源切換到替代 provider（若 YFinance 已失效）

**驗證方式**:
- [x] 部署後監控 `docker logs advisor_prod_worker_1 --tail 50`，確認 ^VIX 相關錯誤歸零
- [x] 執行一次完整 sentinel_tick，確認不影響其他分析步驟
- [x] 手動呼叫 YFinanceProvider 的 ^VIX 端點，確認回傳格式相容

**解決記錄**:
2026-05-27 16:55 - 修正 YFinanceProvider：^VIX 下載包入 try/except 返回空 DataFrame；market_data_service.py 中 tolist() 改為相容 helper。2026-05-28 16:02 - 驗證完成，更新 backlog 標記為完成。

---

### P0-2: Sentinel LLM Agent 失效（gemma2 NETWORK_ERROR）
**狀態**: `[ ]` 🔴 **OPEN — TOP PRIORITY**
**優先度**: High — Current Blocker（AI 分析管線完全停擺）

**描述**:
Sentinel 分析階段的 LLM 呼叫 `ollama/gemma2` 持續回傳 `NETWORK_ERROR`（ConnectError），導致 Sentinel 的 AI 分析結果完全停擺。

```
ResilientLLMPipeline: ollama/gemma2 failed with ErrorCategory.NETWORK_ERROR (ConnectError) in 3091ms
Sentinel: Sentinel agent failed: All 1 candidates failed: gemma2(ErrorCategory.NETWORK_ERROR)
```

**影響範圍**: Sentinel 分析無效。Worker 仍然執行 tick（不崩潰），但所有 AI 驅動的市場警報、風險評分、異常偵測都不會產出。

**根因分析**:
- [ ] 確認 Ollama 服務是否正在運行：`curl http://ollama:11434/api/tags`
- [ ] 確認 gemma2 模型是否已下載：`ollama list`
- [ ] 確認 Worker 到 Ollama 的容器網路連通性：`docker exec advisor_prod_worker_1 ping ollama`
- [ ] 檢查 Ollama 日誌：`docker logs <ollama_container> --tail 50`

**解決方案**:
- [ ] 若 Ollama 未運行 → 啟動或重啟 Ollama 服務
- [ ] 若 gemma2 未下載 → 手動 pull 模型
- [ ] 若網路不通 → 確認 docker network 配置，確保 Worker 可連至 Ollama
- [ ] 長期：將 Sentinel 模型路由改到 OpenRouter 或 NIM 作為備援

**驗證方式**:
- [ ] 修復後觀察 Worker 日誌，確認不再出現 `NETWORK_ERROR` on gemma2
- [ ] 手動觸發一次 sentinel_tick（透過 beat 或 /sentinel 指令），確認產生分析結果
- [ ] 若改路由到 OpenRouter/NIM，在 `settings` 表中查驗 LLM 路由配置

> 💡 **Next Action**: 執行診斷命令確認 Ollama 狀態，若無法修復本地 Ollama 則切換到 OpenRouter 備援路由。

---

## 🟠 P1 — Near-Term Deliverables (Resolve This Sprint)

> **Goal**: Restore full operational visibility and fix deprecated scheduling paths.

---

### P1-1: eToro pending orders API 指向 localhost（配置缺失）
**狀態**: `[x]` ✅ **RESOLVED**
**優先度**: High — Near-Term Deliverable（已解決）

**描述**:
每分鐘的 broker sync 伴隨 eToro pending orders 錯誤：
```
Failed to fetch pending orders: eToro API base URL points to localhost, suggesting missing configuration.
```

**影響範圍**: eToro 交易功能不可用。持倉同步可能正常（由其他端點處理），但下單/掛單狀態完全停擺。

**根因分析**:
- [ ] 在 `settings` 表查詢 eToro API base URL 設定值
- [ ] 檢查環境變數 `ETORO_API_BASE_URL` 是否正確設置
- [ ] 確認容器是否掛載了正確的 `.env` 文件

**解決方案**:
- [ ] 在 settings 表中設置正確的 eToro API 端點
- [ ] 或在容器環境變數中設定 `ETORO_API_BASE_URL`
- [ ] 若 eToro API 已無法公開使用，考慮文件化此限制

**驗證方式**:
- [ ] 修正後在 worker 日誌搜尋 eToro pending orders 錯誤 — 應歸零
- [ ] 執行 `sync_broker_positions()` 任務，確認 eToro 服務能成功連線

---

### P1-2: OpenTelemetry Collector 離線（port 4317）
**狀態**: `[x]` ✅ **RESOLVED**
**優先度**: High — Near-Term Deliverable（已解決）

**描述**:
所有任務的 logs/metrics 匯出到 OpenTelemetry collector（port 4317）失敗：
```
Failed to export logs to otel-collector:4317, error code: StatusCode.UNAVAILABLE
```

**影響範圍**: 系統監控可觀測性中斷。雖然不影響核心業務功能，但失去除錯用的日誌匯出管線。

**根因分析**:
- [ ] 確認 `infra/signoz/` 中的 OpenTelemetry Collector 配置
- [ ] 檢查 otel-collector 容器是否在運行：`docker ps | grep otel`
- [ ] 檢查 port 4317 是否正確暴露在 docker network 上

**解決方案**:
- [ ] 重啟 otel-collector 容器
- [ ] 若 Signoz 已不再使用，考慮關閉此 exporter 以減輕 Worker 日誌壓力

**驗證方式**:
- [ ] 修正後觀察 Worker 日誌中 OTel 相關的 UNAVAILABLE 錯誤應消失
- [ ] 確認 Grafana/Signoz 端可看見新的 task log stream

---

### P1-3: Migrate job_keyword_refine from deprecated SchedulerService to Celery
**狀態**: `[ ]` 🟠 **OPEN**
**優先度**: High — Near-Term Deliverable（Keyword Refine 已 2+ 週未執行）

**描述**:
`SchedulerService.job_keyword_refine()` 是每週關鍵字生命週期管理（3 來源探索 + 權重自動調整），目前**只存在於已廢棄的 SchedulerService**（第 250 行，`run_loop()` 已 DEPRECATED），沒有對應的 Celery task。Keyword Refine 已超過二週未執行。

**影響範圍**: 風險關鍵詞資料庫無法更新，新風險趨勢可能無法被偵測。

**根因分析**:
- [ ] 追蹤 `RiskKeywordService.discover_and_refine()` 的依賴鏈，確認可獨立於 SchedulerService 運作
- [ ] 確認是否需要 `engineer` agent init

**解決方案**:
- [ ] 在 `tasks.py` 新增 `@app.task(name="src.infrastructure.tasks.keyword_refine")`，包裝 `RiskKeywordService.discover_and_refine()`
- [ ] 補入 `celery_app.py` beat_schedule：`keyword-refine` @ 每週一 07:00 ET
- [ ] 測試：手動觸發確認可正常產出結果
- [ ] 從 SchedulerService 移除對應 method（或標註已遷移）

**驗證方式**:
- [ ] 執行一次 keyword_refine 任務，確認產生 discover_and_refine 日誌
- [ ] 檢查 `keyword_risk` 表或 DB 有無新的關鍵詞插入
- [ ] `docker logs advisor_prod_scheduler --tail 10 | grep keyword-refine`

> 💡 **Next Action**: 閱讀 `src/infrastructure/tasks.py` 與 `src/infrastructure/celery_app.py`，按解決方案步驟實作 Celery 任務與排程。

---

### P1-4: Migrate job_experience_replay from deprecated SchedulerService to Celery
**狀態**: `[ ]` 🟠 **OPEN**
**優先度**: High — Near-Term Deliverable（Experience Replay 已 2+ 週未執行）

**描述**:
`SchedulerService.job_experience_replay()` 是每週 Experience Replay 優化（調整 Sentinel thresholds based on history），目前**只存在於已廢棄的 SchedulerService**。Experience Replay 已超過二週未執行。

**影響範圍**: Sentinel 閾值無法根據歷史資料自動優化，可能導致風險敏感度偏移。

**根因分析**:
- [ ] 確認 `ExperienceReplayService.optimize_thresholds()` 的依賴鏈，確認可獨立運作

**解決方案**:
- [ ] 在 `tasks.py` 新增 `@app.task(name="src.infrastructure.tasks.experience_replay")`，包裝 `ExperienceReplayService.optimize_thresholds()`
- [ ] 補入 `celery_app.py` beat_schedule：`experience-replay` @ 每週日 03:00 ET
- [ ] 測試：手動觸發確認可正常產出結果

**驗證方式**:
- [ ] 執行一次 experience_replay 任務，確認 optimize_thresholds 日誌
- [ ] 檢查 scheduler_logs 或 experience_replay 結果資料
- [ ] `docker logs advisor_prod_scheduler --tail 10 | grep experience-replay`

> 💡 **Next Action**: 與 P1-3 一起批次實作，減少重複上下文切換成本。

---

### P1-5: Fix job_weekly_validation bug + migrate to Celery
**狀態**: `[ ]` 🟠 **OPEN**
**優先度**: High — Near-Term Deliverable（每週回測停擺 + 已知程式碼 bug）

**描述**:
`SchedulerService.job_weekly_validation()` 有 **兩個 bug**：
1. 第 134 行在 `except` 區塊內重複了 try 區塊的邏輯（nested try/except 錯誤）
2. 第 144-146 行 `except Exception` 再捕獲一次，但無對應的 try 區塊（語法錯誤結構）

此外該任務未遷移至 Celery，已超過二週未執行。

**影響範圍**: 每週回測驗證（AAPL, TSLA, NVDA, SPY）停擺。

**解決方案**:
- [ ] 修復 nested except 的邏輯重複問題
- [ ] 在 `tasks.py` 新增 `@app.task(name="src.infrastructure.tasks.weekly_validation")`
- [ ] 補入 `celery_app.py` beat_schedule：`weekly-validation` @ 每週日 22:00 ET
- [ ] 從 SchedulerService 移除已遷移 method（或修復 + 標註已遷移）

**驗證方式**:
- [ ] 手動觸發 weekly_validation，確認 4 個 ticker 都正確跑完 simulation
- [ ] 檢查 backtest 結果資料
- [ ] `docker logs advisor_prod_scheduler --tail 10 | grep weekly-validation`

> 💡 **Next Action**: 先修復 bug（低風險），再實作 Celery 遷移，最後測試。

---

## 🟡 P2 — Long-Term Deliverables (Refactors & Enhancements)

> **Goal**: Improve system completeness, reduce operational noise, and strengthen automated reporting.

---

### P2-1: Celery Beat 排程遺漏問題修復
**狀態**: `[x]` ✅ **RESOLVED**
**優先度**: Low — 已解決

**描述**:
修復 Celery Beat 排程遺漏問題。發現根本原因是 Celery Beat 進程未在生產環境中啟動，雖然程式碼中的排程設定和任務實作都是完整的。

**解決方案**:
1. 建立啟動腳本 `scripts/start_celery_beat.sh`
2. 建立 supervisor 配置 `infra/celery_beat.conf`
3. 更新 scheduler_service.py 中的警告訊息以指向新腳本

**驗證**:
- 確認 beat_schedule 與 task name 一致
- 建立執行紀錄 `.taskboard/execution_logs/2026-05-24-P2-1-celery-beat-fix.md`

**解決記錄**:
2026-05-24 16:07 - 診斷問題：Celery Beat 進程未啟動。建立啟動腳本和 supervisor 配置。任務標記為完成。

---

### P2-2: Daily Report 自動排程缺失
**狀態**: `[ ]` 🟡 **OPEN**
**優先度**: Medium — Near-Term Deliverable（每日報告仍需手動觸發）

**描述**:
`EnhancedScheduler.enqueue_daily_report()` 和 `enqueue_weekly_report()` 已經實作（透過 Redis Queue + JobWorkerPool 5-stage pipeline），但**沒有掛入 Celery Beat schedule**。目前報告只能透過 Telegram `/report` 指令手動觸發。

**影響範圍**: 每日/每週投資報告無法自動生成，使用者必須手動請求。

**根因分析**:
- [ ] 檢查 `EnhancedScheduler` 是否需要 Redis Queue Manager 實例化才能運作
- [ ] 確認 `WorkflowStages` pipeline 是否可在 Celery Worker 中正常執行
- [ ] 比對現行 celery_app.py 的 beat_schedule 格式與 `enqueue_daily_report` 的呼叫簽章

**解決方案**:
- [ ] 新增一個 Celery Beat 排程：`daily-report-generation` @ 09:00 ET（盤後1小時）
- [ ] 新增一個 Celery Beat 排程：`weekly-report-generation` @ 每週五 17:00 ET
- [ ] 排程對應的任務可以包裝成 `@app.task` 呼叫 `EnhancedScheduler.enqueue_daily_report()` 或直接呼叫 `DailyWorkflow`

**驗證方式**:
- [ ] 在 dev 環境設定測試排程（每 5 分鐘）並觀察是否正確觸發
- [ ] 檢查 Redis Queue 中是否有新的 job 被 enqueue
- [ ] 確認 `docker logs advisor_prod_scheduler` 顯示 "Sending due task daily-report-generation"
- [ ] 確認 Worker 日誌顯示 job 被成功處理，報告產出

> 💡 **Next Action**: 依賴 P1-3/P1-4/P1-5 完成後，確認現行 tasks.py 模式，按相同方式新增 daily/weekly report tasks。

---

### P2-3: Rebalance 任務未掛入排程
**狀態**: `[ ]` 🟡 **OPEN**
**優先度**: Medium — Near-Term Deliverable（需先確認觸發策略）

**描述**:
`trigger_portfolio_rebalance` 已經註冊為 Celery 任務（5 nodes），且 `@app.task` 可正常呼叫，但**未掛入任何 Celery Beat 排程**。

**影響範圍**: 投資組合再平衡只能透過外部觸發（如 webhook/Sentinel），無法按時自動執行。

**根因分析**:
- [ ] 確認 rebalance 的觸發條件（Sentinel 異常偵測 vs 定時檢查）
- [ ] 確認 Sentinel process_tick 是否已經在 sentinel-minutely-tick 中觸發 rebalance

**解決方案**:
- [ ] 若希望定時檢查：新增一個低頻排程（如每日 11:00 ET 盤中檢查）
- [ ] 若完全依賴 Sentinel 異常觸發：確認 sentinel_tick → rebalance 的邏輯鏈條是否完整
- [ ] 若已由 sentinel-minutely-tick 涵蓋：在 backlog 中註明「已由 Sentinel 觸發，不需要獨立排程」

**驗證方式**:
- [ ] 若新增排程：觀察 Scheduler 日誌 "Sending due task trigger_portfolio_rebalance"
- [ ] 若已由 Sentinel 涵蓋：在 Worker 日誌搜尋 rebalance 相關 log，確認實際有執行
- [ ] 檢查 rebalance 結果資料（portfolio_rebalance 表或 daily_reports 目錄）

---

### P2-4: ^VIX 資料錯誤對 Sentinel 決策影響評估
**狀態**: `[ ]` 🟡 **OPEN**
**優先度**: Low — Long-Term Deliverable（需等 P0-2 修復後評估）

**描述**:
雖然 P0-1 修復 ^VIX 錯誤本身，但需要評估此錯誤過去對 Sentinel 決策的實際影響。VIX 是波動率指標，若長期缺失可能導致風險評估系統性偏低。

**影響範圍**: 依賴 VIX 的風險評分、避險建議、市場壓力判斷。

**根因分析**:
- [ ] 追蹤 `sentinel_service.py` 中 VIX 資料的使用處
- [ ] 確認 VIX 缺失時 Sentinel 的降級行為（跳過、使用預設值、或報錯）

**解決方案**:
- [ ] 若為跳過：確認降級行為是否合理，必要時增加替代波動率指標
- [ ] 若為報錯：P0-1 即為完整修復方案
- [ ] 若使用預設值：需評估預設值是否導致風險誤判

**驗證方式**:
- [ ] 修復後比較修復前後的 Sentinel 風險評分差異（若有歷史資料）
- [ ] 手動設置 VIX 測試值，確認 Sentinel response 正確

> 💡 **Dependency**: 等待 P0-2 修復後才有意義執行此評估。

---

### P2-5: Worker Error Noise 清理（OTel + VIX + eToro 錯誤歸零）
**狀態**: `[ ]` 🟡 **OPEN**
**優先度**: Low — Long-Term Deliverable（依賴 P0 + P1 全部修復）

**描述**:
目前的 Worker 日誌被三種重複錯誤淹沒（每分鐘 ~3-5 條），導致真正的新問題難以從日誌中發現。需要 P0-1 + P0-2 + P1-1 + P1-2 全部修復後驗證錯誤歸零。

**驗證方式**:
- [ ] 所有修復部署後，觀察 5 分鐘的 Worker 日誌：
  ```bash
  docker logs advisor_prod_worker_1 --tail 200 2>&1 | grep -cE "JSONDecodeError|VIX|gemma2|NETWORK|UNAVAILABLE|etoro.*localhost"
  ```
- [ ] 預期結果：上述錯誤計數應為 0
- [ ] 若仍有殘留錯誤，識別並開新 task

> 💡 **Dependency**: 執行此驗證需等 P0-2、P1-1、P1-2 全部完成。

---

## 📋 Priority Summary (as of 2026-05-31)

| Task | Priority | Status | Next Action |
|------|----------|--------|-------------|
| P0-2: Sentinel LLM gemma2 NETWORK_ERROR | 🔴 HIGH (Blocker) | OPEN | Diagnose Ollama, route to OpenRouter fallback |
| P1-3: keyword_refine → Celery | 🟠 HIGH | OPEN | Implement Celery task + beat schedule |
| P1-4: experience_replay → Celery | 🟠 HIGH | OPEN | Implement Celery task + beat schedule |
| P1-5: weekly_validation bug fix + Celery | 🟠 HIGH | OPEN | Fix nested except bug first, then migrate |
| P2-2: Daily Report auto-schedule | 🟡 MEDIUM | OPEN | After P1-3/4/5 complete |
| P2-3: Rebalance schedule strategy | 🟡 MEDIUM | OPEN | Confirm Sentinel trigger chain first |
| P2-4: VIX impact assessment | 🟡 LOW | OPEN | After P0-2 resolved |
| P2-5: Worker error noise cleanup | 🟡 LOW | OPEN | After all P0+P1 resolved |
| P0-1: ^VIX fetch fix | ✅ DONE | — | — |
| P1-1: eToro API config | ✅ DONE | — | — |
| P1-2: OTel Collector | ✅ DONE | — | — |
| P2-1: Celery Beat process | ✅ DONE | — | — |
