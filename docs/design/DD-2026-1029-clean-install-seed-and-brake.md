# DD-2026-1029 — 乾淨安裝的交易煞車：種子寫入不會生效，兩道檢查對缺值判讀相反（提案，待人核可）
> 一句話：`install.sh` 與 `start.sh` 的 `ai_trading_enabled=false` 種子永遠被跳過，乾淨安裝靠 schema 預設值與第二道檢查擋單；兩處對「資料庫沒有這一列」的判讀相反。這份文件列出證據與兩種修法，由人決定。

**狀態**：提案（未實作；本文件不改任何程式或設定）
**風險級**：R3（`ai_trading_enabled` 屬動錢路徑；`automated_trading_service.py` 在 `.github/CODEOWNERS`；實作前需人核可加 ADR）
**上游**：合規審查附錄二 F3、F4、F5；M4 乾淨安裝（本 DD 是 M4 刻意不改的部分）

## 1 問題
- 種子永遠被跳過：`SettingsService.get_setting` 在資料庫沒有該列時回 schema 預設值 `False`，不是 `None`，所以 `install.sh`、`start.sh` 的 `if ... is None` 不成立，`save_settings_bulk` 不會執行。
  證據：`grep -n "ai_trading_enabled') is None" install.sh`、`grep -n "existing is None" start.sh`；`sed -n 100,120p src/services/settings_service.py`（回傳 `effective_default`）。
- 下單服務把「沒有這一列」當成啟用：`automated_trading_service.py` 先讀 repository（不套 schema 預設），讀到 `None` 時再看 `enable_etoro`、`enable_ibkr`，兩者也是 `None` 就設為 `True`。
  證據：`sed -n 371,381p src/services/automated_trading_service.py`。
- 乾淨安裝目前不會下真單，原因是第二道：風控在缺值時改用 schema 預設 `false`，`etoro_mode` 預設 `demo`，而 token 無 demo 權限。第一道開關（這裡）是開的，安全只靠第二道。
  證據：附錄二 F5 列的 `src/infrastructure/risk_manager.py:119-125`、`src/services/etoro_service.py:574`。以上是讀碼推論；實跑紀錄在附錄二 F 節（隔離環境）。

## 2 選項
- **A（建議）：種子改成檢查資料庫實際有沒有這一列。** `install.sh`、`start.sh` 的 python 片段改用 repository 的 `get`（不套預設）判斷，沒有才寫 `False`。不動 R3 檔，只動安裝腳本；缺點是下單服務那一道仍把缺值當啟用，只是不再有缺值的機會。
- **B：下單服務對缺值改為停用（fail-closed）。** 改 `automated_trading_service.py` 第 1 步，缺值視為 `False`。動 R3 檔，需 ADR；好處是兩道檢查判讀一致。

建議 A 先做（R2、可驗證），B 另案由人決定。

## 3 驗證（實作時）
- A：在隔離資料庫跑種子片段，之後 `select value from settings where key='ai_trading_enabled'` 有值且為 false；再跑一次不覆蓋人設的 true。
- B：單元測試「無此列、無 enable_etoro、無 enable_ibkr → 不下單」。

## 4 為什麼 M4 不處理
A 的種子片段在 `install.sh` 與 `start.sh` 各一份，且 `start.sh` 在 CODEOWNERS 的 R3 清單；M4 只改它的命名與流程。把煞車語意放進同一個 PR 會讓 reviewer 難以分辨哪些行為變了。

DERIVED: 腳本裡「值不存在」的判斷要用不套預設值的讀取路徑，否則預設值會讓種子永遠跳過。通用：是
