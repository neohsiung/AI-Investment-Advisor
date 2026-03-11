# 非同步開發庫指南 (Async Libraries Guide)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |


描述：介紹本專案中使用的核心非同步通訊庫 `httpx` 與 `aiosmtplib` 的採用理由與實作規範。
Description: Introduction to the core async communication libraries `httpx` and `aiosmtplib` used in this project, including rationale and implementation standards.

---

## 歷史修訂 (Version History)

| 版本 (Version) | 日期 (Date) | 修訂內容 (Changes) | 作者 (Author) |
| :--- | :--- | :--- | :--- |
| v1.0 | 2026-02-18 | 初始版本：定義 httpx 與 aiosmtplib 使用規範。 | Antigravity |

---

## 1. 採用背景 (Rationale)

為了確保投資顧問平台在高併發行情分析與大量報告發送時不產生阻塞，本專案強制採用「全非同步」(Async-First) 的 I/O 策略。

### 1.1 httpx (非同步 HTTP 客戶端)
`httpx` 是專案中用於所有 Webhook 與外部 API 調用（如 LINE, Slack, Telegram）的主力工具。

- **原生 AsyncIO 支援**：完全相容 `async/await` 語法。
- **高效能**：支援連線池 (Connection Pooling)，大幅減少 HTTPS 握手開銷。

### 1.2 aiosmtplib (非同步 SMTP 客戶端)
`aiosmtplib` 用於非同步發送電子郵件，確保當發送包含大量數據的時報或週報時，不會阻塞系統主執行緒。

- **避免阻塞**：傳統的 `smtplib` 是同步的，在網路延遲較高時會導致整個 Agent 停擺。

---

## 2. 實作規範 (Implementation Standards)

### 2.1 httpx 基本用法 (Basic Usage)
```python
import httpx

async def call_api():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.line.me/v2/bot/message/push",
            json=payload,
            headers=headers
        )
        return response.status_code == 200
```

### 2.2 aiosmtplib 基本用法 (Basic Usage)
```python
import aiosmtplib
from email.message import EmailMessage

async def send_async_email(msg: EmailMessage, config: dict):
    await aiosmtplib.send(
        msg,
        hostname=config['server'],
        port=config['port'],
        username=config['user'],
        password=config['password'],
        start_tls=True
    )
```

---

## 3. 關聯文檔 (Related Documents)

- [全通路適配器規範 (Omni-Channel Adapter Standards)](全通路適配器規範-Omni-Channel-Adapter-Standards)
- [開發環境設定 (Environment Setup)](環境設定與本地開發-Environment-Local-Dev)

---
> [!NOTE]
> 本文件遵循「迴圈式填補迭代 (Iterative Patching Loop)」原則，確保護理與技術規格同步。
