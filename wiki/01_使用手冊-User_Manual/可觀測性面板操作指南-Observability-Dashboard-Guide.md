### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-28 | v5.2 | **Mac Bridge Fix**: Updated endpoint to `host.docker.internal` for high-reliability OTel connectivity. | Antigravity |
| 2026-02-27 | v5.1 | **Optimization**: Added Alert Dashboard setup guide and OpenTelemetry trace propagation improvements. | Neo |
| 2026-02-21 | v5.0 | **Initial Release**: Created step-by-step guide for SigNoz APM initialization and observability base setup. | Neo |

# 可觀測性面板操作指南 (Observability Dashboard Guide)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 SigNoz 面板初始設定與操作指南

當您成功透過 `docker compose up -d` 啟動了 AI Investment Advisor 的所有微服務與基礎設施後，SigNoz 會預設在 **`http://localhost:8080`** 啟動並開始接收 OpenTelemetry (OTel) 數據。

本指南提供您「首次登入」時的 Step-by-Step 儀表板設定教學，幫助您快速建立系統觀測基線 (Observability Base)。

### Step 1: 建立系統管理員帳號
1. 打開瀏覽器，前往 `http://localhost:8080`。
2. 首次進入時，畫面會要求您建立第一組 Admin 帳號 (Create an account)。
3. 輸入您的 Email、密碼以及組織名稱（例如：`AI Advisor Platform`），點擊 **Create Account**。
*(這組帳號資料僅儲存於您本地端的 SQLite 容器內，不會上傳到任何雲端)*

### Step 2: 連結資料來源 (Connect Data Source)
登入後，您會看到歡迎畫面寫著 *"Hello there, Welcome to your SigNoz workspace"*[1]。由於所有微服務（Dashboard, Scheduler, MCP, Notification）的 Docker 容器啟動時就已經配置了 `OTEL_EXPORTER_OTLP_ENDPOINT=http://host.docker.internal:4317` (或透過 `otel-collector:4317` 橋接)，因此遙測資料**已經開始默默地流向 SigNoz 了**。

1. **略過設定精靈**: 畫面上可能顯示 *"You're not sending any data yet"*[1] 以及右側的 *"Build your observability base"* 勾選清單。**這是因為我們透過 Backend 直接注射資料，UI 還沒來得及刷新**。
2. 點擊畫面上的 **[Connect Data Source]** 按鈕。
3. 系統會詢問您的應用程式類型 (Go, Python, Java 等)。請直接點擊右上角的 **[Explore Data]** 或左側導覽列的 **[Services]** 跳過驅動程式安裝流程（這些在源碼中已經預先設定好了）。

---

### Step 3: 探索微服務儀表板 (Services Dashboard)

1. 點擊左側功能表的 **[Services]**。
2. 您應該能看見以下服務出現在列表中（預設透過 `OTEL_SERVICE_NAME` 註冊）：
   - `dashboard` (Streamlit 介面)
   - `scheduler` (排程器)
   - `mcp_server` (工具 API)
   - `notification_service` (通知轉發服務)
3. 點擊任意一個服務（例如 `notification_service`），即可進入該服務的專屬觀測面版並查看：
   - **Application Metrics**: P99 Latency、Error Rate、Requests per second。
   - **Database Calls**: 如果觸發了 SQLAlchemy 資料庫操作，此處會顯示 SQL 執行時間。

---

### Step 4: 日誌結構化檢索 (Logs Explorer)

遵循我們制定的「系統可觀測性規範」，所有微服務的標準輸出 (stdout) 皆使用 `python-json-logger` 結構化日誌。

1. 點擊首頁或左側導覽列的 **[Open Logs Explorer]**。
2. 您將會看到一個類似 Kibana 的查詢介面。
3. **過濾欄位 (Filter)**: 在搜尋框輸入以下條件來追蹤指定行為：
   - `service.name_str = "scheduler"` 可篩選出所有來自 Scheduler 的日志。
   - 查詢 `level_str = "ERROR"` 可以快速找出所有發生異常的崩潰紀錄。
4. 點開任何一筆 Log，您會發現格式如同 JSON 般工整，並帶有專屬的 `trace_id`，這對於跨容器抓蟲 (Debugging) 非常有幫助。

---

### Step 5: 追蹤鏈路與效能瓶頸 (Traces & APM)

分散式追蹤 (Distributed Tracing) 是微服務架構的核心能力。

1. 點開左側功能表的 **[Traces]**。
2. 當 Dashboard 向 MCP Server 或者 Notification Service 發送 HTTP POST 請求時，此處會產生一條 Trace。
3. 點擊進入其中一筆 Trace (例如 HTTP URI `/api/v1/notify`)，您會看到一個 **Gantt Chart (甘特圖)**。
4. 這個圖表清楚地顯示了請求是如何從 `dashboard` 容器發出，然後在 `notification_service` 內部執行非同步邏輯，並最終存入資料庫，讓您一眼看出系統的延遲效能瓶頸發生在哪一個函數/語句上。

