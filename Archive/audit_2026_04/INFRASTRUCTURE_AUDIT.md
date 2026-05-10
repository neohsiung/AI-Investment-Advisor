# 📋 PAD 基礎設施審計 (2026-04-28)

## 1️⃣ 資料庫狀況

### ✅ 本地 SQLite (可用)
| DB 檔案 | 位置 | 表數量 | 狀態 | 用途 |
|--------|------|--------|------|------|
| `portfolio.db` | `data/` | 11+ | ✓ 有數據 | 投資組合、LLM 日誌、設定 |
| `memory.db` | `data/` | 3 FTS | ✓ 活躍 | 記憶體儲存 + 全文搜尋 |
| `cache.db` | `data/` | 1 | ✓ 活躍 | 回應快取 |
| 其他 DB | `data/` | 0 | ✗ 空白 | 無用 |

### ❌ Docker PostgreSQL (未初始化)
- 容器: `advisor_prod_db` (運行中)
- DB: `advisor_prod` **不存在**
- 原因: 上次初始化失敗 / 未執行 init.sql

### 📦 初始化腳本
| 檔案 | 位置 | 行數 | 描述 |
|-----|------|------|------|
| `init.sql` | `deployment/postgres/` | 89 | 交易、持倉、現金流、報告表 |
| `init_memory_tables.sql` | `scripts/` | 30 | 報告記憶體 + 任務執行日誌 |

### 🔄 Alembic 遷移 (15+ 版本)
- **基礎**: `879480c2b31c_baseline_v4_schema.py`
- **企業**: `004_add_enterprise_tables.py`
- **報告系統**: `003_add_report_jobs_tables.py`
- **LLM 多供應商**: `d3f8a1b2c4e5_add_llm_multi_provider_tables.py`
- **成本追蹤**: `gamma_strategy_cost_tracking.py`

---

## 2️⃣ 前端 UI 狀況

### ✅ Next.js 架構 (完整)
```
frontend/
├── src/
│   ├── app/           # 頁面路由
│   │   ├── page.tsx   (首頁)
│   │   ├── auth/      (登入 / 回調)
│   │   ├── settings/  (設定 ⚙️)
│   │   ├── chat/      (聊天對話 💬)
│   │   ├── reports/   (報告 📊)
│   │   ├── data/      (數據上傳 📁)
│   │   ├── performance/ (績效分析 📈)
│   │   └── intelligence/ (智能分析 🧠)
│   ├── features/      # 功能模塊
│   │   ├── agents/    (Agent 狀態)
│   │   ├── llm-settings/ (LLM 設定面板 + 多頁籤)
│   │   │   ├── ModelsTab
│   │   │   ├── ProvidersTab
│   │   │   ├── TierBindingsTab
│   │   │   └── AgentOverridesTab
│   │   └── ...
│   └── context/       # 全域狀態
│       ├── ThemeContext (深色/淺色)
│       ├── WebSocketContext (實時更新)
│       └── SidebarContext (側邊欄)
├── package.json       (Node 依賴)
├── next.config.ts     (Next.js 設定)
└── Dockerfile         (容器化)
```

### 📄 規則文件
- **AGENTS.md**: Next.js breaking changes 警告
- **CLAUDE.md**: Claude 使用指南

---

## 3️⃣ .agent/rules 組織架構

### 📌 規則模塊化 (已建立)
```
.agent/
├── rules/
│   ├── git-commit-format.md        (Git 提交格式)
│   ├── engineering-standards.md    (工程標準)
│   ├── observability-standards.md  (可觀測性)
│   ├── documentation-standards.md  (文檔標準)
│   └── reflection-standards.md     (反思標準)
├── skills/                         (技能庫)
└── workflows/                      (工作流程)
```

---

## 4️⃣ 帳號狀況

### ❌ supermfb@gmail.com
- **Email**: supermfb@gmail.com
- **User ID**: `90693c07-6177-42df-97d9-915f3ce7c573`
- **現存資料**: **無**
- **需要**:
  1. 建立 PostgreSQL 帳號
  2. 初始化投資組合
  3. 插入測試資料 (可選)

---

## 5️⃣ 下一步行動清單

### Phase A: DB 復興 (Immediate)
- [ ] 執行 PostgreSQL 初始化
  ```bash
  docker exec advisor_prod_db psql -U postgres -f /deployment/postgres/init.sql
  ```
- [ ] 運行 Alembic 遷移
  ```bash
  alembic upgrade head
  ```
- [ ] 為 supermfb@gmail.com 建立使用者 + 投資組合

### Phase B: 前端 UI 整備
- [ ] 驗證 Next.js 前端構建 ✓ (已存在)
- [ ] 確認 WebSocket 連線至後端
- [ ] 測試登入流程 (auth/callback)
- [ ] 驗證 LLM 設定頁面 (多供應商、模型選擇)

### Phase C: 資料流測試
- [ ] 前端 → API 提交投資組合數據
- [ ] API → PostgreSQL 儲存
- [ ] PostgreSQL → 報告生成
- [ ] 報告 → 前端儀表板顯示

---

## 📊 檔案結構整理建議

```
.agent/
├── rules/              # ✓ 已存在 (5 個標準)
│   ├── README.md       # 指引
│   ├── git-commit-format.md
│   ├── engineering-standards.md
│   ├── observability-standards.md
│   ├── documentation-standards.md
│   └── reflection-standards.md
├── skills/             # ✓ 已存在 (技能模塊)
├── workflows/          # ✓ 已存在 (工作流)
└── organization.md     # 新增: 檔案組織原則
```

---

## 🎯 關鍵發現

1. **DB 分離**: SQLite (本地) + PostgreSQL (Docker) 需要統一策略
2. **UI 完整**: 前端架構已就位，缺乏後端資料連結
3. **規則完善**: .agent/rules 模塊化程度高 ✓
4. **帳號空白**: supermfb@gmail.com 需要完整初始化

**建議優先級**:
1. 初始化 PostgreSQL (恢復 Phase 1 遷移)
2. 建立 supermfb@gmail.com 帳號 + 樣本資料
3. 連接前端 UI 至後端 API
4. 驗證 WebSocket 實時更新
