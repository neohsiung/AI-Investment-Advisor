# 【P】數據庫遷移指南 — 保護現有數據

⚠️ **重要**：本指南適用於 Docker 環境中的 PostgreSQL 用戶（如 supermfb@gmail.com）

## 概述

遷移文件已準備好，但尚未應用到生產數據庫：
- ✅ `alembic/versions/a02089c0968b_add_user_custom_prompts_table.py` — 待應用
- ⚠️ 應用此遷移 **不會刪除或修改現有數據**

## 安全檢查清單

在應用任何遷移前：

- [ ] 已備份 PostgreSQL 數據庫（可選但推薦）
- [ ] 已確認 Docker 容器中 `supermfb@gmail.com` 用戶的數據完整性
- [ ] 已在測試環境驗證遷移（可選）

## 方式 1：自動遷移（推薦 - 零代碼）

此方式需要在 Docker 容器啟動時自動運行 Alembic 遷移：

### 編輯 `docker-compose.yml`

在 `api` 或 `scheduler` 服務中添加啟動前鉤子：

```yaml
services:
  api:
    build: .
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@postgres:5432/advisor
    entrypoint: /bin/bash -c "alembic upgrade head && exec gunicorn ..."
    # ... 其他配置
```

### 執行

```bash
docker compose up --build
# Alembic 會自動應用所有待決遷移
```

## 方式 2：手動遷移（最安全 - 有確認步驟）

如果你想要完全控制：

### 1. 進入 API 容器

```bash
docker compose exec api bash
```

### 2. 檢查當前遷移狀態

```bash
alembic current
alembic history
```

### 3. 查看將應用的遷移（不執行）

```bash
alembic upgrade --sql head
# 這會打印 SQL，讓你看到會發生什麼
```

### 4. 應用遷移

```bash
alembic upgrade head
# 應用所有待決遷移到最新版本
```

### 5. 驗證

```bash
alembic current
# 應該顯示：'a02089c0968b'（或更新的版本）
```

## 方式 3：跳過遷移（目前的狀態 - 完全安全）

**系統已修改為在表不存在時優雅地跳過** — 你可以繼續正常運作：

- ✅ 代碼會自動處理缺失的 `user_custom_prompts` 表
- ✅ 不會破壞任何現有工作流
- ✅ 以後可以隨時應用遷移

這是目前**推薦的方式**，直到你準備好應用遷移。

## 回滾（如果出問題）

如果遷移導致問題，立即回滾：

```bash
docker compose exec api alembic downgrade -1
# 回滾最後一個遷移
```

## 故障排除

### 「表已存在」錯誤

如果看到 "table already exists"：

```bash
alembic stamp a02089c0968b
# 告訴 Alembic 表已存在（無需再創建）
# 然後升級到下一個版本
alembic upgrade head
```

### 其他數據庫錯誤

始終檢查數據庫連接：

```bash
docker compose exec api psql -U postgres -h postgres -d advisor -c "SELECT version();"
```

## 相關文件

- 遷移腳本：`alembic/versions/a02089c0968b_add_user_custom_prompts_table.py`
- 異常處理：`src/agents/base_agent.py:278-285`（已改為debug級別）
- 配置：`.env` 中的 `DB_TYPE`, `DB_USER`, `DB_PASS`

## 支持

有問題？檢查：

1. Docker 日誌：`docker compose logs api`
2. Alembic 文檔：https://alembic.sqlalchemy.org/
3. PostgreSQL 日誌：`docker compose logs postgres`
