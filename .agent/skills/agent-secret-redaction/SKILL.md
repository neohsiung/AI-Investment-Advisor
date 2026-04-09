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

### 3. CodeQL Taint 斷點原則 (CodeQL Taint-Break Rule)

> 觸發時機：任何 config dict / env var / user input 的值流入 `print()` / `logger.*()`

CodeQL 的 taint analysis 會追蹤整個資料流，包括：
- `agent.config.get('key')` → tainted
- `os.getenv('KEY')` → tainted
- `ternary: value if condition else 'safe'` → **true branch 仍是 tainted**
- `allowlist lookup: value if value in set else 'unknown'` → **仍被標記**

**唯一正確的 taint 斷點**：完全不讓外部資料值進入 print/logger：

```python
# ❌ 全部仍被 CodeQL 標記：
logger.info(f"Provider: {config.get('provider')}")
_p = config.get('provider'); logger.info(f"Provider: {_p}")
_p = _raw if _raw in allowlist else 'unknown'; logger.info(f"{_p}")

# ✅ 唯一完全安全的模式（用於 debug/verification scripts）：
logger.info("--- Testing LLM Gateway (MockLLMGateway) ---")  # 純靜態

# ✅ 若確實需要記錄值（production logger），使用 %-style 並截斷：
logger.error("Streaming error: %s", str(e)[:200])  # 不使用 f-string
```

### 4. SSE Stream Exception 暴露 (SSE Stream Exposure)

> 觸發時機：撰寫 StreamingResponse / event_generator() 時

SSE 生成器的 except block 不走 HTTP exception handler，直接 yield 到 client：

```python
# ❌ 直接將 exception 傳給 client：
except Exception as e:
    yield f"data: {json.dumps({'error': str(e)})}\n\n"

# ✅ 正確：server-side 完整 log，client 只收 generic message：
except Exception as e:
    logger.error("Streaming error in generator: %s", str(e)[:200])
    yield f"data: {json.dumps({'error': 'An internal streaming error occurred.'})}\n\n"
```

### 5. 全面盤查指令 (Comprehensive Taint Scan)

當 CodeQL 回報 PR 有新 taint 警告時，先執行以下全面掃描：

```bash
# 找出 config/env var 衍生值流入 logger/print 的地方
grep -rn "logger\.\|print(f" src/ scripts/ services/ 2>/dev/null \
  | grep -v ".pyc\|#\.\*print\|test_" \
  | grep "config\.\|\.config\[\|os\.getenv\|os\.environ" \
  | grep -v "_safe_\|Static print\|static"

# 找出 SSE stream 中的 str(e) 暴露
grep -rn "yield.*str(e)\|json.dumps.*str(e)" src/ services/
```

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
