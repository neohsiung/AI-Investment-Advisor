# DD-2026-1031 — 凍結閘門改用明文白名單，並擋下非出場賣單（提案，待人核可）
> 一句話：承接 DD-2026-1029 的決定（買單走 B 明文白名單、賣單走 S2），把設計定到可以核可：白名單只管憲章閘門，不動共用的 `is_safety_control`；凍結期間只放行真正的出場。本文件不改任何程式或 `mission.yaml`。

**狀態**：提案（未實作）
**風險級**：R3 提案（`charter_state_service.py`、`unified_risk_gateway_service.py`、`mission.yaml` 都在動錢路徑；實作前需人核可加 ADR）。本文件本身是 R0。
**上游**：DD-2026-1029-frozen-gate-safety-list（選項與證據）；ADR-003 (5)
**已記錄的決定**（使用者，2026-10-30）：買單走 B；賣單走 S2；`benchmark_parking` 凍結時不能買；1、2 兩項在 2026-11-19 前做。

## 1 讀程式後發現的事（改變了做法）

- `StrategyRegistry.is_safety_control` 不只憲章閘門在用。可重跑：

```bash
grep -rn "is_safety_control" src --include=*.py | grep -v "def is_safety"
```

  `risk_manager.py`、`automated_trading_service.py`（約 6 處）都用它判斷風控與出場路徑。DD-1029 的 A 案「把策略移出關鍵字清單」會同時改動這些路徑的行為，不只凍結閘門。
- 因此 B 案要做成**獨立於 `is_safety_control` 的清單**：憲章閘門讀 `mission.yaml` 的凍結白名單，`is_safety_control` 維持原樣。這樣改動範圍就是 `order_allowed` 一個函式與它的呼叫端。
- 賣單閘門目前不存在：`unified_risk_gateway_service.py` 只在 `is_buy` 時呼叫 `order_allowed`（第 0 步）。S2 要讓賣單也走這個呼叫，這是行為變更，不是改清單。

## 2 設計

**白名單**（`mission.yaml` 的 ADR 或獨立區塊，實作時定位置）：`stop_loss`、`trailing_stop_loss`、`trailing_stop`、`emergency_exit`、`position_exit`、`take_profit`。`benchmark_parking`、`cash_deployment`、`capital_rotation`、`rebalance_diversification`、`stagnation_pruning`、`macro_volatility_hedge` 都不在其中。

`order_allowed(action, strategy_name, now)` 新規則：

| 動作 | 策略在白名單 | 策略不在白名單 | 策略名缺漏 |
|---|---|---|---|
| BUY 類 | 放行 | 凍結中擋下 | 凍結中擋下（沿用現行 fail closed） |
| SELL | 放行 | 凍結中擋下（S2） | **放行並標記**（待決定 1） |

- 讀不到狀態：BUY 維持現行 fail closed；SELL 白名單內放行。
- 非凍結時所有規則不變。

## 3 需要你決定（實作前）

1. **策略名缺漏的賣單**：我傾向放行並在回傳理由標記 `unnamed_sell`，因為擋掉無法歸類的出場，風險比放行高。代價是有人可以用空策略名繞過 S2。要不要放行？
2. **`AutomatedTrading` 的賣單**：近 60 天有 3 筆賣單的策略名是 `AutomatedTrading`，不在白名單。S2 實作後它們凍結期間會被擋。我**還沒查**這 3 筆實際是什麼（是通用標籤包著停損，還是別的）。實作前必須先查清楚，查不清楚不可實作 S2。可重跑：

```bash
docker exec advisor_prod_db psql -U postgres -d advisor_prod -c "select action, coalesce(raw_data->>'strategy_name','(none)') strat, count(*) from transactions where created_at > now()-interval '60 days' and source_file='eToro' and entry_category='trade' group by 1,2 order by 1,2"
```

3. **`portfolio_rebalance` 買單**：近 60 天 15 筆，策略名不在現行安全清單，所以現在凍結就會擋，B 案不改變它。列出只為確認這是預期。

## 4 ADR 草稿（ADR-004，實作 PR 一併提交，核可前不進 `mission.yaml`）

> 凍結期間（charter_state=frozen）下單閘門改為明文白名單。BUY 與 SELL 都只放行白名單內的出場策略；白名單列在 `mission.yaml`，修改白名單屬 R3。`is_safety_control` 不變，僅憲章閘門使用白名單。理由：ADR-003 (5) 的「停止新的非安全下單」原由隱性關鍵字清單實作，清單含會買進的策略，凍結後仍成交買單，且所有賣單一律放行使換手無法在凍結期內下降。

## 5 驗收（實作時先寫成會失敗的檢查）

單元測試（`tests/unit/services/test_charter_state_service.py` 擴充）：

- 凍結中 `order_allowed("BUY", "cash_deployment", ...)`、`"benchmark_parking"`、`"capital_rotation"` 回 False。
- 凍結中白名單六個策略的 BUY 與 SELL 回 True。
- 凍結中 `order_allowed("SELL", "rebalance_diversification", ...)` 回 False；策略名 None 的 SELL 回 True 且理由含 `unnamed_sell`。
- 未凍結時以上全部回 True（行為不變）。
- `StrategyRegistry.is_safety_control("cash_deployment")` 仍為 True（共用清單未被動到）。

閘門測試（`tests/unit/services/test_unified_risk_gateway*.py`）：凍結中非白名單 SELL 被 `CharterHalt` 擋下。

不變量測試：白名單與 `mission.yaml` 一致；白名單內每個策略都能在 `StrategyRegistry` 或 `automated_trading_service` 的出場路徑找到。

部署後（可重跑）：

```bash
docker exec advisor_prod_db psql -U postgres -d advisor_prod -c "select action, coalesce(raw_data->>'strategy_name','(none)') strat, count(*) from transactions where created_at > (select since from charter_state) and source_file='eToro' and entry_category='trade' group by 1,2 order by 1,2"
```

凍結期間不應出現非白名單的策略名（除 `unnamed_sell` 例外）。

## 6 不做的事

- 不改 `is_safety_control` 與它在風控、出場路徑的行為。
- 不改 K1／K3／K4 門檻、凍結／解除條件，不清倉，不手動解凍。
- 帳本去重（L2）另案，不在本 DD。

DERIVED: 通用：是（共用的「安全」判斷被多處引用時，要新增一個專用清單，不要改共用清單；先查共用函式的所有呼叫端再選修法）
