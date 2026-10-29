# 靜默失敗防治 (Fail-Silent Prevention)

### 版本紀錄 (Version History)

| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-08-12 | v1.0.0 | 初版。彙整 2026-08-07~12 事故群的共同成因，訂立決策路徑的 except 規則，並以 `tests/unit/test_fail_silent_policy.py` 強制執行。 | Claude Opus 5 |

---

> **[繁體中文 (Traditional Chinese)](#zh) | [English](#en)**

---

<a id="zh"></a>

## 🇹🇼 靜默失敗防治

### 1. 為什麼需要這條規則

本系統至今每一次嚴重事故，都**不是**崩潰，而是「系統回報健康、數字看起來合理、實際上什麼都沒做」。

| 事故 | 靜默機制 | 後果 |
| :--- | :--- | :--- |
| 交易迴圈停擺三天 | dispatcher 的 `.delay()` 送出即回報成功 | 所有監控全綠；最後兩天 `dispatch_sentinel_tick` 成功 95 次，`sentinel_tick` 僅 2 次 |
| 信心分數是 ticker 雜湊值 | LLM 呼叫失敗 → `_fallback_score()` 代換外觀合理的假值 | 約 65% 的買進綜合分數是捏造的，但介面上完全看不出來 |
| 三道 BUY 護欄全部放行 | 歷史資料少於三筆時 `return None` | `decision_outcomes` 為空 → 護欄看似啟用、實則毫無作用 |
| 動能因子永遠中性 5.0 | `MarketDataService()` 建構失敗被廣泛 `except` 吞掉 | 四分之一的出場評分權重長期無效 |
| dashboard 快取只讀不寫 | `setex()` 寫在 `return` 之後 | 每次請求都完整重算，快取形同不存在 |

**崩潰會被發現；一個看似合理的錯誤數字不會。** 這就是本規則存在的理由。

### 2. 規則

> 決策路徑（**交易、評分、風控、排程**）的 `except` 區塊，不得同時滿足下列兩件事：
> 1. 以 `warning` 以下的層級記錄（`debug`、`info`、或完全不記錄、`pass`）
> 2. 回傳一個「看起來像真實答案」的值
>
> 兩者可擇一，不可兼具。

- 想安靜？那就讓錯誤往上拋，由呼叫端決定。
- 想代換預設值？那就用 `warning` 以上記錄，**並且**替該值標記來源。

### 3. 代換預設值時的標記義務

若必須回傳預設值，該值要帶上可觀察的標記，且**呼叫端要能把它顯示給使用者**。

本專案已有的正確範例（規則是把既有好做法寫成標準，不是憑空發明）：

```python
# src/services/exit_compositor_service.py
@staticmethod
def _unavailable(error: Exception) -> Dict[str, Any]:
    return {
        "key_factor": "評分不可用",
        "rationale": f"{type(error).__name__}: {error}",
        "_insufficient_data": True,
    }
```

```python
# src/services/confidence_compositor_service.py
fallback_score, fallback_factors = self._fallback_score(ticker, agent_name)
fallback_factors["_fallback_reason"] = str(e)   # ← 讓下游知道這是假值
```

而 `src/services/decision_card.py` 會把 `Fallback (hash-based)` 直接印在 Telegram 卡片上——使用者看得到哪一項不是真的。**這才是完整的閉環：標記 + 顯示。**

### 4. fail-open 還是 fail-closed？

標記之外還要選方向，判準是「哪個錯誤比較貴」：

| 情境 | 方向 | 理由 |
| :--- | :--- | :--- |
| 再平衡冷卻機制不可用 | **fail-closed**（不交易） | 重複賣單不可逆；跳過本輪只損失一次機會 |
| 告警冷卻機制不可用 | **fail-open**（照發） | 漏掉 P0 比重複通知糟 |
| 部位大小計算失敗 | **fail-closed**（擋 BUY） | 未經 sizing 的買單流到真實 broker 是最糟結果 |
| 賣出數量鉗制失敗 | **fail-closed**（擋 SELL） | 未鉗制的賣單可能超賣成做空部位 |
| 風險評分的 LLM 失敗 | **中性 5.0** | 給 10 分會讓每次供應商中斷變成全組合清倉 |

注意最後一列：fail-closed 不是萬用答案。把 LLM 故障當成「高風險」會製造假性清倉。

### 5. 強制執行

`tests/unit/test_fail_silent_policy.py` 以 AST 掃描決策路徑檔案，斷言不存在「`except` 內只有 `debug`/`pass` 且函式回傳預設值」的組合。白名單需附理由。

---

<a id="en"></a>

## 🇬🇧 Fail-Silent Prevention

### 1. Why this rule exists

Every serious incident in this system has been a silent one, not a crash: the
system reported healthy, the numbers looked plausible, and nothing real was
happening. A three-day trading outage with every monitor green. Confidence
scores that were hashes of the ticker symbol. Three BUY guards that passed
because the table they read was empty. A momentum factor pinned at a neutral
5.0 because a constructor threw inside a broad `except`.

**A crash gets noticed. A plausible wrong number does not.**

### 2. The rule

> On a decision path (**trading, scoring, risk, scheduling**), an `except`
> block must not do both of the following:
> 1. log below `warning` (`debug`, `info`, nothing at all, or `pass`)
> 2. return a value that looks like a real answer
>
> Choose one.

Want it quiet? Let the error propagate and let the caller decide. Want to
substitute a default? Log at `warning` or above **and** mark the value.

### 3. Marking obligation

A substituted default must carry an observable marker, and the caller must be
able to surface that marker to the user. `ExitCompositorService._unavailable()`
and the `_fallback_reason` key in `CompositorService` are the reference
implementations; `decision_card.py` prints `Fallback (hash-based)` straight
onto the Telegram card. Marking without surfacing is only half the loop.

### 4. Fail open or fail closed?

Pick by which error is more expensive. Rebalance cooldown unavailable → fail
closed (a duplicate sell is irreversible). Alert cooldown unavailable → fail
open (a missed P0 beats a duplicate notification). Position sizing failure →
fail closed on BUY. LLM risk scoring failure → neutral 5.0, because scoring it
10 would turn every provider outage into a portfolio-wide liquidation.
Fail-closed is not the universal answer.

### 5. Enforcement

`tests/unit/test_fail_silent_policy.py` walks the AST of decision-path modules
and asserts no `except` both swallows to `debug`/`pass` and returns a default.
Waivers go in the allowlist with a stated reason.
