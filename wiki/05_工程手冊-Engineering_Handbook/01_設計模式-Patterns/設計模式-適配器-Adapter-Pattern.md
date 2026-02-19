# 適配器模式 (Adapter Pattern)

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 適配器模式 (Structural Pattern)

本文件說明如何透過 Adapter Pattern 統一系統中異質介面的調用，確保核心邏輯的穩定性。

### 1. 願景與設計動機 (Problem & Goals - ADR-005)
- **挑戰**: 系統需要對接多個異質管道（LINE, Email, Web）與券商（eToro, Futu, IBKR），每個管道的 API 參數與資料格式迥異。
- **決策**: 定義標準化介面（如 `IChannelAdapter`, `IBroker`），並為每個管道實作專屬 Adapter。
- **目標**: 達成核心邏輯與交付媒介、外部券商的完全解耦。

### 2. 情境對比 (Good vs. Bad)

````carousel
```python
# ❌ Before: 核心邏輯感知具體管道 (Hardcoded)
if channel == "line":
    line_bot.send_flex(msg)
elif channel == "email":
    smtp_client.send(msg)
```
<!-- slide -->
```python
# ✅ After: 透過介面調用 (詳見 src/services/notification_service.py)
# 核心邏輯只需呼叫 notify_all，內部自動分發
notification_service.notify_all(title, content)
```
<!-- slide -->
> [!NOTE]
> **擴充性**: 
> 當需要新增 Slack 管道時，只需新增 `SlackAdapter` 並實作 `send_alert` 介面，完全無須修改 `SentinelService`。
````

### 3. 主要實作案例
- **全通路通知**: 用於 `NotificationService` 統籌 LINE、Email 與 Web 事件紀錄。
- **券商整合**: `BrokerFactory` 回傳符合 `IBroker` 介面的適配類別。
- **評議會適配**: `CouncilAgentAdapter` 將複雜的多人辯論機制封裝成單一 Agent 介面。

---

<a id="en"></a>

## 🇺🇸 Adapter Pattern

### 1. Vision & Goals (ADR-005)
Standardize heterogeneous interfaces (Notifications, Brokers, Council) to protect the core reasoning engine from external API volatility.

### 2. Real-world Examples
- **Omni-channel Notifications**: Decoupling alerts from LINE Flex or SMTP details.
- **Multi-broker Bridge**: Unifying eToro, Futu, and IBKR under a single `IBroker` interface.
- **Council Adapter**: Wrapping the fractal debate logic into a standard Agent call.

## 🔗 Bidirectional Links
- **Intro**: [Design Patterns Intro](設計模式導讀-Design-Patterns-Intro)
- **Landscape**: [System Landscape](系統全景圖-System-Landscape)
- **Notification Standards**: [Omni-Channel Adapter Standards](全通路適配器規範-Omni-Channel-Adapter-Standards)
