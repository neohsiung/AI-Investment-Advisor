# DD-2026-1026 交易總開關缺值時的行為要一致，而且預設是關
> 一句話：`ai_trading_enabled` 缺值時，下單服務現在當成啟用，風控與 schema 當成關閉；提案把下單服務改成缺值就擋，並讓安裝時的種子真的寫得進去。

**狀態**：提案，等創辦人核可；本 PR 不改任何程式
**複核**：2026-11-08 對照最新 main 逐項重跑第 4 節指令，提案仍成立。行號會漂移，已改成可 grep 的錨點。
**風險級**：R3，由創辦人核可並執行。改的是 `automated_trading_service.py`，屬動錢路徑，不開放給 agent 實作。
**上游**：無 issue；來自 2026-10-26 的開關盤點

## 1 問題：舊做法是什麼、錯在哪
- 下單服務對缺值的解讀是啟用。`src/services/automated_trading_service.py` 的 `# 1. Check if trading is enabled` 區塊：
  `ai_trading_enabled` 讀不到，就去看 `enable_etoro`、`enable_ibkr`；兩個也讀不到時，`trading_enabled` 被設成 `True`，註解寫著 `Default to enabled if no explicit setting present`。
- 風控對同一個缺值的解讀是關閉。`src/infrastructure/risk_manager.py` 的 `# 0. Global Check` 區塊，註解寫明 Fails CLOSED。缺值時改用 schema 預設，`config/settings_schema.yaml` 的 `ai_trading_enabled` 預設是 `false`，所以擋下。同一個 `automated_trading_service.py` 的基準停泊的入口用 `str(None)` 判斷，缺值也是擋。
- 同一個缺值，三個地方答案不同。下單服務是唯一會放行的一個。
- 目前不會因此下單：`risk_manager` 缺值時擋下，下單前要先過它。這份 DD 的目的是消除兩道開關對缺值判讀不一致，不是止血。
- 安裝時的種子救不了它。`install.sh` 的 `Seeding safe defaults` 段落意圖是資料庫沒有這一列就寫入 `false`，條件是 `svc.get_setting('ai_trading_enabled') is None`。但 `src/services/settings_service.py` 的 `get_setting` 在沒傳 default 時，用 `schema_default` 的 `False` 當 default 傳給 repo；列不存在時 repo 回傳這個 `False`，所以永遠不是 `None`，種子永遠被跳過，資料庫沒有那一列。
- 影響：全新或只種了一部分的資料庫，這一列不存在，而下單服務會把它當啟用。AGENTS.md 的不變量第 4 條要求缺值就跳過並標記，不能用看似合理的預設。
- 已在隔離環境實跑確認種子被跳過，用 sqlite 暫存檔與空資料庫，不連正式環境：
  ```
  get_setting on empty db -> False
  seed SKIPPED
  rows in settings for key: 0
  ```
  審查時請在自己的隔離環境重跑第 4 節的指令。
- 除了「列不存在」，還有第二條路會走進這個分支：`src/repositories/settings_repository.py` 的 `get` 在查詢發生任何例外時都回傳 default，也就是 `None`。所以正式環境即使有這一列，只要讀取那一刻資料庫連線或查詢出錯，下單服務就會把它當成缺值，進而當成啟用。
- 正式環境目前有這一列，`AGENTS.md` 說明正式值由操作者明確設定，所以「列不存在」只會在全新安裝與災後重建發生；但讀取例外那條路隨時可能發生，不能當成只影響新環境。[推論] 依據：該列存在且讀取成功時 `trading_enabled` 不會是 `None`，不進入上述缺值分支。查證方式見第 4 節。

## 2 決定：新做法，正本在哪
- 正本：`config/settings_schema.yaml` 的 `ai_trading_enabled`，預設 `false`。所有讀取點缺值時都以它為準。
- 提案一，下單服務：`automated_trading_service.py` 的 `# 1. Check if trading is enabled` 區塊改成缺值就擋。刪掉「兩者都缺就啟用」分支；缺值時回傳 `{"status": "blocked", "reason": ...}`，並在 reason 與 log 寫明是「設定缺值」，不是「使用者關閉」，讓人看得出差別。與 `risk_manager.py` 的 fail-closed 一致。
- 提案二，種子：二選一，由創辦人裁決。
  - a. 檢查資料庫原始值：在 repo 層加一個只看資料列、不套 schema 預設的讀法，種子用它判斷「這一列是否存在」。
  - b. 無條件 upsert 成 `false`，但只在全新安裝時執行，`install.sh` 本來就只在首次安裝流程裡跑，才不會覆蓋已設定的值。
  建議 a：不會誤蓋。b 較簡單，但依賴「只在全新安裝跑」這個前提。
