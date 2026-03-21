# 投資技能學習系統 — 設定指南

> Step-by-step 指引：從環境變數設定到 n8n 串接 Podcast RSS 與 Readwise。

---

## Step 1：取得外部 API Keys

### 1.1 Readwise Access Token

1. 登入 [Readwise](https://readwise.io)
2. 前往 **https://readwise.io/access_token**
3. 複製 Access Token

### 1.2 Groq API Key（Podcast 語音轉譯）

1. 註冊 [Groq Console](https://console.groq.com)
2. 前往 **API Keys** → Create API Key
3. 複製 Key

> [!TIP]
> Groq Whisper 免費層提供每日一定額度，足以處理 1-3 集 Podcast。超出限制會回傳 429。

### 1.3 投資顧問系統 API Key

你的 `X-API-Key`，用於驗證 n8n → 系統 webhook 的請求。  
可在 `.env` 的 `API_KEY` 欄位查看。

---

## Step 2：設定環境變數

編輯 `.env` 檔案，新增以下欄位：

```bash
# Investment Skill Learning System
READWISE_TOKEN=<Step 1.1 的 Token>
GROQ_API_KEY=<Step 1.2 的 Key>
```

若使用 Docker Compose，確認 `docker-compose.yml` 中 `mcp_server` 服務的 `env_file` 已包含 `.env`。

重啟服務：

```bash
docker compose restart investment_advisor_mcp
```

---

## Step 3：驗證 Readwise 連線

```bash
# 手動觸發一次 Readwise 學習
curl -X POST http://localhost:8000/webhook/skill-learning \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <你的 API_KEY>" \
  -d '{"source_type": "highlight"}'
```

**預期回應**：

```json
{"status": "accepted", "user_id": "...", "source": "skill-learning", "workflow": "skill_learning"}
```

**檢查 logs**：

```bash
docker compose logs -f investment_advisor_mcp 2>&1 | grep -i "skill"
```

---

## Step 4：設定 n8n Podcast RSS 來源

### 4.1 開啟 n8n 編輯器

前往 **http://localhost:5678**，找到 workflow：  
**Investment Advisor - RSS Alert Bridge (v4 - Skill Learning)**

### 4.2 編輯「Podcast Feed List」節點

1. 雙擊 **Podcast Feed List** 節點
2. 在 Code 區塊中取消註解你想追蹤的 Podcast：

```javascript
const PODCAST_FEEDS = [
  { name: 'All-In Podcast',        url: 'https://feeds.megaphone.fm/all-in' },
  { name: 'Invest Like the Best',  url: 'https://feeds.simplecast.com/JGE3yC0V' },
  // 自行新增更多...
];
```

3. 按 **Save** 儲存

### 4.3 設定 GROQ_API_KEY 環境變數

n8n 中的 `Groq Whisper Transcribe` 節點使用 `{{ $env.GROQ_API_KEY }}`。請確認：

1. 在 `docker-compose.yml` 的 `n8n` 服務中加入：
   ```yaml
   environment:
     - GROQ_API_KEY=${GROQ_API_KEY}
   ```
2. 或在 n8n UI 中設定：**Settings → Variables → Add Variable**
   - Name: `GROQ_API_KEY`
   - Value: `<你的 Groq Key>`

### 4.4 替換 API Key

在 n8n 中所有含 `your_api_key_here` 的節點，替換為你的實際 `X-API-Key`：

- **Trigger Skill Learning**
- **Send Transcript to Skill Learning**
- **Fetch RSS Sources**
- **Send to Advisor**

### 4.5 啟用 Workflow

確認 Workflow 右上角的 **Active** 開關已開啟。

---

## Step 5：驗證 Podcast 流程

### 5.1 手動測試

在 n8n 編輯器中：

1. 選取 **Podcast RSS Trigger** 節點
2. 點擊 **Test workflow**
3. 觀察每個節點依序亮燈：  
   `Podcast Feed List` → `Fetch Podcast Feed` → `Extract Latest Episode` → `Download Audio` → `Groq Whisper Transcribe` → `Send Transcript to Skill Learning`

### 5.2 用 curl 直接送 Podcast 逐字稿

```bash
curl -X POST http://localhost:8000/webhook/skill-learning \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <你的 API_KEY>" \
  -d '{
    "source_type": "podcast",
    "transcript": "在今天的節目中我們討論了動能投資的進場時機...",
    "source_url": "https://podcast.example.com/ep42",
    "source_name": "投資大師"
  }'
```

---

## Step 6：手動送文章（選用）

```bash
curl -X POST http://localhost:8000/webhook/skill-learning \
  -H "Content-Type: application/json" \
  -H "X-API-Key: <你的 API_KEY>" \
  -d '{
    "source_type": "article",
    "article_text": "當股票突破 20 日新高且成交量大於均量 1.5 倍時...",
    "article_url": "https://example.com/momentum-strategy"
  }'
```

---

## 自動排程時間表

| 觸發器 | 頻率 | 用途 |
| --- | --- | --- |
| Daily Skill Learning Trigger | 每日 07:00 | 自動從 Readwise 抓 highlights |
| Podcast RSS Trigger | 每 4 小時 | 檢查 Podcast 新集 → Groq 轉譯 → 技能萃取 |
| Schedule Trigger | 每 15 分鐘 | 原有 RSS 新聞監控（非技能學習） |

---

## n8n Workflow 架構圖

```
Lane 1 (Y=300): RSS 新聞監控
Schedule → Fetch Sources → Fetch Feed → Sanitize → Parse XML → Iterate → Send to Advisor

Lane 2 (Y=800): Readwise 每日學習
Daily Trigger → POST /webhook/skill-learning (highlight)

Lane 3 (Y=1100): Podcast RSS 監控
Podcast RSS Trigger → Feed List → Fetch Feed → Extract Episode → Download Audio → Groq Whisper → POST /webhook/skill-learning (podcast)
```

---

## Troubleshooting

| 問題 | 排查 |
| --- | --- |
| Groq 429 Too Many Requests | 降低 Podcast RSS Trigger 頻率或減少 feed 數量 |
| n8n 找不到 GROQ_API_KEY | 檢查 docker-compose 環境變數或 n8n Settings → Variables |
| Readwise 無回傳 | 確認 `READWISE_TOKEN` 有效且 highlight 存在 |
| Webhook 401 Unauthorized | 確認 `X-API-Key` header 值正確 |
| Podcast 音檔下載失敗 | 某些 podcast 有 CDN 限制，可在 n8n 加 retry |
