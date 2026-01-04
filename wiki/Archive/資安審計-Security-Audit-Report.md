# Security Audit Report

> **[English](#english) | [繁體中文 (Traditional Chinese)](#traditional-chinese)**

<a id="english"></a>

## 🇺🇸 Security Audit Report

### Goal
Identify and fix vulnerabilities to ensure confidentiality, integrity, and availability of user data (API Keys, Portfolio).

### Why
- **Sensitive Data**: Investment data is private.
- **Cost Risk**: Leaked API keys lead to huge bills.
- **Server Safety**: Prevent SQLi/Command Injection.

### Analysis (What)
Executed comprehensive audit:
1.  **SAST**: `bandit` source code scan.
2.  **Dependency Check**: `requirements.txt` check.
3.  **Secret Audit**: Manual check for hardcoded secrets.

### Findings & Fixes (How)

#### A. SQL Injection (Fixed)
- **Issue**: String concatenation in `dashboard.py`.
- **Fix**: Use **Parameterized Queries** (SQLAlchemy `text(:param)`).

#### B. Hardcoded Secrets (Fixed)
- **Issue**: API Keys in code.
- **Fix**: Removed keys. Use `os.getenv` and `.gitignore`.

#### C. Command Injection (Fixed)
- **Issue**: `subprocess.run` without filtering.
- **Fix**: Use `sys.executable` and avoid `shell=True`.

### Recommendations
- **Least Privilege**: Global Cloud Run Service Account permissions.
- **CI/CD**: Add `bandit` to GitHub Actions.

---

<a id="traditional-chinese"></a>

## 🇹🇼 資安審計報告 (Security Audit Report)

### 目標 (Goal)
識別並修復系統中的潛在安全漏洞，確保使用者數據 (持倉、API Key) 的機密性、完整性與可用性。

### 為什麼 (Why)
- **金融數據敏感**: 投資持倉雖非銀行帳戶，但仍屬高度隱私。
- **API Key 保護**: OpenAI/Google API Keys 若外洩將導致鉅額費用。
- **防禦惡意攻擊**: 避免 SQL Injection 或 Command Injection 導致伺服器被挾持。

### 做了什麼 (What)
我們執行了全面的資安檢測，包含：
1.  **SAST (靜態掃描)**: 使用 `bandit` 掃描原始碼。
2.  **Dependency Check**: 檢查 `requirements.txt` 第三方套件漏洞。
3.  **Secret Audit**: 人工與工具審查是否有 Hardcoded Secrets。

### 如何進行 (How) - 審計發現與修復

#### 1. 發現與修復 (Findings & Fixes)

**A. SQL Injection (已修復)**
- **問題**: `dashboard.py` 中曾有部分查詢字串拼接。
- **修復**: 全面改用 **Parameterized Queries** (SQLAlchemy `text(:param)`).

**B. Hardcoded Secrets (已修復)**
- **問題**: 開發初期方便測試，將 API Key 寫在 code 中。
- **修復**:
    - 移除所有 Key。
    - 強制從環境變數 (`os.getenv`) 或資料庫 `settings` 表讀取。
    - 加入 `.gitignore` 排除 `.env` 與 `client_secret.json`。

**C. Command Injection (已修復)**
- **問題**: `subprocess.run` 呼叫外部指令時未過濾輸入。
- **修復**: 使用 `sys.executable` 確保執行正確的 Python 直譯器，並避免使用 `shell=True` 除非必要且經過過濾。

#### 2. 持續防護建議 (Recommendations)
- **最小權限原則**: Cloud Run 的 Service Account 僅給予必要的 GCS/SQL 權限。
- **定期掃描**: 在 CI/CD Pipeline 中整合 `bandit` 與 `safety` 檢查。
