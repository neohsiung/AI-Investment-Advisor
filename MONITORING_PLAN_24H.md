# 🎯 24 小時生產監控計畫

**部署時間**: 2026-04-13 20:31 UTC  
**監控週期**: 24 小時（2026-04-13 至 2026-04-14）  
**負責人**: Neo  
**狀態**: 🟢 ACTIVE

---

## 📊 監控架構概圖

```
┌─────────────────────────────────────────────────────────────┐
│              Production Environment (prd)                    │
├──────────┬──────────┬──────────┬──────────┬──────────────────┤
│ Frontend │   API    │Scheduler │ n8n      │   Database       │
│(Next.js) │ (MCP)    │(Async)   │(Webhook) │  (PostgreSQL)    │
│ :3000   │  :8000   │ bg task  │  :5678   │   + Redis        │
└──────────┴──────────┴──────────┴──────────┴──────────────────┘
     │           │           │           │           │
     └───────────┴───────────┴───────────┴───────────┘
                         │
                 ┌───────▼─────────┐
                 │ SigNoz APM      │
                 │ :8080 (Tracing) │
                 └─────────────────┘
                         │
                 ┌───────▼─────────┐
                 │ Telegram Alerts │
                 │ (Neo's channel) │
                 └─────────────────┘
```

---

## 1️⃣ 核心指標監控清單

### A. 前端 (Frontend - Next.js :3000)

| 指標 | 目標 | 檢查方法 | 告警閾值 |
|-----|------|---------|--------|
| HTTP 可用性 | ✅ 200 OK | `curl http://localhost:3000` | > 2 次連續失敗 |
| NLV 數值 | $1,105.33 ± $5 | 訪問儀表板 | 偏差 > $10 |
| P&L 數值 | $314.64 ± $2 | 訪問儀表板 | 偏差 > $5 |
| 頁面載入時間 | < 3 秒 | DevTools / 瀏覽器控制台 | > 5 秒 |
| 靜態資產快取 | Gzip 壓縮 | Network 選項卡 | Uncompressed > 100KB |

### B. API (MCP Server :8000)

| 指標 | 目標 | 檢查方法 | 告警閾值 |
|-----|------|---------|--------|
| HTTP 健康檢查 | ✅ 200 OK | `curl http://localhost:8000/health` | > 2 次失敗 |
| MCP 服務狀態 | ✅ 已初始化 | Docker 日誌 | ERROR 級別日誌 |
| 數據庫連接 | ✅ 健康 | SQLAlchemy ORM 連接池 | 連接超時 |
| FRED 服務 | ✅ 已連接 | 日誌中的 "FRED client initialized" | 缺失初始化消息 |
| Tavily 搜索 | ✅ 已初始化 | 日誌中的 "Tavily Search initialized" | 缺失初始化消息 |
| Polygon WebSocket | ✅ 已訂閱 9 個代碼 | 日誌確認訂閱列表 | 訂閱失敗或<9個 |
| Sentinel VIX 校準 | ✅ 已完成 | 日誌顯示 VIX 閾值 | 校準失敗 |

### C. 調度器 (Scheduler - async tasks)

| 指標 | 目標 | 檢查方法 | 告警閾值 |
|-----|------|---------|--------|
| 容器運行狀態 | ✅ Running | `docker ps \| grep scheduler` | 容器停止 |
| 任務初始化 | ✅ 已初始化 | 日誌檢查用戶數 | 初始化錯誤 |
| 排程配置 | ✅ 已載入 | 日誌顯示 Daily=20:00 | 配置加載失敗 |
| 4 小時間隔穩定性 | ✅ 無 TypeError | 實時監控 24 小時 | 任何崩潰或掛起 |
| eToro 同步頻率 | ✅ 按時執行 | 檢查時間戳和頻率 | 同步遲到 > 5 分鐘 |

### D. n8n Webhook (自動化引擎 :5678)

| 指標 | 目標 | 檢查方法 | 告警閾值 |
|-----|------|---------|--------|
| n8n 容器狀態 | ✅ Running | `docker ps \| grep n8n` | 容器停止 |
| Webhook 可達性 | ✅ 回應 | `curl http://localhost:5678/webhook/*` | HTTP 錯誤 |
| RSS 流處理 | ✅ 每 15 分鐘 1 次 | n8n UI 監控執行歷史 | 執行失敗 |
| 技能學習觸發 | ✅ 每日 07:00 | 檢查執行日誌 | 錯過執行 |
| Podcast 檢查 | ✅ 每 4 小時 1 次 | 檢查執行日誌 | 執行失敗 |
| 決策策略觸發 | ✅ 正常運行 | n8n 儀表板中的決策流 | 任何錯誤 |
| API 密鑰驗證 | ✅ X-API-Key 有效 | 檢查 n8n 配置 | 401 Unauthorized |

