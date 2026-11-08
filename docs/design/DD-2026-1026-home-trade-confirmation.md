# DD-2026-1026 首頁的交易與再平衡按鈕要先確認
> 一句話：首頁「執行交易」與「執行再平衡」按一下就送出，沒有二次確認，而且 `AUTH_MODE=none` 時不用登入；提案送出前顯示確認對話框，並一律要求再輸入標的代號；另外「執行交易」目前路徑錯誤會 404，修路徑時必須一併加確認。

**狀態**：提案，等創辦人核可；本 PR 不改任何程式
**複核**：2026-11-08 對照最新 main 逐項重跑第 4 節指令，提案仍成立。行號會漂移，已改成可 grep 的錨點。唯一實質過時處是第 2 節的模式分支，已改寫。
**風險級**：R3，由創辦人核可並執行。這兩個按鈕通往交易紀錄與哨兵觸發，是動錢路徑的入口；前端本身屬 R1，但它通往的後端是 R3。
**上游**：無 issue；來自 2026-10-26 的首頁盤點

## 1 問題：舊做法是什麼、錯在哪
- 「執行交易」：`frontend/src/components/dashboard/Terminal.tsx` 的按鈕直接呼叫 `handleExecute`；它只檢查標的與數量有填，就 `POST /transactions`，body 是標的、方向、數量、價格 0、手續費 0。沒有確認，沒有顯示模式，demo 或 real。
- 路徑對不上：`apiClient` 的 `getUrl`，在 `frontend/src/lib/api-client.ts`，把 `/transactions` 補成 `/api/transactions`，但後端只有 `/api/v1/transactions`，見 `src/api/v1/router.py` 的 `prefix="/transactions"`；`/api/transactions` 沒有路由。所以現況這顆按鈕按下去會得到 404，交易其實送不出去。同一個專案的 `frontend/src/app/data/page.tsx` 用的是 `/api/v1/transactions`。這表示確認機制必須在修正路徑之前或同一個 PR 內到位，否則修一個路徑 bug 就會讓一個沒有任何保護的入口生效。
- 這個端點實際做的事，指修正路徑後會發生的事：`src/api/v1/endpoints/transactions.py` 的 `add_transaction` 呼叫 `TransactionService.add_manual_trade`，只寫一筆交易紀錄並更新每日快照；這條路徑沒有呼叫券商。介面文字卻寫「市價單將繼承所有 Sentinel 監控守則」，Terminal.tsx 的按鈕說明文字，讓人以為在下單。兩種誤解都有代價：以為下了單其實沒下，或以為只是記帳其實價格 0 的紀錄汙染帳本與績效計算。這是 [推論]，依據是上述呼叫鏈沒有券商呼叫；請在審查時用第 4 節的指令確認。
- 「執行再平衡」：`frontend/src/features/portfolio/components/PortfolioStats.tsx` 的按鈕呼叫 `onRebalance`，由 `frontend/src/app/page.tsx` 的 `handleRebalance` 執行，經 `frontend/src/features/portfolio/infra/PortfolioRepository.ts` 送出 `POST /api/v1/dashboard/rebalance`。後端 `src/api/v1/endpoints/dashboard.py` 的 `trigger_rebalance` 排進 `trigger_portfolio_rebalance`，用 `force=True` 跑一次哨兵全量檢查（`src/infrastructure/tasks.py`）。哨兵會啟動議會，花 LLM 費用；後續是否下單由 `ai_trading_enabled` 與風控閘門把關 [推論，依據是哨兵持有議會服務，下單路徑在議會之後]。後端限流是每 5 分鐘一次，這只擋連點，擋不了誤按。
- 沒有登入門檻：`src/api/middleware/local_auth.py` 的預設 `AUTH_MODE=none`，不要求任何驗證。儀表板只在 `127.0.0.1:8088` 對外開放，見 `docker-compose.prod.yml` 的 gateway 埠；ngrok 指向的是另一個只轉 `/webhook/` 與 `/callback/` 的虛擬主機，見 `infra/nginx/nginx.conf` 的 8080 區塊，所以儀表板不經由隧道公開。能按到按鈕的是能連到本機 8088 的人，例如本機瀏覽器或 SSH 轉發。[推論] 依據是上述兩份設定，不是實測外部連線。
- 影響：誤按或被他人觸發都沒有任何摩擦。

