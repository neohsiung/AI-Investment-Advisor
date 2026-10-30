# DD-2026-1029 — 憲章凍結時，哪些訂單仍可下單；以及換手是怎麼被算的（提案，待人核可）
> 一句話：凍結閘門把會買進的策略（`cash_deployment`、`benchmark_parking` 等）當成安全控制放行，凍結後仍成交買單；另外 K3／K4 用的交易帳本混了券商同步匯入的列，其中一部分重複計算。這份文件列出事實、選項與要你決定的事，不改任何程式或 `mission.yaml`。

**狀態**：提案（未實作）
**風險級**：R3 提案（`strategy_registry.py`、`charter_state_service.py`、`mission_watchdog_service.py`、`etoro_service.py` 都在動錢或券商同步路徑；實作前需人核可加 ADR）。本文件本身是 R0。
**上游**：ADR-003 (5) 停機語意；2026-10-29 運作檢查；2026-10-30 Opus 唯讀研究，並由 scout 重跑查詢驗證
**已記錄的決定**（使用者，2026-10-30）：凍結期間 `benchmark_parking` 不能買，只留真正的出場。

## 1 凍結閘門：現在怎麼運作、哪裡和文字不一致

- 文字：ADR-003 (5) 寫「K1、K3、K4 違規時進入 frozen，停止新的非安全下單，不自動清倉；到 `clears_on` 後自動恢復，**之後** benchmark parking 才在預算內補回」。也就是說，文字的意思是凍結期間 benchmark parking 是停的。
- 實作（買單）：`order_allowed`（`src/services/charter_state_service.py`）對安全控制免讀狀態直接放行。`StrategyRegistry.is_safety_control`（`src/services/strategy_registry.py`）除了各策略合約，還有一份關鍵字清單，包含 `capital_rotation`、`rebalance_diversification`、`cash_deployment`、`stagnation_pruning`、`macro_volatility_hedge`、`benchmark_parking`。其中會買進的策略在凍結期間照常下單。
- 實作（賣單）：`order_allowed` 對所有賣單一律放行（docstring 寫明「賣單與安全控制免讀狀態」）。這是刻意設計，對應「不自動清倉」。但結果是非出場性質的賣單（例如 `rebalance_diversification`）也不受凍結約束，會增加換手。
- 證據（唯讀，可重跑）：

```bash
Q='docker exec advisor_prod_db psql -U postgres -d advisor_prod -c'
$Q "select action, coalesce(raw_data->>'strategy_name','(none)') strat, count(*), round(sum(amount)::numeric,2) usd from transactions where created_at > '2026-10-21 10:10:00+00' and source_file='eToro' and entry_category='trade' group by 1,2 order by 1,2"
$Q "select * from charter_state"
```

  查到的類別（數字隨時間變，以指令為準）：凍結後有 `cash_deployment` 買單、`benchmark_parking` 買單、一筆 `rebalance_diversification` 賣單，以及 `stop_loss`、`trailing_stop_loss` 賣單。
- 未查：這些成交是不是凍結後才下的單，還是更早的訂單到凍結後才成交。資料庫看不出，需要對訂單時間查券商端或執行服務的紀錄。[未驗證]

## 2 換手是怎麼被算的：`ETORO_SYNC` 列的真實語意

**更正**：先前的說法「每筆 eToro 成交都另有一筆 `ETORO_SYNC` 重複列」不成立。重跑查詢後，近 30 天只有部分對得上，同步列也比成交列多。實際語意如下。

- 寫入者：`src/services/etoro_service.py` 的券商交易歷史匯入（約 1140–1240 行）。它把券商歷史的**開倉腿與平倉腿**都寫成 `source_file='ETORO_SYNC'`，用 (日期、**大寫 ticker**、買賣、數量) 與既有交易比對來避免重複。
- 重複的成因：券商歷史只有 instrument ID。查不到對應代號時 ticker 會變成 `ID_<id>`，與系統自己寫入的 `AMZN` 之類的列比對不到，去重失效，同一筆成交就寫成兩列。代號查得到的，去重正常。
- 資料佐證（唯讀，可重跑）：

```bash
$Q "with s as (select ticker,action,trade_date::date d,round(quantity::numeric,4) q,price from transactions where source_file='ETORO_SYNC' and entry_category='trade' and trade_date>=current_date-30),
e as (select action,trade_date::date d,round(quantity::numeric,4) q,price from transactions where source_file='eToro' and entry_category='trade' and trade_date>=current_date-30)
select (s.ticker like 'ID\_%') is_id, count(*) sync_rows,
 count(*) filter (where exists (select 1 from e where e.action=s.action and e.d=s.d and e.q=s.q and abs(e.price-s.price)/nullif(e.price,0)<0.02)) matched_system_fill
from s group by 1 order by 1"
```

  結果的形狀：`ID_` 開頭的同步列，有約六成能用（日期、買賣、數量、價格 2% 內）對上系統自己的成交列，這部分是重複；代號查得到的同步列則一筆都對不上，是系統自己列沒有的腿（多為平倉的賣單）。其餘 `ID_` 列對不上，不能斷定是重複。