### E. 數據庫 (PostgreSQL + Redis)

| 指標 | 目標 | 檢查方法 | 告警閾值 |
|-----|------|---------|--------|
| PostgreSQL 連接 | ✅ 健康 | `docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT 1"` | 連接失敗 |
| 表行數穩定性 | ✅ 無異常增長 | `SELECT COUNT(*) FROM transactions;` | 24 小時增長 > 50% |
| `current_billing_cycle_start` 列 | ✅ 存在 | `SELECT current_billing_cycle_start FROM users LIMIT 1;` | 列遺失 |
| Redis 緩存命中率 | ✅ > 80% | SigNoz 指標或 Redis CLI | < 60% |
| 慢查詢 | ✅ < 100ms 中位數 | PostgreSQL logs / SigNoz | 任何 > 1s 的查詢 |

### F. Telegram 集成

| 指標 | 目標 | 檢查方法 | 告警閾值 |
|-----|------|---------|--------|
| 頻道連接 | ✅ 已連接 | 在 Neo 的 channel 查看 | 無法發送消息 |
| 告警消息投遞 | ✅ 即時 | 檢查消息時間戳 | > 5 秒延遲 |
| 交易通知 | ✅ 發送成功 | channel 中的交易紀錄 | 沉默 > 24 小時 |

---

## 2️⃣ 監控檢查清單（每 4 小時）

### ⏰ 第 1 檢查點：T+0 (20:31 UTC)
```bash
✅ 部署完成
✅ 所有容器運行中
✅ API 健康檢查通過
✅ 調度器已初始化
✅ n8n 正常
✅ NLV: $1,105.33
✅ P&L: $314.64
```

### ⏰ 第 2 檢查點：T+4 (00:31 UTC)
- [ ] 前端：測試首頁加載
- [ ] API：驗證 `/health` 端點
- [ ] 調度器：檢查是否有計劃任務執行（預計無）
- [ ] n8n：確認 RSS 流是否執行（每 15 分鐘一次）
- [ ] DB：檢查連接和行數穩定性
- [ ] 數據漂移：NLV 變化 < $5
- [ ] 錯誤日誌：查看 ERROR / CRITICAL 級別

### ⏰ 第 3 檢查點：T+8 (04:31 UTC)
- [ ] 重複第 2 檢查點
- [ ] **技能學習**：檢查 07:00 觸發是否開始（預計 2.5 小時內執行）
- [ ] Telegram：檢查是否收到任何告警

### ⏰ 第 4 檢查點：T+12 (08:31 UTC)
- [ ] **技能學習**：驗證 07:00 執行完成 ✅
- [ ] 重複核心檢查
- [ ] **Podcast RSS**：檢查 4 小時觸發執行情況

### ⏰ 第 5 檢查點：T+16 (12:31 UTC)
- [ ] 重複第 2 檢查點
- [ ] **eToro 同步**：檢查 20:00 是否已觸發（預計今日 20:00 执行）

### ⏰ 第 6 檢查點：T+20 (16:31 UTC)
- [ ] 重複第 2 檢查點

### ⏰ 第 7 檢查點：T+24 (20:31 UTC - 最終檢查)
- [ ] **eToro 同步驗證**：確認 20:00 任務已執行
- [ ] **24 小時穩定性報告**：零崩潰、零數據漂移
- [ ] **總體評分**

---

## 3️⃣ 檢查腳本