## 2 決定：新做法，正本在哪
- 確認對話框是唯一正本，做成共用元件，兩個按鈕都經過它，不各寫一份。
- 交易表單送出前顯示：標的、方向、數量、價格，市價則標明、模式，demo 或 real、以及這個動作會做什麼，是「只記帳」還是「送到券商」。
- 一律要求再輸入一次標的代號，與表單的標的一致才能按確認，不分模式：demo 現在不是可用的安全模式，不能因為它而放鬆確認。模式只顯示在對話框，不決定要不要輸入。若日後 token 取得 demo 權限，再由新 DD 決定是否放鬆。
- 再平衡的對話框說明會發生什麼：啟動一次哨兵檢查、可能產生議會與 LLM 費用、是否可能下單取決於交易總開關目前的值。
- 模式的讀法：鍵名是 `etoro_mode`，schema 預設 `demo`，選項 demo 或 real；但目前 token 沒有 demo 權限，選 demo 會讓所有券商呼叫失敗，schema 說明與 `AGENTS.md` 都這樣寫，查法是 `git grep -n "無 demo 權限" -- config/settings_schema.yaml`，所以 demo 不是可用的安全模式，見 `config/settings_schema.yaml` 的 `key: etoro_mode`。讀取統一走 `src/services/broker_factory.py` 的 `effective_trading_mode`：缺值當 demo；讀取例外當 real；環境變數 `TRADING_MODE=paper` 會強制 demo。前端和 `src/api` 目前都沒有暴露這個值，實作需要新增一個唯讀端點回傳 `effective_trading_mode` 的結果，不要讓前端自己讀設定。
- 端點失敗或回傳未知值時，對話框顯示「模式未知」，確認流程不變。與 `effective_trading_mode` 讀取例外當 real 的關門預設一致。
- 後端不改。確認只是前端的摩擦；真正的保護仍是風控與總開關。AUTH_MODE 的議題另案處理。
- 介面文字同步修正：Terminal.tsx 的按鈕說明要與端點實際行為一致。
- 既有確認寫法：`/universe` 的主動輪動、`/data` 的刪除交易已各自用瀏覽器內建 `window.confirm`，查法是 `git grep -n "confirm(" -- frontend/src`。共用元件要明說是否取代這兩處，避免兩套確認並存；本提案先只要求首頁兩個按鈕經過共用元件。
- 不做的事：不改 `POST /transactions` 的語意；不改限流；不改 `AUTH_MODE` 預設。

## 3 風險與回滾
- 風險：摩擦增加，緊急時多一步。這是刻意的取捨。
- 回滾：還原該 commit，沒有資料變更。

## 4 可重跑的證明
現況沒有確認步驟：
```bash
git grep -n "handleExecute\|handleRebalance" -- frontend/src
git grep -n -i "confirm" -- frontend/src/components/dashboard/Terminal.tsx frontend/src/app/page.tsx
```
第一條列出直接呼叫 API 的處理函式；第二條現況無輸出，改完要有輸出。

路徑對不上，現況 `/api/transactions` 沒有路由，`/api/v1/transactions` 有：
```bash
DB_URL=sqlite:///:memory: DB_TYPE=sqlite .venv/bin/python - <<'PY'
from services.mcp_server.src.app import app
paths = [r.path for r in app.routes if hasattr(r, 'path')]
print('/api/transactions', '/api/transactions' in paths)
print('/api/v1/transactions', '/api/v1/transactions' in paths)
PY
```
現況輸出 False 與 True。

確認 `/transactions` 不呼叫券商，只讀檔：
```bash
git grep -n -A25 "def add_manual_trade" -- src/services/transaction_service.py | grep -i "broker\|etoro\|AutomatedTrading"
git grep -n -A25 "async def add_transaction" -- src/api/v1/endpoints/transactions.py | grep -i "broker\|etoro\|AutomatedTrading"
```
兩條現況都無輸出，支持上面的 [推論]。注意不能對整個 `transaction_service.py` 搜尋，同檔的 `sync_broker_positions` 是另一條路徑。

行為層證明由實作 PR 補：
```bash
cd frontend && npx vitest run src/components/dashboard
```
測試要涵蓋：未確認不呼叫 API；任何模式代號不符都不能確認；模式讀不到時仍要求輸入代號。

## 已知殘留
- `AUTH_MODE=none` 時誰都能操作，這份 DD 只加摩擦，不加驗證。
- 路徑錯誤本身是另一個 bug，修法很小，但要和確認對話框一起上，不要單獨修。
- 首頁以外的入口，例如 `/adaptive` 頁的同類按鈕、`/api/v1/ticker-universe/rebalance`不在本 DD 範圍，實作時一併盤點。
- 「執行交易」是記帳還是下單的產品定位，需要創辦人決定；若只是記帳，介面應改名，不該叫「執行交易」。

## 驗收條件
- AC1：按下「執行交易」不會立刻呼叫 `POST /transactions`，要先出現確認對話框；反驗：拿掉對話框直接呼叫，「未確認不呼叫 API」的測試要失敗。
- AC2：對話框列出標的、方向、數量、模式，模式未知時顯示「未知」；反驗：移除任一欄位，對應的畫面測試要失敗。
- AC3：任何模式下，輸入的代號與標的不一致時確認鍵不能按；反驗：把比對拿掉，這個測試要失敗。
- AC4：模式讀不到時，畫面顯示「模式未知」且仍要求輸入代號；反驗：讓設定讀取失敗，檢查上述；若改成「模式未知就免輸入」，這個測試要失敗。
- AC5：「執行再平衡」同樣要經過確認，且共用同一個元件；反驗：`git grep -n "ConfirmDialog" -- frontend/src` 要同時出現在兩個按鈕的來源檔，其中一個拿掉時測試要失敗。
- AC6：只修路徑的 PR 不能通過；反驗：把 Terminal 的路徑修成 `/api/v1/transactions` 但不加確認，AC1 的測試要失敗。
