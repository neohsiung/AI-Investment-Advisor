# 安全政策 / Security Policy

> [繁體中文](#zh) | [English](#en)

<a id="zh"></a>

## 安全政策

這個專案可以用真錢下單，所以安全性與資料完整性優先於功能。以下說明支援哪些版本、怎麼回報漏洞，以及系統內建的防護。

### 支援版本

目前只有 `main` 分支和最新的 0.x 版會收到安全更新。

| 版本 | 支援狀態 |
| ------- | ------------------ |
| main 與最新的 0.x | 支援 |
| 更舊的 0.x | 不支援 |

### 回報漏洞

如果你認為發現了安全漏洞，請不要開公開的 Issue，照下面做：

1. 把報告寄到 `support@litov.app`。
2. 信裡寫漏洞的描述、重現步驟和可能的影響。
3. 我們會回覆，並告訴你修復的時程，之後在揭露前持續更新進度。

### 內建防護

1. **緊急狀況**：`SentinelService` 偵測到市場異常時，預設只發通知，不下單。設定 `sentinel_emergency_protocol_mode` 改成 legacy 才會自動清倉。
2. **參數化查詢**：核心交易資料庫 PostgreSQL 的查詢一律用參數化查詢，防止 SQL Injection。
3. **機密隔離**：不把 API 金鑰或個資寫死在程式裡。機密只從環境變數 `.env` 或加密的資料庫設定表讀取。
4. **映像檔**：容器部署使用經過挑選的基底映像檔，例如 `python:3.11-slim-bookworm`，套件版本鎖定。

---

<a id="en"></a>

## Security Policy

This project can place real orders with real money, so security and data integrity come before features. This page says which versions are supported, how to report a vulnerability, and which defenses are built in.

### Supported versions

Only the `main` branch and the latest 0.x release receive security updates.

| Version | Supported |
| ------- | ------------------ |
| main and the latest 0.x | Yes |
| Older 0.x | No |

### Reporting a vulnerability

If you believe you have found a security vulnerability, do not open a public issue. Instead:

1. Email the report to `support@litov.app`.
2. Include a description, steps to reproduce, and the potential impact.
3. We will reply with a timeline for a fix and keep you updated until disclosure.

### Built-in defenses

1. **Emergencies**: when `SentinelService` detects a market anomaly it only sends a notification by default and places no orders. It liquidates automatically only if `sentinel_emergency_protocol_mode` is set to legacy.
2. **Parameterized queries**: queries against the core transaction database (PostgreSQL) are parameterized to prevent SQL injection.
3. **Secrets isolation**: no hardcoded API keys or personal data. Secrets come from environment variables (`.env`) or encrypted database settings.
4. **Base images**: deployment uses selected base images, for example `python:3.11-slim-bookworm`, with pinned dependencies.