### 🔴 快速健康檢查 (2 分鐘)
```bash
#!/bin/bash

echo "🚀 Production Health Check - $(date)"
echo "=================================="

# Frontend
echo "📱 Frontend..."
curl -s http://localhost:3000 > /dev/null && echo "  ✅ Available" || echo "  ❌ FAILED"

# API
echo "🛡️  API..."
curl -s http://localhost:8000/health > /dev/null && echo "  ✅ Healthy" || echo "  ❌ FAILED"

# Database
echo "🗄️  Database..."
docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT 1" > /dev/null 2>&1 && echo "  ✅ Connected" || echo "  ❌ FAILED"

# Containers
echo "🐳 Containers..."
docker ps | grep -q "advisor_prod_api" && echo "  ✅ API running" || echo "  ❌ API down"
docker ps | grep -q "advisor_prod_scheduler" && echo "  ✅ Scheduler running" || echo "  ❌ Scheduler down"
docker ps | grep -q "advisor_prod_n8n" && echo "  ✅ n8n running" || echo "  ❌ n8n down"
docker ps | grep -q "advisor_prod_ui" && echo "  ✅ Frontend running" || echo "  ❌ Frontend down"

# NLV/P&L
echo "💰 Portfolio Data..."
curl -s http://localhost:8000/api/portfolio/summary | jq '.nlv, .pnl' 2>/dev/null || echo "  ❌ API call failed"

echo "=================================="
```

### 🔴 深度監控檢查 (10 分鐘)
```bash
#!/bin/bash

echo "🔍 Deep Monitoring Check - $(date)"

# 1. API Logs (last 50 lines, errors only)
echo "📋 API Errors:"
docker logs advisor_prod_api 2>&1 | grep -i "error\|failed\|exception" | tail -10

# 2. Scheduler Logs
echo "📋 Scheduler Status:"
docker logs advisor_prod_scheduler 2>&1 | tail -5

# 3. n8n Execution History
echo "📋 n8n Recent Executions:"
curl -s http://localhost:5678/rest/executions?limit=5 2>/dev/null | jq '.[] | {id, status, startedAt}' || echo "  ❌ n8n unreachable"

# 4. SigNoz Trace Status
echo "📋 SigNoz Tracing:"
curl -s http://localhost:8080/api/v1/health 2>/dev/null | jq '.status' && echo "  ✅ Tracing active" || echo "  ❌ Tracing down"

# 5. Database Connection Pool
echo "📋 DB Connections:"
docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT count(*) as total_connections FROM pg_stat_activity;" 2>/dev/null || echo "  ❌ DB error"

# 6. Redis Cache Stats
echo "📋 Redis Stats:"
docker exec advisor_prod_cache redis-cli INFO stats 2>/dev/null | grep -E "total_commands_processed|connected_clients" || echo "  ❌ Redis unreachable"

echo "=================================="
```

---

## 4️⃣ 故障排除決策樹

```
┌─ 前端無法訪問
│  ├─ 檢查 Docker：docker ps | grep frontend
│  ├─ 檢查端口：lsof -i :3000
│  ├─ 檢查日誌：docker logs advisor_prod_ui
│  └─ 重啟：docker compose -f docker-compose.prod.yml restart ui

├─ API 返回 500
│  ├─ 檢查 DB：docker exec advisor_prod_db psql ...
│  ├─ 檢查連接：curl http://localhost:8000/health
│  ├─ 查看日誌：docker logs advisor_prod_api | grep ERROR
│  └─ 重啟：docker compose -f docker-compose.prod.yml restart mcp_server

├─ 調度器崩潰
│  ├─ 檢查進程：docker ps | grep scheduler
│  ├─ 查看錯誤：docker logs advisor_prod_scheduler | tail -50
│  ├─ 檢查配置：curl http://localhost:8000/api/scheduler/config
│  └─ Issue #5 回滾：git log | grep "Issue #5"

├─ n8n Webhook 失敗
│  ├─ 檢查容器：docker ps | grep n8n
│  ├─ 檢查日誌：docker logs advisor_prod_n8n
│  ├─ 測試連接：curl -X POST http://localhost:5678/webhook/test
│  └─ 檢查 API Key：查看 n8n_workflow_template.json

├─ NLV/P&L 數據漂移
│  ├─ 查詢 DB：SELECT * FROM portfolios WHERE user_id = '...';
│  ├─ 檢查 eToro 同步：查看調度器日誌中的 job_etoro_sync
│  ├─ 驗證來源：使用 eToro 官方 API
│  └─ 回滾修復：git reset --hard HEAD~1（如需要）

└─ 數據庫行數異常增長
   ├─ 查詢表行數：SELECT COUNT(*) FROM transactions;
   ├─ 檢查最新記錄：SELECT * FROM transactions ORDER BY created_at DESC LIMIT 10;
   ├─ 查找重複：SELECT ticker, COUNT(*) FROM transactions GROUP BY ticker HAVING COUNT(*) > 100;
   └─ 清理策略：備份後刪除舊記錄
```

