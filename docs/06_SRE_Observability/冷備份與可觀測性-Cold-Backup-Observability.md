# 冷備份與可觀測性 (Cold Backup & Observability)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-10-23 | v9.0 | **新增 §3 夜間資料庫備份**：腳本驗證產物、狀態檔、自我維運告警與還原演練（PR #225、#226、#228） | Claude |
| 2026-08-23 | v8.0 | **新增 §2.1 n8n workflow 備份與 `SKIP_N8N_IMPORT`**：每次 cold start 都在 UPSERT 覆寫並停用 workflow，而 n8n 是全系統唯一零備份覆蓋的元件。 | Claude Opus 5 |
| 2026-07-19 | v7.0 | 新增冷備份與可觀測性說明文件 (Added Cold Backup & Observability doc) | Antigravity |

---

## 🇹🇼 繁體中文

### 1. 系統概觀
為了配合本地自運行 (Local self-hosted) 的特點並落實嚴格的預算治理，系統實作了本地日誌冷備份機制，並深化了基於 OpenTelemetry 與 SigNoz 的系統可觀測性架構。

### 2. 冷處理備份 (Cold Processing Backup)
- **機制設計**：由於系統運行於本地環境，日誌與鏈上軌跡如果全數傳輸至雲端 APM 會產生過多流量。因此，系統將關鍵的決策結果（session_id, topic, consensus, grounding_note, timestamp）同步寫入本地的冷備份檔案 `logs/workflow_cold_backup.jsonl`。
- **非阻塞寫入**：寫入邏輯由 `asyncio.get_event_loop().run_in_executor()` 託管，確保磁碟 I/O 不會阻塞主要的 AI 分析管線與交易流程。
- **備份保留**：本機備份主要用於在發生資料庫損壞或 APM 連線中斷時進行系統復盤。

### 2.1 n8n Workflow 備份與 `SKIP_N8N_IMPORT` (2026-08-20)

> [!CAUTION]
> **每一次 cold start 都在無聲摧毀 n8n 的狀態。**
> `n8n_workflow_template.json` 帶有頂層 `"id": "1"`，所以 `n8n import:workflow` 是對
> workflow 1 的 **UPSERT** —— 你在 n8n UI 上調的任何東西都會被覆寫。
> n8n 2.x 更糟：`--activeState` 預設 `false`，所以匯入還會順手把 workflow **停用**。

而 n8n 是全系統**唯一零備份覆蓋**的元件：它的資料全在 `advisor_n8n_data` volume
（自帶 SQLite 與自動產生的加密金鑰），`scripts/backup_db.sh` 只 `pg_dump` PostgreSQL。
手工調過的 workflow 一旦被覆寫就救不回來。

現行防護（皆在 `start.sh`）：

| 機制 | 行為 |
| :--- | :--- |
| **匯入前自動備份** | `backup_n8n_workflow()` 先 `n8n export:workflow --id=1` 到 `backups/n8n_workflow_1_<timestamp>.json`。**備份失敗則中止匯入**，現有 workflow 原封不動 |
| **`--activeState=fromJson`** | 依模板的 `"active": true` 決定啟用狀態，不再被 2.x 的預設值停用；1.x 沒有這個參數，故保留 fallback |
| **`SKIP_N8N_IMPORT`** | 完全跳過匯入。`SKIP_N8N_IMPORT=1 ./start.sh prod`，或寫進 `.env` |

```bash
# 手動調過 workflow、不希望被模板覆蓋時：
SKIP_N8N_IMPORT=1 ./start.sh prod
```

> 中止匯入時腳本回傳 0 而非 1 —— `start.sh` 跑在 `set -e` 下，而這個函式是在叢集已經
> 起來之後才被 `deploy_prod` 呼叫，回非零會把整個部署炸掉。橫幅訊息才是訊號。

---

### 3. OpenTelemetry 與 SigNoz 整合
- **分佈式追蹤 (Distributed Tracing)**：系統各關鍵模組（`SentinelService`、`CouncilService`、`DAGExecutor`）皆部署了 OTel Tracer。
- **DAG Telemetry 打點**：
  - `BaseNode` 自動收集節點延遲 (`latency`)、快取狀態 (`cache_hit`)、執行狀態。
  - 當節點命中快取時，`WorkflowCache` 會根據該節點對應的 model tier，自動計算本次命中為用戶「節省的 LLM 費用 (saved_cost_usd)」並累計至指標中。
- **SigNoz Dashboard**：
  - 開發人員可透過 SigNoz 面板實時監控系統的 API 呼叫、SQL 慢查詢、以及各 LLM Provider (OpenRouter/Ollama) 的請求成功率與 Token 消耗。

---

## 🇺🇸 English

### 1. System Overview
To match the requirements of self-hosted local execution and ensure strict cost governance, the system implements a local cold backup mechanism alongside structured OpenTelemetry (OTel) and SigNoz observability.

