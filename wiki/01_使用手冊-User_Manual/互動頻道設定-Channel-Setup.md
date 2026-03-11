# 互動頻道設定 (Channel Setup Guide)

本文件提供全通路 (Omni-Channel) 互動設定的 Step-by-Step Runbook。支援的頻道包括 LINE, Slack, Telegram, Messenger 與 Google Chat。

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-16 | v3.8.1 | Updated for Omni-Channel Factory & Settings | Neo |

> **提示**: 所有設定均可透過儀表板 `Settings > Interaction & Comms` 頁面進行動態管理。系統啟動時將自動透過 `ChannelFactory` 載入所有已啟用的頻道。

---

## 🧭 通用流程 (General Workflow)

```mermaid
graph LR
    A[User/Admin] -->"|1. Create Bot/App| B(External Provider)"
    B -->|2. Get Tokens| A
    A -->"|3. Input Credentials| C[Dashboard Settings]"
    C -->"|4. Save to DB| D[""(Settings DB")]
    E[ChannelFactory] -->|5. Read Settings| D
    E -->"|6. Instantiate Adapters| F[NotificationService]"
    F -->"|7. Notify All| G[Users]"
```

---

## 1. LINE (Personal)

最完整的個人化互動體驗，支援 Rich Menu 與 Postback 按鈕。

