# 架構優化與後續擴充藍圖 (Phase 4 / Security & Architecture Optimization)

本文件匯總了確保 B2C SaaS 平台具備 **企業級資安 (Enterprise Security)** 與 **絕對穩定性 (Absolute Reliability)** 所必須解決的核心技術債與優化項目。

當進入後續開發階段時，請依照本文件的具體實作指示推進。

---

## 優化項目一：前端憑證安全極致化 (HttpOnly Cookie Migration)
**背景：** 目前 Sprint 4 (Phase 3) 採用的是前端 `localStorage` 來保存 Jwt Bearer Token。這在 B2C 環境下有潛在的 XSS（跨站腳本攻擊）風險。
**目標：** 徹底廢棄 `localStorage` 存放 Token 機制，改以伺服器端核發的 `HttpOnly Cookie` 進行自動認證。

### 具體開發步驟
1. **重啟 Next.js Route Handler**
   - 建立 `/frontend/src/app/auth/callback/route.ts`。
   - 捨棄原有的 `page.tsx` 轉址頁面。
   - 在 `route.ts` 內攔截 Google Callback 的 `access_token` 與 `refresh_token`，並使用 `next/headers` API 寫入 `HttpOnly` Cookie：
     ```typescript
     cookieStore.set("access_token", access_token, { httpOnly: true, sameSite: "lax", path: "/" });
     ```
2. **修改 FastAPI 驗證策略 (`src/api/v1/router.py`)**
   - 將 `OAuth2PasswordBearer` 與 `get_current_user_id` 修改為優先讀取 `request.cookies.get("access_token")`。
3. **改造前端 `apiClient.ts`**
   - 移除所有的 `localStorage.getItem('access_token')`。
   - 將所有的 `fetch` 請求自動帶上 `credentials: "include"` 參數，讓瀏覽器自動攜帶 Cookie。

---

## 優化項目二：WebSocket 認證守衛 (Realtime WSS Guard)
**背景：** 目前的 HTTP API 皆受限於 `@Depends(get_current_user_id)` 保護，但 Dashboard 用於推播「即時報價」與「Agent 執行狀態」的 WebSocket (WS/WSS) Endpoint (`/api/v1/dashboard/ws`) 尚未具備 JWT 解析機制，這可能導致旁門資料洩漏。
**目標：** 確保所有的 WebSocket 連線都經過嚴格的身份驗證。

### 具體開發步驟
1. **FastAPI WS Handler 升級**
   - 在 WebSocket 握手 (Handshake) 階段，擷取 Cookie 中的 Token，或是要求前端在 WS URL 參數帶上臨時的 `ticket`。
   - 若不符合，直接 `await websocket.close(code=status.WS_1008_POLICY_VIOLATION)`。
2. **前端 Hook 補強 (`useDashboardSocket.ts`)**
   - 確保在發起 `new WebSocket(url)` 之前，已經取得了有效的認證憑證。
   - 實作 WS 斷線後自動發起 `/refresh` 取得新 Cookie 再重連的機制。

---

## 優化項目三：使用者資料庫結構實體化 (Alembic Schema Freeze)
**背景：** 我們在 `user_repository.py` 加入了動態註冊白名單 Google 帳戶的邏輯。但在全新的伺服器上啟動時，若未執行 DDL 語法建立相對應的 Postgres 資料表 (`users` 以及 `user_identities`)，呼叫 Repo 會直接引發 500 錯誤。
**目標：** 導入 Alembic Migration 確保 Immutable State。

### 具體開發步驟
1. **實體模型定義**
   - 在 `src/infrastructure/database/models.py` 制式化定義 SQLAlchemy Models (繼承 `Base`)：
     ```python
     class User(Base):
         __tablename__ = "users"
         id = Column(String, primary_key=True)
         email = Column(String, unique=True, index=True)
     ```
2. **產出與應用遷移檔**
   - 運行 `alembic revision --autogenerate -m "Add B2C Auth Users"`。
   - 使 `start.sh --prod` 在啟動 `mcp_server` 之前，自動執行 `alembic upgrade head`，確保 Schema 一定是最新的狀態才接收 HTTP 請求。

---

## 優化項目四：LLM 扣款與預算隔離 (Agent Tiered Budgeting)
**背景：** 現在已擋下了非白名單用戶的登入存取。但進入系統後，所有觸發的 Groq/OpenRouter 請求依然是吃共同的環境變數 API Key 預算。
**目標：** 確保每一筆 Agent API Call 都有獨立算在個別使用者的 Token 使用紀錄中。

### 具體開發步驟
1. **注入 Request Context**
   - 在 FastAPI API Router 中取得 `user_id`。
   - 透過 `contextvars` 或是 `kwargs` 一路往下傳遞給 `CouncilTierRouter` 與 `LoggingProxy`。
2. **Dashboard 費用顯示**
   - 更新前端 Dashboard 的 `PortfolioStats.tsx`，加入【本月 LLM 消耗額度】與【剩餘預算】的視覺化指標。
   - 超出預算時，後端拋出 `402 Payment Required`，前端顯示「請升級付費方案」之攔截畫面。