---
 
 ### Step 6: 建立告警規則與自定義儀表板 (Alerts & Dashboards)
 
 為了確保系統在發生異常時能主動通知，您需要設定告警閾值。
 
 1. **建立告警規則**:
    - 點擊左側 **[Alerts]** -> **[New Alert Rule]**。
    - **指標選擇 (Metric)**: 選擇 `latency` 或 `error_rate`。
    - **條件設定**: 例如設定 `Error Rate > 5%` 持續 5 分鐘。
    - **通知管道**: 連結您的 Slack Webhook 或 Email。
 2. **建立自定義儀表板**:
    - 點擊 **[Dashboards]** -> **[New Dashboard]**。
    - 加入 **Panel**: 選擇 "Value" 或 "Time Series"。
    - **查詢語法**: 使用 `signoz_calls_total` 指標來觀察特定 Agent 的觸發頻率。
 
 ### 告警工作流架構 (Alerting Workflow)
 
 ```mermaid
 graph TD
     A[""微服務 (Services")"] -->|"OTLP Traces/Logs"| B["OTel Collector"]
     B -->"C[""SigNoz Engine"]
     C --> D{""告警引擎 (Alert Manager")"}
     D -->"|符合閾值| E["""通知中心 (Notification Service")"]
     E -->"F[""LINE / Email / Slack"]
     D -->|"OK"| G[""持續監控 (Monitoring")"]
 ```
 
 ---
 
 > 🎉 **完成！** 
 > 您現在已經建立了您的第一個地端可觀測性基地。您可以隨時返回首頁點選 **[Create a dashboard]** 來自定義專屬的監控看板（例如：將 Sentinel 觸發次數與報錯率拉成折線圖置頂）。

---

<a id="en"></a>
## 🇺🇸 SigNoz Setup and Operational Guide

Once you've launched the AI Investment Advisor infrastructure via `docker compose up -d`, SigNoz initializes on **`http://localhost:8080`** and acts as the collection point for all OpenTelemetry (OTel) metrics, logs, and traces.

Follow this guide to set up your workspace and establish a robust Observability Base.

### Step 1: Create an Admin Account
1. Open a browser and navigate to `http://localhost:8080`.
2. As a first-time user, you must register a local admin account.
3. Input your email, password, and organization name (e.g., `AI Advisor Platform`), then click **Create Account**. *(Note: This data is stored locally in your SQLite container, no cloud transmission occurs).*

### Step 2: Connect Data Source Validation
Upon login, you may see a welcome screen displaying *"You're not sending any data yet"* alongside a setup checklist [1]. Because our microservices have telemetry pre-configured at boot via the `OTEL_EXPORTER_OTLP_ENDPOINT` pointing to `host.docker.internal:4317`, the data is already flowing asynchronously.

1. **Skip the Setup Wizard**: 
2. Click the **[Connect Data Source]** button.
3. The system might ask what language your app is coded in. You can simply bypass this installation sequence by clicking **[Explore Data]** in the top-right corner, or by navigating directly to **[Services]** on the left menu. The python OTel SDK instrumentation is already hardcoded into the project base.

### Step 3: Explore Microservice Telemetry
1. Navigate to **[Services]** via the left sidebar.
2. The OTel Collector automatically registers the following applications:
   - `dashboard`
   - `scheduler`
   - `mcp_server`
   - `notification_service`
3. Click on any of these to drill down into the service-specific APM metrics. You will be able to monitor the P99 Error Rates, Latencies, and throughput parameters immediately.

### Step 4: Utilize the Logs Explorer
All applications are forced to output `python-json-logger` payloads strictly conforming to our observability configurations.
1. Access the **[Logs]** explorer.
2. In the query builder, filter by `service.name_str = "scheduler"` or use `level_str = "ERROR"` to instantly catch pipeline failures without ssh'ing into the containers.
3. Every log natively encapsulates its correlated `trace_id`, making cross-boundary debugging significantly easier.

### Step 5: Setting Up Alerts and Custom Dashboards
 
 Proactive monitoring requires setting up thresholds for critical metrics.
 
 1. **Configure Alert Rules**:
    - Go to **[Alerts]** -> **[New Alert Rule]**.
    - **Condition**: Set a threshold such as `Error Rate > 1%` or `Latency P99 > 2s`.
    - **Action**: Connect to Slack, PagerDuty, or Webhook.
 2. **Build Custom Dashboards**:
    - Navigate to **[Dashboards]** -> **[New Dashboard]**.
    - Add panels to visualize specific Agent performance or Sentinel hit rates using clickhouse-based queries.
 
 ### Alerting Architecture
 
 ```mermaid
 graph TD
     A["Microservices"] -->|"OTLP"| B["OTel Collector"]
     B -->"C[""SigNoz"]
     C --> D{"Alert Rules"}
     D -->"|Trigger| E[""Notification Module"]
     E -->"F["""End User (Ops/Admin")"]
 ```
 
 > 🎉 **You're All Set!** 
 > The foundation of your Observability Base is built. Proceed to **[Dashboards]** to create customized visualization panels tailored precisely to your Sentinel automation hit-rates and agent latency profiles.
 
 ---
 
 [1] UI Reference from user snapshot.