- 對 K3／K4 的影響：`mission_watchdog_service.py` 的 `_trades` 把 `entry_category='trade'` 的所有列都算，不分 `source_file`。所以換手同時被兩件事影響：重複列讓它偏高；系統自己列沒記的真實平倉腿讓它偏低。**整個排除 `ETORO_SYNC` 會低估真實換手**，不是正確的修法。
- 影響量：未算。要算需要先決定「同一筆成交」怎麼判定（見選項 L2）。先前報告的「K4 51x→21x」「K3 最差日 85.8%→26.4%」沒有這個依據，**不採用**。[未驗證]

## 3 選項

### 3.1 凍結閘門：買單

| | A：收緊關鍵字清單 | B：明文白名單 |
|---|---|---|
| 做法 | 把會買進的策略移出 `is_safety_control` 關鍵字清單，至少 `cash_deployment`、`benchmark_parking`、`capital_rotation` | 在 `mission.yaml` 的 ADR 補一條凍結時仍允許的策略白名單，程式讀這份白名單，不再用關鍵字清單 |
| 好處 | 與 ADR-003 (5) 文字一致，改動最小 | 把「安全控制」從隱性清單變成可審查的明文 |
| 風險 | 凍結期間現金閒置，相對 SPY 有追蹤誤差 | 白名單要人維護；寫錯等於凍結失效 |
| 動到 | `strategy_registry.py`、測試 | `mission.yaml`、`strategy_registry.py`、測試、ADR |

依你 2026-10-30 的決定（`benchmark_parking` 凍結時不買），兩案的內容相同：白名單只剩真正的出場（`stop_loss`、`trailing_stop_loss`、`trailing_stop`、`emergency_exit`、`position_exit`、`take_profit`）。我的傾向：B 的結構較好；若只要最小改動，A 即可。

### 3.2 凍結閘門：賣單

- S1：維持現狀，所有賣單放行（符合「不自動清倉」的字面）。換手不會因此被擋，K4 在凍結期內可能清不掉。
- S2：非出場性質的賣單（`rebalance_diversification`、`capital_rotation`、`stagnation_pruning` 的賣出）在凍結期間也擋下，只放行出場類。更貼近「停止新的非安全下單」，代價是持倉在凍結期內不再調整。
- 我的傾向：S2，但這是語意取捨，不是從程式能推出的事實，由你決定。

### 3.3 帳本：怎麼讓換手算對

- L1：修根因，匯入時用 instrument ID 解析代號，或改用 instrument ID 去重。動券商同步路徑（`etoro_service.py`），R3。
- L2：只改 watchdog 的計算：算換手前先把「同一筆成交」合併（日期、買賣、數量、價格 2% 內，跨 `source_file`）。動 `mission_watchdog_service.py`，屬 R3 憲章路徑。優點是不碰券商同步。
- L3：先不改，只在 K3／K4 的報告旁標註已知偏差。
- 不論選哪個，都要先把 §2 的「影響量」算出來，再決定要不要為了它改門檻之外的東西。

## 4 驗收（實作時先寫成會失敗的檢查）

- 單元測試：凍結狀態下，不在白名單的策略 BUY 被 `order_allowed` 回 False；白名單策略與出場放行；S2 時非出場 SELL 被擋。
- 不變量測試：白名單與 `mission.yaml` 一致（B）。
- 帳本：同一筆成交跨 `source_file` 只算一次的單元測試；`ID_` 列對得上系統成交時合併，對不上時保留。
- 部署後：上面 §1 的第一條查詢，凍結期間不在白名單的策略 BUY 為 0。

## 5 不做的事

- 不改 K1／K3／K4 門檻，不改凍結／解除的條件，不清倉，不手動解凍。
- 不放寬 K3／K4，直到 §2 的影響量算出來。
- 本文件不處理 K1 與 LLM 預算的矛盾（另案，先出回放數據），也不處理 `LEDGER_ANCHOR` 的現金漂移對帳（未查）。

## 6 需要你決定

1. 買單走 A 還是 B（`benchmark_parking` 不買已決定）。
2. 賣單走 S1 還是 S2。
3. 帳本走 L1、L2 還是 L3；是否先授權我做「影響量」的唯讀計算。
4. 是否要在 2026-11-19 前處理（之後問題暫時不顯現，但下次凍結會重現）。

DERIVED: 通用：是（「安全例外」清單要明文可審查，不要藏在關鍵字比對裡；匯入來源會產生重複時，先查重複的成因與量，再決定整個排除或合併）
