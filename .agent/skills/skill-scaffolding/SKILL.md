---
name: skill-scaffolding
description: 快速建立並啟用新的 Agent Runtime Skill（服務工具）的標準化流程與範本。
---

# Skill Scaffolding — 快速新增 Agent Skill 指南

> 本技能協助 Agent 為服務 **快速建立、註冊並啟用** 新的 Runtime Skill（Agent 可呼叫的工具）。

## 適用時機 (When to Use)

- 使用者要求「新增一個 Skill」、「加一個工具」或「讓 Agent 能做 X」
- 串接新的 Service 到 Agent 工具鏈
- 擴展 Agent 分析能力（新的 data source、API、計算方法）

---

## ⚠️ Skill 分類原則 (Categorization)

本專案有 **兩類 Skill**，存放位置與用途不同：

| 類別 | 存放位置 | 用途 | 範例 |
|------|----------|------|------|
| **Runtime Skill (服務框架)** | `src/agents/skills/<name>/` | Agent 在運行時可呼叫的工具 (MCP Tool) | `search_web`, `get_market_data`, `get_portfolio` |
| **Agent Dev Skill (開發輔助)** | `.agent/skills/<name>/` | 指導 Agent 開發時遵循的規範與最佳實踐 | `postgres-raw-sql`, `skill-scaffolding`, `wiki-maintainer` |

### Agent Dev Skills 進一步分為：

| 子類 | 說明 | 範例 |
|------|------|------|
| **框架通用 (Framework)** | 可跨專案使用的通用規範 | `postgres-raw-sql`, `agent-secret-redaction`, `environment-doctor`, `skill-scaffolding` |
| **專案專屬 (Project-specific)** | 僅適用於本 investment-advisor 專案 | `macro-data-ingestion`, `portfolio-data-verification`, `swarm-orchestration-pattern`, `troubleshooting-isolated-mcp` |

---

## Pre-flight 檢查

在建立新 Skill 前，Agent 必須先執行以下檢查：

1. **避免重複**: 檢查 `src/agents/skills/` 下是否已有同名或功能相似的 Skill
2. **確認 Service 層存在**: 新 Skill 通常整合一個 `Service` — 確認 `src/services/` 或 `src/repositories/` 下有對應實作
3. **確認 User 需求**: 如果需求不明確（例如 input/output schema），向使用者釐清

---

## Step 1: 建立目錄結構

```bash
mkdir -p src/agents/skills/<skill_name>
```

每個 Runtime Skill 目錄必須包含：

```
src/agents/skills/<skill_name>/
├── metadata.json    # Layer 1: 輕量發現 (必要)
├── SKILL.md         # Layer 2+3: 完整定義 (必要)
└── impl.py          # Layer 4: 執行實作 (必要 - 用於熱插拔自動發現)
```

---

## Step 2: 撰寫 `metadata.json`

```json
{
  "name": "<skill_name>",
  "version": "1.0.0",
  "description": "短描述：這個 Skill 做什麼",
  "category": "<category>",
  "tier": "<fast|smart|advanced>",
  "input_schema": {
    "type": "object",
    "properties": {
      "param1": {"type": "string", "description": "參數說明"}
    },
    "required": ["param1"]
  },
  "output_schema": {
    "type": "string",
    "description": "回傳值說明"
  },
  "platform": ["linux", "darwin"],
  "tags": ["tag1", "tag2"]
}
```

### 欄位規範

| 欄位 | 必要 | 說明 |
|------|------|------|
| `name` | ✅ | 必須與目錄名一致，使用 snake_case |
| `version` | ✅ | SemVer 格式 |
| `description` | ✅ | 簡短描述，會顯示在 Agent System Prompt |
| `category` | ✅ | 功能分類: `research`, `market`, `portfolio`, `analysis`, `notification` 等 |
| `tier` | ✅ | 執行層級: `fast`=即時, `smart`=需推理, `advanced`=複雜分析 |
| `input_schema` | ✅ | JSON Schema 定義輸入參數 |
| `output_schema` | ✅ | JSON Schema 定義輸出格式 |
| `platform` | ⬜ | 預設 `["linux", "darwin"]` |
| `tags` | ⬜ | 用於過濾與搜尋的標籤 |

