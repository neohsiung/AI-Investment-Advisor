---
name: agent-secret-redaction
description: Rules and patterns for redacting sensitive information (API Keys, Bearer Tokens) from logs and persisted state (WAL).
---

# Agent Secret Redaction Skill

## 概述 (Overview)

為了遵循 **Rule #13 (No-Hardcoded-Secrets)** 與解決 CodeQL 識別出的「資訊過度暴露」風險，所有繼承自 `BaseAgent` 的智能體在進行日誌處理或狀態持久化（如 WAL Checkpoints）時，必須執行脫敏處理。

## 實作模式 (Implementation Pattern)

### 1. 使用 `BaseAgent.redact_secrets`

所有核心 Agent 邏輯在寫入 `STATE.md` 或 `WAL` 之前，應呼叫繼承自 `BaseAgent` 的內建脫敏方法。

```python
# 範例：在持久化狀態前進行脫敏
def _perform_silent_flush(self):
    # 建立脫敏後的複本進行寫入
    redacted_wal = [self._redact_secrets(str(item)) for item in self.wal_state]
    
    with open(self.state_path, "w") as f:
        f.write("# Agent State\n\n")
        f.write("\n".join(redacted_wal))
```

### 2. 日誌脫敏規範 (Logging Standard)

嚴禁直接將包含 `secret`, `token`, `key` 等關鍵字的原始物件或回應內容寫入日誌。

- **錯誤示範**: `logger.info(f"Received webhook with secret: {secret}")`
- **正確示範**: `logger.info(f"Received webhook with signature: {self._redact_secrets(secret)}")`

## 脫敏規則與範圍 (Redaction Scope)

目前的 `_redact_secrets` 涵蓋以下模式：

- **OpenAI/Anthropic API Keys**: `sk-...`
- **Bearer Tokens**: `Authorization: Bearer ...`
- **Generic Secrets**: 包含 `secret`, `api_key`, `access_token` 等關鍵字的 JSON 欄位。
- **Finnhub/Webhooks**: `webhook_secret`, `token=...`

## 驗證 (Verification)

開發者應定期執行 `grep` 檢查 `STATE.md` 與 `logs/` 目錄，確保無洩漏：

```bash
grep -rE "sk-[a-zA-Z0-9]{20,}" .
```