### 2. Cold Processing Backup
- **Mechanism**: Running in a local environment, uploading raw execution logs or agent chains to cloud APM can be bandwidth-heavy. The system serializes critical outcomes (session_id, topic, consensus, grounding_note, timestamp) into a local JSON Lines file: `logs/workflow_cold_backup.jsonl`.
- **Non-blocking Writes**: Logging execution is offloaded via `asyncio.get_event_loop().run_in_executor()` to prevent slow disk I/O from blocking active AI decision loops.
- **Data Recovery**: This cold storage log serves as a secure fallback to restore context or perform diagnostic replays if local databases become corrupted or APM links disconnect.

### 3. OpenTelemetry & SigNoz APM Integration
- **Distributed Tracing**: Spans are defined across `SentinelService`, `CouncilService`, and `DAGExecutor` to visualize component latency.
- **DAG Telemetry**:
  - `BaseNode` automatically records node-level latency, cache hit/miss status, and execution metadata.
  - On a cache hit, `WorkflowCache` determines the corresponding model tier and increments `saved_cost_usd` tracking metrics in real-time.
- **SigNoz Dashboards**:
  - Developers can view metrics on API requests, SQLAlchemy database query times, and LLM providers' success rates and token consumption.

---

## 3. 夜間資料庫備份 (Nightly Database Backup, 2026-10-23)

<!-- TW -->
**事故**：`backups/` 的 30 份夜間備份有 29 份是零位元組。cron 的 PATH 很短，找不到 `docker`，腳本只把「找不到指令」寫進沒人讀的日誌；crontab 也指向舊的專案路徑。

**現行機制（`scripts/backup_db.sh`）**
- 自設 `PATH`，不用 `docker exec -t`（cron 沒有 TTY）。
- 先寫 `.partial` 暫存檔，**非空且結尾有 `PostgreSQL database dump complete`** 才改名為正式備份；失敗刪暫存檔、`exit 1`、寫 `backups/BACKUP_FAILED`。
- 每次寫 `config/.backup_status.json`（worker 掛載 `./config` 但看不到 `./backups`，所以狀態放這裡；已 gitignore）。
- 保留 `BACKUP_KEEP_DAYS`（預設 14）天；清掉零位元組殘留。

**誰會發現失敗**
- 自我維運每 15 分鐘檢查 `nightly_backup_fresh`（`src/services/backup_status.py`）：失敗或超過 36 小時沒更新為 `critical`（直接通知，6 小時冷卻再提醒）；狀態檔不存在或壞掉為 `warning`（未知，不當成正常）。
- 週報（章程週報-Charter-Weekly-Digest）的「夜間備份」段。

**還原演練（2026-10-23 實跑）**：用最新夜間備份（約 320 MB）在拋棄式 `pgvector/pgvector:pg16` 容器還原，9 秒完成零錯誤；69 張表、158 個索引、alembic 版本一致，逐表筆數只差備份後 6 小時新增的資料。連續 3 次 `pg_dump` 輸出一致。

```bash
docker run -d --name restore_drill -e POSTGRES_PASSWORD=x pgvector/pgvector:pg16
docker exec restore_drill psql -U postgres -c 'create database advisor_prod'
docker exec -i restore_drill psql -U postgres -d advisor_prod -q < backups/db_backup_<日期>.sql
docker rm -f restore_drill   # 演練完刪除，不要留著
```

**已知異常**：2026-10-22 部署前備份期間，PostgreSQL 的一個連線程序 4 次無預警結束（exit code 2，無 PANIC，WAL 重放乾淨，復原時同步資料目錄慢了 30 秒以上）。無法在拋棄式副本重現，也沒有資料損毀證據；推測是 Docker 在 Mac 上磁碟 I/O 暫時卡住，但這只是推測。再發生時先查 Docker Desktop 的磁碟與記憶體。

<!-- EN -->
**Incident**: 29 of the 30 nightly dumps in `backups/` were zero bytes (cron's short PATH lacked `docker`; the failure went to a log nobody read; the crontab pointed at an old checkout).

**Now**: `scripts/backup_db.sh` sets its own PATH, writes a `.partial` file, keeps it only if non-empty and ending with the pg_dump completion trailer (else exit 1 and `backups/BACKUP_FAILED`), and writes `config/.backup_status.json` (the worker mounts `./config`, not `./backups`). Self-ops check `nightly_backup_fresh` alerts `critical` on a failed or >36h-old backup and `warning` when the status is unknown; the weekly digest shows it too.

**Restore drill (run 2026-10-23)**: the latest nightly dump restored into a throwaway pgvector container in 9 s with zero errors; 69 tables, 158 indexes and the alembic version matched, row counts differing only by data written after the backup. **Known anomaly**: four unexplained backend exits (code 2) during the 2026-10-22 pre-deploy dump; not reproduced, no corruption evidence.