---

## 5️⃣ 告警規則 (Telegram 發送)

```json
{
  "alerts": [
    {
      "name": "Frontend Down",
      "condition": "curl http://localhost:3000 fails > 2 times",
      "severity": "CRITICAL",
      "telegram_group": "@Neo_Investment_Alerts"
    },
    {
      "name": "API Error Rate > 5%",
      "condition": "SigNoz error rate spike",
      "severity": "HIGH",
      "telegram_group": "@Neo_Investment_Alerts"
    },
    {
      "name": "Scheduler Crash",
      "condition": "docker ps shows no scheduler",
      "severity": "CRITICAL",
      "telegram_group": "@Neo_Investment_Alerts"
    },
    {
      "name": "NLV Drift > $10",
      "condition": "$1,105.33 ± $10 threshold",
      "severity": "HIGH",
      "telegram_group": "@Neo_Investment_Alerts"
    },
    {
      "name": "n8n Webhook Failure",
      "condition": "HTTP 5xx or timeout",
      "severity": "HIGH",
      "telegram_group": "@Neo_Investment_Alerts"
    },
    {
      "name": "Database Connection Failed",
      "condition": "psql connection refused",
      "severity": "CRITICAL",
      "telegram_group": "@Neo_Investment_Alerts"
    }
  ]
}
```

---

## 6️⃣ 24 小時監控日誌

| 時間 | 組件 | 狀態 | 備註 |
|------|-----|------|------|
| T+0 | 全部 | ✅ | 部署完成 |
| T+4 | | | |
| T+8 | | | |
| T+12 | | | |
| T+16 | | | |
| T+20 | | | |
| T+24 | 全部 | ✅ | 最終驗收 |

---

## 7️⃣ 專案流程約束（規則文件）

根據 `.agent/rules/` 中的規範：

### ✅ 工程標準 (engineering-standards.md)
- **Python**: 3.10+（已滿足 3.11）
- **代碼風格**: Google Python + 英中雙語註解
- **混合儲存**: ORM for Admin, Raw SQL for Performance
- **安全**: SHA256 for IDs, 嚴禁 MD5/SHA1
- **憑證管理**: 通過 `SettingsService` 讀取，嚴禁硬編碼

### ✅ 觀測標準 (observability-standards.md)
- **OTel**: 所有微服務必須透過 OpenTelemetry 打點
- **結構化日誌**: `python-json-logger` 格式
- **監控自託管**: SigNoz (http://localhost:8080)
- **通知匯流排**: 禁止各服務直接調用 SMTP/LINE，必須通過 Notification Microservice
- **服務解耦**: 所有外部 API 調用需非同步防呆

### ✅ 文檔標準 (documentation-standards.md)
- 所有 API 端點須文檔化
- 部署變更須記錄在 CHANGELOG.md

### ✅ n8n Webhook 流程（根據 n8n_workflow_template.json）
1. **15 分鐘 RSS 流**: 抓取新聞，分析，發送到 API
2. **每日 07:00 技能學習**: 觸發 Readwise 集成
3. **每 4 小時 Podcast RSS**: 檢查新的 Podcast 更新
4. **決策策略工作流**: n8n → API → 買賣信號 → Telegram

---

## 📞 應急聯絡

| 角色 | 聯絡方式 | 可用時間 |
|------|--------|--------|
| Neo (首級) | Telegram @neohsiung | 24/7 |
| Backup | GitHub Issues #EMERGENCY | 非即時 |

---

## 🎯 成功定義

**24 小時監控成功 = 以下所有條件滿足**

1. ✅ **零崩潰**: 所有容器連續運行
2. ✅ **零數據漂移**: NLV ± $5, P&L ± $2
3. ✅ **排程正常**: 所有計劃任務按時執行
4. ✅ **API 可用性**: > 99.5%（允許 1 次 < 30 秒 中斷）
5. ✅ **n8n 工作流**: 所有 webhook 無失敗
6. ✅ **Telegram 集成**: 告警消息即時投遞
7. ✅ **無 SQL 錯誤**: 無 "UndefinedColumn" 或 "ProgrammingError"
8. ✅ **性能穩定**: 平均響應時間 < 500ms

---

**最後更新**: 2026-04-13 20:35 UTC  
**下次檢查**: 2026-04-14 00:31 UTC