---

## Step 3: 撰寫 `SKILL.md`

```markdown
---
name: <skill_name>
description: 與 metadata.json 一致的描述
metadata:
  openclaw:
    os: [linux, darwin]
---
## Instruction
清楚說明 Agent 何時該使用此工具、如何使用。

### Examples
User: <使用者可能的問句>
Assistant: <tool_code><skill_name>(param1="value")</tool_code>
```

### 撰寫規範

- `name` 必須與 `metadata.json` 中的 `name` **完全一致**
- Instruction 要具體，包含邊界條件與限制
- 至少提供 **2 個 Examples**

---

## Step 4: 撰寫 `impl.py` (實作層)

為了支援 **「熱插拔」** 與 **「第三方下載即用」**，嚴格禁止修改 `src/agents/skills/registry.py`。所有的程式碼實作必須放在該 Skill 目錄下的 `impl.py` 中。

```python
import logging
import functools
from src.utils.logger import setup_logger

logger = setup_logger("<skill_name>")

def <skill_name>(user_id: str, **kwargs) -> str:
    """
    Skill 進入點函數。
    名稱必須與目錄名一致。
    第一個參數必須是 user_id。
    """
    try:
        # ⚠️ 延遲載入 Service 避免循環依賴
        from src.services.<service_module> import <ServiceClass>
        
        svc = <ServiceClass>(user_id=user_id)
        # 執行逻辑...
        return "執行結果"
    except Exception as e:
        logger.error(f"Skill <skill_name> failed: {e}")
        return f"Error: {e}"
```

### 實作規範 (Implementation Rules)

- ⚠️ **禁止修改 `registry.py`**: 系統會自動掃描目錄並掛載 `impl.py`。
- ⚠️ **函數命名**: 必須與資料夾名稱完全一致。
- ⚠️ **參數注入**: 第一個參數固定為 `user_id: str`。
- ⚠️ **資通安全**: 網路下載的 Skill 必須通過 `MCPBackgroundCheckService` 靜態掃描，否則會被攔截。
- ⚠️ **循環依賴**: 永遠在函數內部 import `src.services`。

---

## Step 5: 驗證

```bash
# 1. 確認 SkillLoader 能發現 (Layer 1)
python -c "
from src.agents.skills.skill_loader import SkillLoader
loader = SkillLoader()
meta = loader.discover_skills()
assert '<skill_name>' in meta, f'Not discovered! Found: {list(meta.keys())}'
print(f'✅ Layer 1: {meta[\"<skill_name>\"]}')"

# 2. 確認完整載入 (Layer 2+3)
python -c "
from src.agents.skills.skill_loader import SkillLoader
loader = SkillLoader()
skills = loader.load_skills()
assert '<skill_name>' in skills, f'Not loaded! Found: {list(skills.keys())}'
print(f'✅ Layer 2+3: {skills[\"<skill_name>\"].description}')"

# 3. 確認 Registry 有註冊
python -c "
from src.agents.skills.registry import get_default_registry
reg = get_default_registry()
reg._ensure_builtins()
assert reg.has('<skill_name>'), 'Not registered!'
print('✅ Registry: registered')"

# 4. 執行測試
python -m pytest tests/ --tb=short
```

---

## Step 6: 寫測試

在 `tests/` 中新增測試，至少涵蓋：

1. **SkillLoader 發現**: `discover_skills()` 結果包含新 Skill
2. **SkillLoader 載入**: `load_skills()` 結果包含新 Skill 且 schema 正確
3. **Implementation 正常**: mock Service 層，驗證函式回傳
4. **Implementation 失敗處理**: mock Service 拋出異常，驗證回傳 error string

---

## Checklist

- [ ] `src/agents/skills/<name>/metadata.json` 已建立且欄位完整
- [ ] `src/agents/skills/<name>/SKILL.md` 已建立且有 Examples
- [ ] `src/agents/skills/<name>/impl.py` 已建立且函數命名正確
- [ ] `SkillLoader.discover_skills()` 可發現
- [ ] `SkillLoader.load_skills()` 可載入
- [ ] 測試已寫且通過
- [ ] `python -m pytest tests/ --tb=short` 零迴歸
