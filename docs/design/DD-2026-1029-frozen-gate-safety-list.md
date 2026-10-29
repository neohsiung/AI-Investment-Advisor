# DD-2026-1029 — 憲章凍結時，哪些買入策略仍可下單（提案，待人核可）
> 一句話：凍結閘門把 `cash_deployment`、`benchmark_parking` 等會買進的策略當成安全控制放行，凍結後仍成交 11 筆買單；這份文件列出兩種修法，由人決定。

**狀態**：提案（未實作；本文件不改任何程式或 `mission.yaml`）
**風險級**：R3（`unified_risk_gateway_service.py`、`charter_state_service.py`、`config/mission.yaml` 都在動錢路徑；實作前需人核可加 ADR）
**上游**：ADR-003 (5) 停機語意；來自 2026-10-29 的運作檢查

## 1 問題：現在怎麼運作、哪裡和文字不一致
- 文字：`config/mission.yaml` 的 ADR-003 (5) 與 `kill_criteria` 寫「K1／K3／K4 違規 → `charter_state=frozen`，停止新的非安全下單，不自動清倉」。
- 實作：`unified_risk_gateway_service.py` 的第 0 道閘門呼叫 `charter_state_service.order_allowed`；賣單與「安全控制」策略免讀狀態直接放行。「安全控制」由 `StrategyRegistry.is_safety_control` 判定，除了各策略合約外還有一份關鍵字清單，其中包含 `capital_rotation`、`rebalance_diversification`、`cash_deployment`、`stagnation_pruning`、`macro_volatility_hedge`、`benchmark_parking`。
- 結果：這些策略中會買進的（至少 `cash_deployment`、`benchmark_parking`）在凍結期間照常下單。
- 證據（唯讀，可重跑）：

```bash
docker exec advisor_prod_db psql -U postgres -d advisor_prod -c "select raw_data->>'strategy_name' strat, count(*), round(sum(amount)::numeric,2) usd from transactions where action='BUY' and entry_category='trade' and source_file='eToro' and created_at>='2026-10-21 10:10' group by 1"
docker exec advisor_prod_db psql -U postgres -d advisor_prod -c "select * from charter_state"
```

  查到：`cash_deployment` 9 筆約 $442、`benchmark_parking` 2 筆約 $310（凍結自 2026-10-21 10:10 UTC 起，解除預定 2026-11-19）。數字會隨時間變，以指令為準。
- 未查：這些策略是否「應該」算安全控制，是設計意圖，不是從程式能推出的事實。`benchmark_parking`（把現金停在 SPY）可以主張是降低追蹤誤差；`cash_deployment` 是分批建倉，較難這樣主張。[推論]

## 2 選項

| | A：收緊清單 | B：明文承認 |
|---|---|---|
| 做法 | 把會買進的策略移出 `is_safety_control` 關鍵字清單（至少 `cash_deployment`），凍結時被閘門擋下 | 在 `mission.yaml` 的 ADR 補一條：凍結時仍允許的買入策略白名單，並讓程式讀這份白名單，不再用關鍵字清單 |
| 好處 | 行為與現有文字一致；改動最小 | 把「安全控制」從隱性清單變成可審查的明文；`benchmark_parking` 可保留 |
| 風險 | 凍結期間現金閒置，相對 SPY 有追蹤誤差（本帳戶是和 SPY 比超額報酬） | 白名單本身要人維護；寫錯等於凍結失效 |
| 動到 | `strategy_registry.py`（R3 路徑）、測試 | `mission.yaml`、`strategy_registry.py`、測試、ADR |

我的傾向（可被推翻）：B 的結構較好（明文、可審查），但內容上 `cash_deployment` 不進白名單、`benchmark_parking` 是否進由你決定。若只要最小改動，A 即可。

## 3 驗收（實作時先寫成會失敗的檢查）
- 單元測試：凍結狀態下，非白名單策略的 BUY 被 `unified_risk_gateway` 以 `CharterHalt` 擋下；白名單策略放行；SELL 一律放行。
- 不變量測試：`is_safety_control` 的清單與 `mission.yaml` 的白名單一致（B）。
- 部署後：凍結期間的 `transactions` 查詢，非白名單策略的 BUY 為 0（上面第一條指令）。

## 4 不做的事
- 不改 K1／K3／K4 門檻，不改凍結／解除的條件，不清倉。
- 不在本文件決定 `benchmark_parking` 算不算安全控制。

## 5 需要你決定
1. 走 A 還是 B。
2. `benchmark_parking` 凍結時可不可以買。
3. 是否要這週處理（凍結預定 11/19 解除，之後這個問題暫時不顯現，但會在下次凍結重現）。

DERIVED: 通用：是（「安全例外」清單要明文可審查，不要藏在關鍵字比對裡）
