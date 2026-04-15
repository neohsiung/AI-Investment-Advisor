# 📊 生產監控摘要 — 2026-04-13

**部署時間**: 20:31 UTC  
**檢查時間**: 21:11 UTC (T+40 分鐘)  
**狀態**: ✅ 穩定運行中

---

## 🎯 快速檢查結果

```
✅ 前端 UI                   — HTTP 200，可訪問
✅ API 健康檢查              — HTTP 200，正常
✅ PostgreSQL 數據庫         — 連接成功
✅ Redis 緩存                — 運行中
✅ API 容器 (MCP)            — Running
✅ 調度器容器                — Running
✅ n8n 自動化引擎            — Running
✅ 前端容器 (Next.js)        — Running
❌ Portfolio API 端點        — 需驗證（可能端點路由不同）
```

---

## 📈 深度檢查項目

### 1. API 錯誤日誌
```bash
$ docker logs advisor_prod_api 2>&1 | grep -i "error" | wc -l
# 預期: < 10 個 ERROR（正常噪聲水平）
```

### 2. 調度器狀態
```bash
$ docker logs advisor_prod_scheduler 2>&1 | tail -10
# 預期：「Multi-tenant scheduler loop started」無崩潰
```

### 3. n8n Webhook 歷史
```bash
$ curl -s http://localhost:5678/rest/executions?limit=5
# 預期：最近 5 個執行正常完成
```

### 4. 數據庫連接
```bash
$ docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT COUNT(*) FROM pg_stat_activity;"
# 預期: 5-15 個活躍連接（正常）
```

### 5. Redis 統計
```bash
$ docker exec advisor_prod_cache redis-cli INFO stats
# 預期: total_commands_processed > 1000, connected_clients >= 2
```

### 6. 交易記錄數
```bash
$ docker exec advisor_prod_db psql -U postgres -d portfolio -c "SELECT COUNT(*) FROM transactions;"
# 預期: 穩定（無異常增長）
```

### 7. Billing Column 驗證
```bash
$ docker exec advisor_prod_db psql -U postgres -d portfolio \
  -c "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='current_billing_cycle_start');"
# 預期: t（true）— 列已存在
```

---

## 📋 Telegram 集成檢查清單

### ✅ 需驗證項目

- [ ] Neo 可以在 Telegram channel 中接收消息
- [ ] 交易信號正常投遞（如有交易）
- [ ] 告警消息格式清晰，時間戳準確
- [ ] 無高頻重複告警
- [ ] API 錯誤能被正確報告到 channel

### 📌 集成端點

```
Telegram Bot Token: (已配置)
Channel ID: @Neo_Investment_Alerts (或相應頻道)
Message Format:
  🔔 [Event Type]
  時間: 2026-04-13 21:11 UTC
  詳情: ...
  狀態: ✅/⚠️/❌
```

---

## 🔔 n8n Webhook 流程驗證

### 1️⃣ RSS 新聞流 (每 15 分鐘)
- **觸發時間**: 每小時的 :00, :15, :30, :45
- **預期結果**: 獲取新聞，分析相關性，發送到 API
- **檢查方法**: `docker logs advisor_prod_n8n | grep "Fetch RSS"`

### 2️⃣ 技能學習 (每日 07:00)
- **下次執行**: 2026-04-14 07:00 UTC
- **預期結果**: 觸發 Readwise 集成
- **檢查方法**: n8n Dashboard → Executions

### 3️⃣ Podcast RSS (每 4 小時)
- **執行時間**: :00, :04, :08, :12, :16, :20 (小時)
- **預期結果**: 檢查 Podcast 更新
- **檢查方法**: n8n 執行歷史

### 4️⃣ 決策策略工作流
- **觸發條件**: API 信號或定時
- **預期結果**: 買/賣信號 → Telegram 通知
- **檢查方法**: Telegram channel 消息歷史

---

## 💾 數據完整性驗證

### 關鍵數據點

| 數據 | 預期值 | 當前值 | 狀態 |
|-----|--------|--------|------|
| NLV | $1,105.33 ± $5 | 待驗證 | ⏳ |
| P&L | $314.64 ± $2 | 待驗證 | ⏳ |
| 交易記錄數 | 穩定，無異常增長 | 待驗證 | ⏳ |
| current_billing_cycle_start | 存在 | ✅ true | ✅ |

---

## 🛠️ 已採取的行動

1. ✅ **Issue #6 修復**: 添加 `current_billing_cycle_start` 列到 users 表
2. ✅ **API 容器重啟**: 解決 Schema 錯誤，恢復健康狀態
3. ✅ **n8n 監控**: 驗證容器運行中，Webhook 端點可達
4. ✅ **調度器驗證**: 確認多租戶排程器已初始化

---

## ⚠️ 已知限制

- **Portfolio API 端點**: 需確認正確的 URL 路由（可能不是 `/api/portfolio`）
- **OTel 連接**: 遠端服務（PostHog、Rudder）因網路不可用，但本地 SigNoz 正常
- **Telegram Bot**: 需手動驗證頻道連接和消息投遞

---

## 🎯 下一步（T+4 小時 = 00:31 UTC）

```markdown
- [ ] 運行深度檢查腳本：bash scripts/health_check_deep.sh
- [ ] 驗證 Telegram 消息接收
- [ ] 查詢 Portfolio NLV/P&L 數值
- [ ] 檢查 RSS 流是否執行（預計 2-3 次）
- [ ] 驗證調度器無崩潰
- [ ] 檢查 SigNoz 追蹤儀表板
- [ ] 記錄所有指標到監控日誌
```

---

**生成時間**: 2026-04-13 21:11 UTC  
**下一更新**: 2026-04-14 00:31 UTC
