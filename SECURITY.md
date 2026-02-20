# 專案安全政策 (Security Policy)

### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Complete rewrite conforming to GitHub Best Practices & Project Bilingual Standards | Neo |

---

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

<a id="zh"></a>

## 🇹🇼 安全政策與承諾

本專案模擬高風險的量化對沖基金環境。安全性、數據完整性與自動化防禦是我們的最高優先事項。我們承諾為開源社群及使用者提供企業級的安全保障。

### 📈 支援版本

我們主動為以下版本提供安全更新：

| 版本 | 支援狀態 |
| ------- | ------------------ |
| 1.0.x   | ✅ 是 |
| < 1.0   | ❌ 否 |

### 🚨 漏洞通報流程

我們非常重視本專案的安全性。如果您認為您發現了安全漏洞，**請勿**開啟公開的 Issue。請遵循以下流程：

1. **聯絡維護者**: 請將詳細的 CVE 或 Bug 報告發送至 `supermfb@gmail.com`。
2. **提供細節**: 信件請包含漏洞的描述、重現步驟以及潛在影響。
3. **回應時間表 (SLA)**: 
   - 我們將在 **48 小時**內確認收到您的報告。
   - 我們會提供修復的時間表，並在此責任揭露 (Responsible Disclosure) 過程中持續更新進度。

### 🛡️ 架構級安全防護

本專案內建多層級的防禦機制，確保系統在無人值守狀態下的安全性：

1. **自動對沖與清倉**: 透過 `WebhookService` 與 `SentinelService`，系統能在偵測到外部異常警報 (如 VIX 飆漲, TradingView 訊號) 時，於毫秒級自動啟動清倉程序。
2. **資安唯一原則**: 強制規定所有核心交易資料庫 (PostgreSQL) 存取必須使用參數化查詢 (Parameterized Queries) 防範 SQL Injection。
3. **敏感資源隔離**: 嚴禁硬編碼 (Hardcode) 任何 API 金鑰或 PII。所有敏感數據僅能透過環境變數 (`.env`) 或加密的資料庫設定表存取。
4. **映像檔加固**: 容器化部署強制使用經過資安審核的基底映像檔 (如 `python:3.11-slim-bookworm`)，並鎖定所有套件版本。

---

<a id="en"></a>

## 🇺🇸 Security Policy

This project simulates a high-stakes quantitative hedge fund environment. Security, data integrity, and autonomous defense are our highest priorities. We are committed to providing enterprise-grade security for the open-source community and our users.

### 📈 Supported Versions

We actively provide security updates for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | ✅ Yes             |
| < 1.0   | ❌ No              |

### 🚨 Reporting a Vulnerability

We take the security of this project seriously. If you believe you have found a security vulnerability, please do **not** open a public issue. Instead, follow the process below:

1. **Email the Maintainer**: Send a detailed CVE/Bug report to `supermfb@gmail.com`.
2. **Include Details**: Please include a description of the vulnerability, steps to reproduce, and potential impact.
3. **Response Timeline (SLA)**: 
   - Acknowledgment within **48 hours**. 
   - We will provide a timeline for a patch and keep you updated throughout the responsible disclosure process.

### 🛡️ Architecture-Level Defenses

The project implements multi-layered security to ensure autonomous operation safety:

1. **Auto-Hedging & Emergency Liquidation**: System auto-liquidates positions via Webhook alerts (`WebhookService` & `SentinelService`) without human intervention during market crashes (e.g., VIX spikes, TradingView alerts).
2. **Safe-SQL-Only Principle**: All raw SQL queries in the core transaction database (PostgreSQL) are parameterized to prevent SQL injection attacks.
3. **Secrets Isolation**: Zero-tolerance for hardcoded API keys or PII. All secrets are injected dynamically via environment variables (`.env`) or encrypted database settings.
4. **Hardened Base Images**: Uses hardened, distroless-like container images (e.g., `python:3.11-slim-bookworm`) and pinned dependencies for deployment.
