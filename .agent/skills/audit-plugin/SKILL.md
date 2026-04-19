---
name: audit-plugin
description: 在安裝任何第三方 AI 工具、plugin、skill 或 CLI 之前，先做資安審計。
---

# /audit-plugin — 安裝前資安審計

**用途**：在安裝任何第三方 AI 工具、plugin、skill 或 CLI 之前，先做資安審計。
**使用時機**：當使用者在對話中提到「安裝新 skill」、「新增工具」、「整合 Plugin」或給予一個 GitHub 工具 URL 時，**必須執行**此審計程序。

---

## 審計流程

### Step 1：使用自動化腳本 (推薦)

```bash
./.agent/skills/audit-plugin/scripts/audit_tool.sh <repo_url_or_local_path>
```

### Step 2：手動五大掃描 (詳細流程)

**2a. Telemetry / Analytics 收集**
```bash
grep -r "telemetry\|analytics\|track\|phone.home\|beacon\|segment\|mixpanel\|amplitude" \
  "$TARGET" --include="*.ts" --include="*.js" --include="*.sh" --include="*.py" \
  -l 2>/dev/null
```

**2b. 硬寫的外部 endpoint 或 API key**
```bash
grep -r "https://.*supabase\|https://.*firebase\|https://.*segment\|https://.*sentry" \
  "$TARGET" -h 2>/dev/null | sort -u | head -20

# JWT / publishable key pattern
grep -r "eyJ[a-zA-Z0-9_-]\{20,\}\|sk-[a-zA-Z0-9]\{20,\}\|pk_\|sb_publishable" \
  "$TARGET" -h --include="*.ts" --include="*.sh" --include="*.json" 2>/dev/null | head -10
```

**2c. Outbound 網路呼叫**
```bash
grep -r "fetch(\|axios\.\|curl \|wget \|http\.request\|urllib\.request" \
  "$TARGET" --include="*.ts" --include="*.js" --include="*.sh" --include="*.py" \
  -l 2>/dev/null
```

**2d. 寫入 HOME 之外的隱藏目錄**
```bash
grep -r '~\/\.[a-zA-Z]\|HOME\/\.' \
  "$TARGET" --include="*.sh" --include="*.ts" -h 2>/dev/null | \
  grep -v "node_modules\|#" | sort -u | head -20
```

**2e. Telemetry gate 邏輯驗證**
```bash
# 找 "off" 關閉條件的真實邏輯
grep -n "off\|telemetry\|_TEL" "$TARGET/scripts/resolvers/preamble.ts" 2>/dev/null | head -30
# 確認 local write 是否在 gate 內部還是外部
```

### Step 3：風險矩陣評估

根據以上掃描，輸出下表：

| 項目 | 發現 | 風險等級 | 建議 |
|------|------|---------|------|
| 本地資料收集 | ？ | 🟡/🟢/🔴 | ？ |
| 遠端上傳 | ？ | 🟡/🟢/🔴 | ？ |
| 硬寫 API key | ？ | 🟡/🟢/🔴 | ？ |
| HOME 外寫入 | ？ | 🟡/🟢/🔴 | ？ |
| Telemetry gate 有效 | ？ | 🟡/🟢/🔴 | ？ |
| 混淆 / minified code | ？ | 🟡/🟢/🔴 | ？ |

**風險等級**：🟢 無問題 ｜ 🟡 需注意 ｜ 🔴 建議不裝

### Step 4：安全安裝程序（如果決定裝）

1. **先複製，再設 off**（不要用官方 installer 直接跑）：
   ```bash
   cp -r /tmp/_audit_target ~/.claude/skills/<tool-name>
   # 立刻設 telemetry=off
   ~/.claude/skills/<tool-name>/bin/<tool>-config set telemetry off 2>/dev/null
   # 或寫 config 檔
   echo '{"telemetry":"off"}' > ~/.<tool-name>/config.json
   ```

2. **block 已知的 telemetry endpoint**（需要 sudo）：
   ```bash
   # 把 Step 2b 找到的域名加進去
   echo "127.0.0.1 <found-domain>" | sudo tee -a /etc/hosts
   ```

3. **驗證 telemetry 真的關了**：
   ```bash
   # 跑一次工具，然後確認沒有產生 analytics 檔案
   ls ~/.<tool-name>/analytics/ 2>/dev/null || echo "no analytics dir - good"
   ```

4. **監控 outbound**（長期）：
   - macOS: `sudo lsof -i -n | grep <tool-process>` 
   - 或用 Little Snitch / LuLu 設規則

---

## 對本機已安裝工具的快速掃描

```bash
# 掃描所有 ~/.claude/skills/ 下的工具
for skill in ~/.claude/skills/*/; do
  echo "=== $(basename $skill) ==="
  grep -r "telemetry\|supabase\|analytics" "$skill" \
    --include="*.ts" --include="*.sh" -l 2>/dev/null | head -3
done

# 掃描所有 .jsonl（analytics 殘留）
find ~ -name "*.jsonl" \
  -not -path "*/.claude/projects/*" \
  -not -path "*/.gvm/*" \
  -not -path "*/node_modules/*" \
  2>/dev/null
```
