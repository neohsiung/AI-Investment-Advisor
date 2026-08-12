"""
How much of the brokerage account this system is allowed to touch.
本系統獲准動用的帳戶資金上限。

Why this exists / 為何需要
────────────────────────
The eToro account holds roughly $1,048 (daily_snapshots, 2026-08-02), but the
automated trading loop has never placed a single order — `transactions` still
has zero rows with `entry_category='trade'`. Turning it loose on the whole
balance to find out whether it works would be an expensive way to learn.

So the loop is capped: it sizes every position against a *tradable capital*
figure rather than the real net liquidation value. Set it to $100 and the
worst case is losing $100, no matter what the account actually holds.

This is a software-level cap, not a broker-level one. It only holds if every
place that sizes an order asks this module rather than reading `total_equity`
directly. That is the whole point of putting it in one function: there is a
single thing to audit, and `test_capital_policy.py` asserts the call sites
stay wired to it.

eToro 帳戶約有 $1,048，但自動交易迴圈至今從未成交過任何一筆。直接讓它動用
全部餘額來驗證能否運作，代價太高。因此改以「可交易資本」而非真實淨值來計算
部位大小：設為 $100，最壞情況就是賠掉 $100。

此上限屬軟體層而非券商層，只有在「每個計算部位的地方都呼叫本模組」時才成立。
把它收斂成單一函式，就是為了讓稽核對象只有一個。

Sizing arithmetic at $100 / $100 下的部位計算
─────────────────────────────────────────────
eToro's minimum order is $10, which is coarse relative to $100 — only ten
units of resolution. With `max_single_position_pct` at its 0.10 default, every
position caps at exactly $10, i.e. exactly the minimum, so any downward clamp
(insufficient cash, rounding) drops below the minimum and the order is skipped
outright. 0.20 gives a $20 target with 2x of clamp headroom, and leaves room
for four positions alongside the 20% cash target.

eToro 最小單為 $10，相對於 $100 只有十格解析度。若 max_single_position_pct
維持預設 0.10，每筆上限剛好等於最小單，任何往下鉗制都會跌破門檻而整筆略過。
改用 0.20（每筆 $20）可留兩倍鉗制餘裕，並容納四個部位加上 20% 現金水位。
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("CapitalPolicy")

# Settings key holding the cap, in USD. 0 / negative / absent all mean
# "no cap — use the broker's real equity", which is how this behaves for
# anyone who never opts in.
# 上限設定鍵（美元）。0、負數或未設定皆代表「不設限，使用券商真實淨值」。
SETTING_TRADABLE_CAPITAL = "tradable_capital_usd"

# Default while the $100 live test runs. Raising this one value is the whole
# ceremony for scaling up later.
# $100 實測期間的預設值；日後放大資金只需改這一個值。
DEFAULT_TRADABLE_CAPITAL_USD = 100.0


def tradable_capital(
    user_id: str,
    broker_nlv: float,
    settings_repo: Any = None,
) -> float:
    """
    The equity figure position sizing must use. Never exceeds the real account.
    部位計算應使用的權益數字；絕不超過帳戶真實金額。

    `broker_nlv` is the account's real net liquidation value. The return is
    `min(broker_nlv, cap)` — capping can only ever shrink the number, so this
    cannot cause the system to size against money that is not there.
    回傳 min(真實淨值, 上限)：只會縮小、不會放大，因此不可能讓系統以不存在的
    資金計算部位。
    """
    try:
        nlv = float(broker_nlv)
    except (TypeError, ValueError):
        logger.warning(f"tradable_capital: unusable broker_nlv={broker_nlv!r}; treating as 0")
        return 0.0

    if nlv <= 0:
        return 0.0

    cap = _configured_cap(user_id, settings_repo)
    if cap is None:
        return nlv

    if cap < nlv:
        logger.info(
            f"Capital policy: sizing against ${cap:.2f} tradable capital "
            f"(account NLV ${nlv:.2f})"
        )
        return cap
    return nlv


def is_small_test_capital(
    user_id: str,
    broker_nlv: float,
    settings_repo: Any = None,
) -> bool:
    """
    True while the tradable capital is small enough to count as a live test.
    可交易資本仍屬「小額實測」規模時回傳 True。

    Used by the strategy-validation gate in AutomatedTradingService to waive
    the backtest requirement during the $100 run. It reads the *effective*
    capital, so raising `tradable_capital_usd` re-arms the gate automatically
    — nobody has to remember to switch the waiver back off.
    供 AutomatedTradingService 的策略驗證關卡在 $100 實測期間豁免回測要求。
    因為讀的是「實際生效」的資本，調高上限即自動恢復把關，無需記得手動關閉。
    """
    threshold = _small_test_threshold(user_id, settings_repo)
    if threshold <= 0:
        return False
    return tradable_capital(user_id, broker_nlv, settings_repo) <= threshold


def _configured_cap(user_id: str, settings_repo: Any) -> Optional[float]:
    """Read the cap; None means uncapped. 讀取上限；None 代表不設限。"""
    raw = _read_setting(user_id, SETTING_TRADABLE_CAPITAL, settings_repo)
    if raw is None:
        return DEFAULT_TRADABLE_CAPITAL_USD
    try:
        cap = float(raw)
    except (TypeError, ValueError):
        logger.warning(
            f"Invalid {SETTING_TRADABLE_CAPITAL}={raw!r}; "
            f"falling back to ${DEFAULT_TRADABLE_CAPITAL_USD:.2f}"
        )
        return DEFAULT_TRADABLE_CAPITAL_USD
    # An explicit 0 (or negative) is the documented way to remove the cap.
    # 明確設為 0（或負數）是解除上限的方式。
    return None if cap <= 0 else cap


def _small_test_threshold(user_id: str, settings_repo: Any) -> float:
    raw = _read_setting(user_id, "small_test_capital_usd", settings_repo)
    if raw is None:
        return DEFAULT_TRADABLE_CAPITAL_USD
    try:
        return float(raw)
    except (TypeError, ValueError):
        return DEFAULT_TRADABLE_CAPITAL_USD


def _read_setting(user_id: str, key: str, settings_repo: Any) -> Any:
    repo = settings_repo
    if repo is None:
        from src.repositories.settings_repository import AlchemySettingsRepository
        repo = AlchemySettingsRepository()
    try:
        return repo.get(user_id, key)
    except Exception as e:
        # Fail toward the cap rather than toward the full account balance: an
        # unreadable settings table must not silently unlock all the money.
        # 設定讀取失敗時傾向「維持上限」而非「開放全帳戶」，避免無聲解鎖資金。
        logger.warning(f"Capital policy: settings read failed for {key} ({e}); using default cap")
        return None
