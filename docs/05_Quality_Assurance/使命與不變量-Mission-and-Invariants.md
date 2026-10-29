# 使命與不變量 (Mission & Invariants)

### 版本紀錄 (Version History)

| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-10-16 | v1.0 | 初版：使命檔 `config/mission.yaml`、不變量測試、部署前閘門、再平衡護欄、基準停泊、策略實驗室與多重檢定帳本。 | Claude |
| 2026-10-17 | v1.1 | 這一版換掉的想法：基準停泊從「願景」變成「已啟用」（ADR-002），並明定自動調整只能讓系統更保守；新增棘輪涵蓋舊演化任務與下單呼叫點。 | Claude |

## 🇹🇼 繁體中文

### 為什麼
經過深度健檢，專案的規則幾乎只是文件；真正會讓流程失敗的只有少數測試，而部署路徑完全不經過它們。結果是同一類事故反覆發生：一次賣出 11 檔、設定檔錯誤導致標的被誤剔除、模擬成交擋住真實買進。使命與不變量把「專案要什麼、絕對不能做什麼」變成**會失敗的機制**。

### 單一真相
- `config/mission.yaml`：目標（相對 SPY、扣成本）、預算、不變量、晉升門檻、7 條 kill criteria、ADR。程式以 `src.config.mission.load_mission()` 讀取，禁止複製數字。
- `AGENTS.md` 的 `MISSION` 區塊是所有 AI agent 規則的來源；`scripts/gen_agent_shims.py` 產生其他工具的指令檔，`tests/invariants` 檢查同步。

### 強制機制
| 機制 | 位置 | 作用 |
| :--- | :--- | :--- |
| 不變量測試（棘輪） | `tests/invariants/` | `src.*` import 必須可解析、僅 executor 可下單、禁新增寫死分數、演化碼不得寫正式設定；既有違規列入基準，只能縮小 |
| 部署前閘門 | `scripts/predeploy_gate.sh`（接入 `start.sh up/upgrade`） | 乾淨工作樹、main/tag、YAML 可解析、alembic 單 head、config/invariants/deploy 測試；覆寫需 `FORCE_DEPLOY=1` 並寫稽核 |
| 再平衡護欄 | `src/services/rebalance_guard.py` | 賣單需真實分數、需換入計畫、每日 ≤2 檔且 ≤淨值 20%（超額縮減分日退出）、資料不健康即 fail-closed |
| 資本上限 | `capital_policy.tradable_capital` | `tradable_capital_pct`（預設 75%）與 USD 上限取較嚴者；0 代表禁止交易 |
| 看門狗 | `mission_watchdog_service` / `GET /api/v1/mission/status` | 每日評估 kill criteria；無法量測者明示 `not_measurable` |
| 基準停泊 | `benchmark_parking_service`（預設關閉） | 閒置資金買入 SPY；只買不賣；核心部位不受停損/集中度/換庫/剔除觸碰 |
| 策略實驗室 | `strategy_lab_service` / `GET /api/v1/mission/strategies` | 每個變體只記一次試驗，累計 N 進入 Deflated Sharpe；通過 DSR 與 t 值才成為 shadow 候選，不直接配置資金 |

### 真實資料評估結果（2026-10-16，46 檔現有大型股，約 4 年，成本 10 bps）
動能傾斜（SPY 70% ＋ 動能前 3 檔 30%）：年化超額 +4.4%、追蹤誤差 7.4%、IR 0.6、t=1.2；DSR（N=1）=0.89、（N=12）=0.32；未達晉升門檻；若以實盤證明（t=3）需約 25 年。**注意**：標的池為現有成分股，存在存活者偏差，結果偏樂觀；僅作流程示範與下限檢查。

### 2026-10-17 補充：ADR-002 與自動調整的邊界

- **ADR-002（2026-10-17）**：啟用基準停泊——閒置現金分批買入 SPY（槓桿 1、只買不賣、有區間與單筆上限），讓 `default_allocation: benchmark` 成為實際行為而非願景。依據：SPY 買賣價差約 0.004%、槓桿 1 的多單不是 CFD、支援零股、最小 $10；**未驗證**：每筆下單手續費、台灣稅務居民的股息預扣（估約每年 0.4% 拖累）。回滾：`benchmark_parking_enabled=false`。
- **自動調整只能更保守**：任何自動發生的調整只能收緊；放寬一律是人核准的提案（設計見 自適應閘門與證據迴圈）。
- **新棘輪**：演化模組寫設定的檢查現在也涵蓋 `settings_repo.set(` 與 `save_setting(`；`evaluate_and_execute_trade` 的呼叫點數量被凍結，只能減少（目前 8 個檔案共 17 處）。
- 驗證：`.venv/bin/python -m pytest tests/invariants -q`；停泊計畫 `curl -s localhost:8088/api/v1/mission/parking-plan`。

## 🇺🇸 English

### Why
Rules were prose; only a few tests could fail a build and the deploy path ran none. The same class of incident kept recurring (11 holdings sold in one run, a malformed settings file evicting tickers, simulated fills blocking real buys). Mission & invariants turn "what we want / never do" into mechanisms that fail loudly.

### Sources of truth
`config/mission.yaml` (objective vs SPY net of costs, budgets, invariants, promotion thresholds, 7 kill criteria, ADR log), loaded via `load_mission()`; the `MISSION` block of `AGENTS.md` feeds every agent instruction file (`scripts/gen_agent_shims.py`, checked in `tests/invariants`).

### Enforcement
Ratchet invariant tests; `scripts/predeploy_gate.sh` wired into `start.sh up|upgrade`; `rebalance_guard`; percentage capital cap (0 = trading disabled); kill-criteria watchdog (explicit `not_measurable`); benchmark parking (default OFF, buy-only, core exempt from discretionary exits); strategy lab with a multiple-testing ledger (cumulative trial count N feeds the Deflated Sharpe).

### Real-data evaluation (2026-10-16)
Momentum tilt over 46 current large caps, ~4y, 10 bps: +4.4%/yr excess, TE 7.4%, IR 0.6, t 1.2, DSR 0.89 (N=1) / 0.32 (N=12) — not promotable; ~25 years of live data would be needed for t=3. Survivorship bias (current constituents) makes this optimistic.