### Step 1: 建立 Provider 與 Channel
1. 前往 **[LINE Developers Console](https://developers.line.biz/)**。
2. 建立一個新的 **Provider** (或是使用既有的)。
3. 建立一個 **Messaging API** Channel。

### Step 2: 取得憑證 (Credentials)
1. 在 **Basic settings** 頁籤，找到 **Channel Secret**。
2. 在 **Messaging API** 頁籤，找到 **Channel access token** (若無則點擊 Issue)。
3. 在 **Messaging API** 頁籤，關閉 "Auto-reply messages" 與 "Greeting messages"。
4. 設定 **Webhook URL**: `https://<YOUR_DOMAIN>/mcp/v1/callback` (需啟用 Use webhook)。

### Step 3: 系統設定
1. 進入系統 Dashboard -> **Settings** -> **Interaction & Comms** -> **Personal Channels (LINE)**。
2. 填入 **Channel Access Token** 與 **Channel Secret**。
3. 勾選 **Enable LINE Channel**。
4. 點擊 **Save Settings**。

### Step 4: 驗證
1. 點擊 **Send Test Message** 按鈕。
2. 檢查手機 LINE 是否收到 "Test Message from Investment Advisor"。

---

## 2. Slack (Group)

適合團隊協作與即時戰情室通知。

### Step 1: 建立 App
1. 前往 **[Slack API Apps](https://api.slack.com/apps)** -> **Create New App** -> **From scratch**。
2. 選擇你的 Workspace。

### Step 2: 設定權限與 Scope
1. 進入 **OAuth & Permissions**。
2. 在 **Bot Token Scopes** 新增: `chat:write`, `channels:read`。
3. 點擊 **Install to Workspace** 並授權，取得 **Bot User OAuth Token** (`xoxb-...`)。

### Step 2.5: 啟用 Interactivity (關鍵)
1. 在左側選單點擊 **Interactivity & Shortcuts**。
2. 開啟 **Interactivity** 開關 (On)。
3. **Request URL**: `https://<YOUR_DOMAIN>/mcp/v1/callback/slack`。
4. 點擊 **Save Changes**。

### Step 3: 取得 Channel ID
1. 在 Slack 桌面版/網頁版，對著你想接收通知的頻道按右鍵 -> **Copy Link**。
2. 網址最後一串亂碼即為 Channel ID (例如 `C012345678`)。
3. **重要**: 需將 App 邀請入該頻道 (在頻道內輸入 `/invite @YourApp`)。

### Step 4: 系統設定
1. Dashboard -> **Interaction & Comms** -> **Group Channels (Slack)**。
2. 填入 **Bot Token** 與 **Channel ID**。
3. 勾選 **Enable Slack Channel** 並儲存。

### Step 5: 驗證
1. 點擊 **Send Test Message**。
2. 確認 Slack 頻道收到訊息。

---

## 3. Telegram (Personal/Group)

輕量級、高隱私的通知選擇。

### Step 1: 建立 Bot
1. 在 Telegram 搜尋 **@BotFather**。
2. 輸入指令 `/newbot`。
3. 依指示設定 Bot Name 與 Username。
4. 取得 HTTP API **Token**。

### Step 2: 取得 Chat ID
1. 啟動你的 Bot (點擊 Start)。
2. 傳送一則任意訊息給 Bot。
3. 呼叫 API: `https://api.telegram.org/bot<YourToken>/getUpdates`。
4. 在回應 JSON 中找到 `"chat": {"id": 123456789}`，該數字即為 **Chat ID**。

### Step 3: 系統設定
1. Dashboard -> **Interaction & Comms** -> **Personal Channels (Telegram)**。
2. 填入 **Bot Token** 與 **Chat ID**。
3. 勾選 **Enable Telegram Channel** 並儲存。

---

## 4. Messenger (Personal)

透過 Facebook Page 進行通知。

### Step 1: 建立 App 與 Page
1. 前往 **[Meta for Developers](https://developers.facebook.com/)** -> **My Apps** -> **Create App**。
2. 選擇 **Other** -> **Business**。
3. 在 App Dashboard 新增 **Messenger** 產品。

### Step 2: 取得 Token
1. 在 Messenger 設定頁面，建立或連結一個 Facebook Page。
2. 點擊 **Generate Token** 取得 **Page Access Token**。
3. 設定 **Verify Token** (自訂字串，需記下)。

### Step 3: 設定 Webhook (接收訊息用)
1. 在 Messenger 設定頁面點擊 **Setup Webhooks**。
2. Callback URL: `https://<YOUR_DOMAIN>/mcp/v1/callback/messenger`。
3. Verify Token: 輸入剛才自訂的字串。
4. 訂閱欄位: `messages`, `messaging_postbacks`。

### Step 4: 系統設定
1. Dashboard -> **Interaction & Comms** -> **Personal Channels (Messenger)**。
2. 填入 **Page Access Token** 與 **Verify Token**。
3. 勾選 **Enable Messenger Channel** 並儲存。

---

## 5. Google Chat (Group)

透過 Webhook 進行單向通知 (最簡單設定)。

### Step 1: 設定 Webhook
1. 進入 Google Chat Space (群組)。
2. 點擊群組標題 -> **Apps & integrations** -> **Manage webhooks**。
3. 輸入 Name (e.g., "Advisor Bot") -> Save。
4. 複製生成的 **Webhook URL**。

### Step 2: 系統設定
1. Dashboard -> **Interaction & Comms** -> **Group Channels (Google Chat)**。
2. 填入 **Webhook URL**。
3. 勾選 **Enable Google Chat Channel** 並儲存。

---

## ✅ 驗證策略 (Verification Strategy)

完成設定後，建議執行以下完整測試循環：

1. **連線測試**: 使用 Dashboard 的 "Send Test Message" 功能。
2. **審核流程測試**:
   - 觸發需審核的交易 (可透過手動腳本或模擬信號)。
   - 確認是否在所有啟用頻道收到 "Approve/Reject" 請求。
   - 在任一頻道回覆 "執行" 或 "OK"。
   - 確認系統收到回覆並執行後續動作。

---

## 🔗 相關文件 (See Also)
- **[快速啟動與操作指南](快速啟動與操作指南-Quickstart-User-Guide)**: 系統整體啟動流程。
- **[全通路適配器規範](全通路適配器規範-Omni-Channel-Adapter-Standards)**: 深入了解適配器架構與開發者細節。
- **[底層通信協議](底層通信協議-Agent-Mesh-Protocols)**: 了解 MCP 與全通路訊息流。
