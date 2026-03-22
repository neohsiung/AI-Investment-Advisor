# 資安管理與基礎映像檔規範 (Security and Base Image Standard)

## 版本紀錄 (Iteration Record)

| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-03-22 | v1.2 | 實作集中化及脫敏工具 (`src/utils/security.py`) 並加固日誌安全。 | Antigravity |
| 2026-03-08 | v1.1 | 新增密碼雜湊規範 (SHA256) 與全域秘密遮蔽機制 (BaseAgent Redaction)。 | Antigravity |
| 2026-02-17 | v1.0 | 初始規範建立，採用 Rule #11 標準。 (Initial Release, following Rule #11) | Antigravity |

---

## 概述

本文件定義了 AI Investment Advisor 平台的容器映像檔建置規範與第三方依賴項的資安審計流程。依據 **Rule #11 (Managed-Security-Base)**，所有生產環境的基礎設施必須遵循「最小化、硬化與可追蹤」原則。

## 基礎映像檔規範

### 1. 基礎映像檔選擇

強制使用官方維護的 **Slim** 或 **Hardened** 變體，以減少攻擊面。

- **標準映像檔**: `python:3.11-slim-bookworm` (Debian 12 為基礎)。
- **禁用**: 嚴禁使用 `latest` 標籤或未經認證的第三方映像檔。

### 2. 映像檔建置原則

- **非 Root 執行**: 映像檔內部必須建立專用的 `appuser` (UID/GID 10001)，嚴禁使用 `root` 執行應用程式。
- **最小化層級**: 使用 `.dockerignore` 排除不必要的測試程式、日誌與敏感憑證。
- **快取優化**: 優先複製 `requirements.txt` 以利用 Docker 層級快取，減少重複下載。

## 依賴項管理

### 1. 版本鎖定

生產環境的 `requirements.txt` 必須精確鎖定版本 (e.g., `pandas==2.1.0`) 或定義嚴格的最低安全版本 (e.g., `requests>=2.31.0`)。

### 2. 資安審計流程

所有代碼與依賴項在進入生產分支前，必須通過以下自動化掃描：

```mermaid
graph TD
    A[代碼提交 Code Commit] --> B{資安掃描 Scan}
    B -->"| Bandit | C[SAST 靜態檢查]"
    B -->"| Safety | D[依賴項漏洞檢查]"
    B -->"| Pip-audit | E[OSV 資料庫對比]"
    C --> F{通過審核?}
    D --> F
    E --> F
    F -->"| Yes | G[映像檔建置 Image Build]"
    F -->"| No | H[修補漏洞 Fix/Patch]"
    H --> A
```

### 3. 密碼學規範 (Cryptographic Standards)

- **雜湊算法**: 嚴禁使用 `MD5` 或 `SHA1` 進行安全相關的 ID 生成或雜湊。強制使用 `SHA256` 或更高版本。
- **隨機數**: 使用 `secrets` 模組而非 `random` 生成安全權杖或密鑰。

### 4. 秘密遮蔽與日誌安全 (Secret Redaction & Logging)

- **全域遮蔽**: 所有繼承自 `BaseAgent` 的實例必須調用 `_redact_secrets()` 進行狀態持久化前的資料清理。
- **集中化脫敏工具 (v1.2)**: 強制使用 `src/utils/security.py` 中的 `redact_secrets()` 處理任何可能包含敏感資訊（如 API Key, Trace ID, Ticker）的日誌輸出。
- **日誌敏感資訊**: 嚴禁在日誌中記錄 API Key、Bearer Token 或 Webhook Secret 的任何部分。日誌應僅記錄請求的大小或不具辨識性的 Meta 資訊。

## 定期維護流程

1. **每月審查**: 每月第一週進行依賴項版本掃描與更新評估。
2. **緊急補丁**: 當高風險 CVE 公布時，需在 48 小時內完成映像檔重建與部署。
3. **基礎升級**: 每半年進行一次 Python 大版本或基礎 OS 升級評估。

## 設計原則 (Design Principles)

- **最小權限原則 (Least Privilege)**: 容器僅具備執行必要任務的權限。
- **不可變基礎設施 (Immutable Infrastructure)**: 嚴禁在運行中的容器內手動安裝或更新套件。

---

## Overview

This document defines the container image build specifications and third-party dependency security auditing process for the AI Investment Advisor platform. According to **Rule #11 (Managed-Security-Base)**, all production infrastructure must follow the "Minimize, Harden, and Trace" principles.

## Base Image Standards

### 1. Base Image Selection

The use of official **Slim** or **Hardened** variants is mandatory to reduce the attack surface.

- **Standard Image**: `python:3.11-slim-bookworm` (based on Debian 12).
- **Forbidden**: Using the `latest` tag or uncertified third-party images is strictly prohibited.

### 2. Image Build Principles

- **Non-Root Execution**: A dedicated `appuser` (UID/GID 10001) must be created within the image. Running the application as `root` is strictly prohibited.
- **Layer Minimization**: Use `.dockerignore` to exclude unnecessary test programs, logs, and sensitive credentials.
- **Cache Optimization**: Copy `requirements.txt` first to leverage Docker layer caching and reduce redundant downloads.

## Dependency Management

### 1. Version Pinning

The `requirements.txt` for production must be precisely version-pinned (e.g., `pandas==2.1.0`) or define strict minimum security versions (e.g., `requests>=2.31.0`).

### 2. Security Auditing Process

All code and dependencies must pass the following automated scans before entering the production branch:
(Refer to the Mermaid diagram in the Chinese section for the workflow).

- **Bandit**: Static Application Security Testing (SAST) for Python code.
- **Safety**: Scans `requirements.txt` for known vulnerabilities.
- **Pip-audit**: Compares dependencies against the Google Open Source Vulnerabilities (OSV) database.

## Periodic Maintenance Lifecycle

1. **Monthly Review**: Dependency scans and update evaluations are performed in the first week of every month.
2. **Emergency Patching**: Upon discovery of high-risk CVEs, image reconstruction and deployment must be completed within 48 hours.
3. **Infrastructure Upgrade**: Large-version Python or OS upgrades are evaluated every six months.

## Design Principles

- **Least Privilege**: Containers only possess the permissions necessary for their tasks.
- **Immutable Infrastructure**: Manual installation or updating of packages within running containers is strictly prohibited.