- 不做的事：不改正式環境的值；不動 `enable_etoro`、`enable_ibkr` 的語意；不改風控；不動 `tradable_capital_pct`。
- 部署前提：實作 PR 要補測試，且 `tests/invariants` 要通過；缺值行為改變後，既有測試若依賴「缺值就啟用」要明列並改成明確設定。

## 3 風險與回滾
- 風險：若正式環境某個使用者其實沒有這一列、靠「缺值就啟用」在運作，改完後會停止下單。實作前先查每個使用者是否都有這一列，查詢見第 4 節。
- 另一面：改完後，讀取例外也會讓下單暫停，而不是放行。這是刻意的取捨：暫停的代價是錯過一次機會，放行的代價是在不確定開關狀態下動錢。
- 回滾：還原該 commit 即可；正式環境不需要任何資料變更。

## 4 可重跑的證明
下單服務缺值時啟用，現況有輸出，改完應無輸出：
```bash
git grep -n "Default to enabled if no explicit setting present" -- src/services/automated_trading_service.py
```
行為層的證明由實作 PR 補：三個開關都缺值時呼叫 `evaluate_and_execute_trade`，現況會繼續往風險閘門走，改完要回 blocked。測試的建構方式參考 `tests/unit/services/test_automated_trading_service.py`。

種子被跳過，在隔離環境重跑，不連正式資料庫：
```bash
SC=$(mktemp -d); DB_URL=sqlite:///$SC/seed.db DB_TYPE=sqlite .venv/bin/python - <<'PY'
from src.data.database import get_db_engine, init_db
from src.data.models import Setting
from sqlalchemy.orm import sessionmaker
eng = get_db_engine(); init_db(engine=eng, force=True)
from src.services.settings_service import SettingsService
svc = SettingsService(user_id="probe-user")
print("get_setting ->", repr(svc.get_setting("ai_trading_enabled")))
print("rows ->", sessionmaker(bind=eng)().query(Setting).filter_by(key="ai_trading_enabled").count())
PY
```
現況輸出 `False` 與 `0`：不是 `None`，也沒有資料列。

正式環境是否每個使用者都有這一列，用唯讀查詢，由創辦人執行：
```sql
SELECT u.id FROM users u LEFT JOIN settings s ON s.user_id = u.id AND s.key = 'ai_trading_enabled' WHERE s.key IS NULL;
```
應無資料列；有的話先補值再部署。

## 已知殘留
- `settings_repository.get` 在例外時回傳 default，讓所有缺值判斷同時承擔了讀取失敗的情況。建議另案評估讓決策路徑的讀取失敗明確 raise，不在本 DD 範圍。
- 其他設定鍵可能有同樣的「讀取點各自解讀缺值」問題，本 DD 只處理 `ai_trading_enabled`。
- 基準停泊已經缺值就擋，但靠的是 `str(None)` 的巧合，不是明確判斷；實作時順手改成明確判斷。
- `webhook_service.py` 的 `/health` 指令用 `ss.get_setting("ai_trading_enabled", "true")` 顯示狀態，缺值時顯示「啟用」，與擋下的實際行為相反；只影響顯示，實作時順手改成缺值顯示「未設定」。查法：`git grep -n 'get_setting("ai_trading_enabled", "true")' -- src/services/webhook_service.py`。
- 種子方案 a 需要在 repo 層加新方法，要補 repo 層測試。

## 驗收條件
- AC1：下單服務在 `ai_trading_enabled`、`enable_etoro`、`enable_ibkr` 全部缺值時回傳 blocked，且 reason 標明是設定缺值；反驗：把「兩者都缺就啟用」的分支加回去，新增的缺值測試要失敗。
- AC2：下單服務、風控、基準停泊三處對缺值的結果一致，都擋；反驗：只改其中一處回到放行，跨三處的一致性測試要失敗。
- AC3：全新資料庫跑完 `install.sh` 的種子步驟後，`settings` 表有 `ai_trading_enabled` 這一列，值為 false；反驗：把種子的判斷改回 `svc.get_setting(...) is None`，重跑第 4 節的隔離腳本，資料列數要是 0，驗收腳本要失敗。
- AC4：種子不會覆蓋已存在的值；反驗：先寫入 true，再跑種子，值仍是 true；把種子改成無條件覆蓋，這個檢查要失敗。
- AC5：既有行為沒壞；反驗：`.venv/bin/python -m pytest tests/invariants tests/unit/services/test_automated_trading_service.py tests/unit/infrastructure/test_infra_risk_manager.py -q` 全綠。
