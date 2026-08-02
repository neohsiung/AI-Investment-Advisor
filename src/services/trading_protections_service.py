"""
Declarative trading protections (P4.2) — reimplements the freqtrade
protections idea (plugins/protections/*.py, GPL-3.0 — concept only, no code
copied): a small set of rules checked before order submission that can halt
trading based on recent REALIZED outcomes.

Reuses the P1 `decision_outcomes` table (real alpha vs benchmark, not
self-graded) as its evidence source — no new plumbing, and the halt
decisions are grounded in the same falsifiable data the learning loop uses.

三條保護規則（下單前檢查，資料來源＝P1 的 decision_outcomes 真實結果）：
- 全域回撤停機：近期已解決決策的平均 alpha 過於負向 → 暫停新 BUY
- 個股虧損冷卻：該標的最近一次已解決決策虧損 → 冷卻期內暫停該標的新單
- 連續虧損鎖定：最近 N 筆已解決決策全部虧損 → 全面暫停新 BUY

All checks are advisory-safe: any DB/query failure returns "allow" (None)
rather than blocking trading on an infrastructure hiccup — protections must
never become a new source of downtime for a live trading system.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import bindparam, text

from src.data.database import get_db_engine

logger = logging.getLogger(__name__)

# Defaults — conservative. Now overridable per user via settings; these remain
# the fallback when the settings read fails (see _load_config).
# 這些同時是預設值與設定讀取失敗時的 fallback。
MAX_DRAWDOWN_HALT_ALPHA_PCT = -5.0     # avg alpha over lookback below this → halt
DRAWDOWN_LOOKBACK_N = 10
PER_TICKER_COOLDOWN_DAYS = 3
CONSECUTIVE_LOSS_LOCKOUT_N = 3
SELL_CHURN_ENABLED = True
SELL_CHURN_LOOKBACK_DAYS = 3
SELL_CHURN_MAX_ROUND_TRIPS = 2

_SETTING_DEFAULTS = {
    "protection_max_drawdown_alpha_pct": MAX_DRAWDOWN_HALT_ALPHA_PCT,
    "protection_drawdown_lookback_n": DRAWDOWN_LOOKBACK_N,
    "protection_ticker_cooldown_days": PER_TICKER_COOLDOWN_DAYS,
    "protection_consecutive_loss_lockout_n": CONSECUTIVE_LOSS_LOCKOUT_N,
    "protection_sell_churn_enabled": SELL_CHURN_ENABLED,
    "protection_sell_churn_lookback_days": SELL_CHURN_LOOKBACK_DAYS,
    "protection_sell_churn_max_round_trips": SELL_CHURN_MAX_ROUND_TRIPS,
}

# `decision_outcomes.signal` carries a FIVE-value scale (structured.Rating:
# STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL), so filtering on `= 'BUY'`
# would silently drop the highest-conviction decisions. Always use IN-lists.
# signal 是五值，不是三值；用 = 'BUY' 會漏掉 STRONG_BUY 這些最高信心的決策。
BUY_SIDE_SIGNALS = ("BUY", "STRONG_BUY")
SELL_SIDE_SIGNALS = ("SELL", "STRONG_SELL")

# Action vocabulary actually emitted upstream. Kept in sync with
# src/agents/action_extractor.py, which collapses free-text CIO actions into
# BUY / SELL / HOLD, and with src/agents/structured.py Rating
# (STRONG_BUY | BUY | HOLD | SELL | STRONG_SELL).
# 上游實際會產生的 action 字彙；與 action_extractor 及 structured.Rating 保持同步。
_BUY_ACTIONS = frozenset({"BUY", "STRONG_BUY", "ACCUMULATE", "ADD", "INCREASE"})
_SELL_ACTIONS = frozenset({
    "SELL", "STRONG_SELL", "TRIM", "REDUCE", "LIQUIDATE", "EXIT", "CLOSE",
})
_HOLD_ACTIONS = frozenset({"HOLD", "NEUTRAL"})


def _normalize_side(action: object) -> Optional[str]:
    """
    Map a raw action to "BUY" / "SELL" / "HOLD", or None if unrecognized.

    Why this matters for safety: AutomatedTradingService resolves the order
    direction with `OrderAction.BUY if action.upper() == "BUY" else
    OrderAction.SELL`, so ANY unrecognized string becomes a live SELL. The
    WebSocket manual-order path forwards a client-supplied action verbatim at
    confidence_score=10 (always auto-executes, no approval card). Returning
    None here lets check() refuse instead of silently selling.

    將 action 正規化為 BUY / SELL / HOLD，無法辨識回 None。
    下游是「非 BUY 即 SELL」，所以無法辨識的字串會變成真實賣單；
    WebSocket 手動下單又是 client 直接傳入且必定自動執行，故必須在此攔下。
    """
    if action is None:
        return None
    token = str(action).strip().upper().replace("-", "_").replace(" ", "_")
    if not token:
        return None
    if token in _BUY_ACTIONS:
        return "BUY"
    if token in _SELL_ACTIONS:
        return "SELL"
    if token in _HOLD_ACTIONS:
        return "HOLD"
    return None


class TradingProtectionsService:
    def __init__(self, user_id: str, db_path: Optional[str] = None):
        self.user_id = user_id
        self.engine = get_db_engine(db_path)
        self._cfg = None

    def _load_config(self) -> dict:
        """
        Read protection thresholds from settings, falling back to the module
        defaults on any failure.

        Falling back is fail-SAFE here: the defaults are exactly the current
        conservative behaviour, so a settings-table hiccup must not become a
        reason to block every BUY. One bulk read, not seven point queries.
        設定讀取失敗時退回常數（常數就是現行保守值），避免設定表打嗝擋掉所有 BUY。
        """
        if self._cfg is not None:
            return self._cfg
        cfg = dict(_SETTING_DEFAULTS)
        try:
            from src.services.settings_service import SettingsService
            stored = SettingsService(user_id=self.user_id).get_all_settings() or {}
            for key, default in _SETTING_DEFAULTS.items():
                if key not in stored or stored[key] in (None, ""):
                    continue
                raw = stored[key]
                if isinstance(default, bool):
                    cfg[key] = str(raw).strip().lower() in ("true", "1", "yes")
                elif isinstance(default, int):
                    cfg[key] = int(float(raw))
                else:
                    cfg[key] = float(raw)
        except Exception as exc:
            logger.warning(
                "TradingProtectionsService: settings read failed, using defaults: %s", exc
            )
        self._cfg = cfg
        return cfg

    def check(self, ticker: str, action: str) -> Optional[str]:
        """
        Returns None if the trade may proceed, or a human-readable block
        reason string if a protection rule fires. Only BUY-side actions are
        gated (protections should never block getting OUT of a position).

        An unrecognized action is REFUSED rather than waved through: the
        caller turns anything that isn't "BUY" into a SELL order, so passing
        an unknown token here would place an unguarded live sell.
        無法辨識的 action 一律拒絕：下游「非 BUY 即 SELL」，放行等於未經風控的真實賣單。
        """
        side = _normalize_side(action)
        if side is None:
            logger.error(
                "TradingProtectionsService: unrecognized action %r for %s — refusing",
                action, ticker,
            )
            return (
                f"Unrecognized trade action {action!r}; refused for safety "
                "(unknown actions are treated as SELL downstream)"
            )
        if side == "HOLD":
            return None

        if side == "SELL":
            # SELL is gated ONLY by the churn rule, and it fails OPEN.
            # The three BUY rules key off "recent decision alpha is negative",
            # which is precisely when a user most needs to exit — applying them
            # to SELL would lock people into falling positions. And a churn
            # guard is a nice-to-have, so it must never itself become the
            # reason someone cannot get out.
            # SELL 只走 churn 規則且 fail-open：三條 BUY 規則的觸發條件正是使用者
            # 最需要出場的時候；churn 只是加分項，不能變成無法出場的理由。
            try:
                return self._check_sell_churn(ticker)
            except Exception as exc:
                logger.error(
                    "TradingProtectionsService: SELL churn check failed — allowing exit: %s", exc
                )
                return None

        try:
            reason = (
                self._check_max_drawdown()
                or self._check_ticker_cooldown(ticker)
                or self._check_consecutive_loss_lockout()
            )
            return reason
        except Exception as exc:
            # 2026-08-02: fail CLOSED. Previously this returned None on any
            # error, so a transient DB fault silently disarmed every BUY-side
            # protection. Only BUY reaches here, so blocking never traps a
            # user in a position.
            # 2026-08-02：改為 fail-closed。此處只會是 BUY，擋下不會把人鎖在部位裡。
            logger.error("TradingProtectionsService: check failed — blocking BUY: %s", exc)
            return f"Protection check unavailable ({type(exc).__name__}); BUY blocked for safety"

    def _check_sell_churn(self, ticker: str) -> Optional[str]:
        """
        Block a SELL only when this ticker is being repeatedly cycled.

        Counts COMPLETED ROUND TRIPS (a SELL later followed by a BUY of the
        same ticker) in the window — not raw SELL count. Scaling out of one
        position in tranches is legitimate risk management and a raw count
        would block it. Requiring an intervening BUY proves the position was
        re-established, i.e. genuine churn. It also makes the rule
        STRUCTURALLY incapable of blocking a first exit: with zero
        SELL→BUY alternations the count is 0 and the rule cannot fire. That
        property is what makes it safe to run on a live account.

        Reads `transactions` (the executed-trade ledger) rather than
        `decision_outcomes` (council intent, written even when nothing traded,
        and never written by the Sentinel/webhook SELL paths).
        Uses `trade_date`, not `created_at`: a full eToro history re-sync
        stamps months-old SELLs with a recent created_at and would instantly
        false-positive.
        以「完成的來回次數」計算，而非 SELL 原始筆數 —— 分批出場是正當的，
        要求中間有 BUY 才算 churn，因此結構上不可能擋掉第一次出場。
        """
        cfg = self._load_config()
        if not cfg["protection_sell_churn_enabled"]:
            return None

        lookback_days = int(cfg["protection_sell_churn_lookback_days"])
        max_round_trips = int(cfg["protection_sell_churn_max_round_trips"])

        from datetime import date, timedelta
        cutoff = date.today() - timedelta(days=lookback_days)

        with self.engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT trade_date, action FROM transactions
                WHERE user_id = :user_id AND ticker = :ticker
                  AND UPPER(action) IN ('BUY', 'SELL')
                  AND entry_category = 'trade'
                  AND trade_date >= :cutoff
                ORDER BY trade_date ASC
            """), {"user_id": self.user_id, "ticker": ticker, "cutoff": cutoff}).fetchall()

        round_trips = 0
        awaiting_rebuy = False
        for _, action in rows:
            act = str(action).upper()
            if act == "SELL":
                awaiting_rebuy = True
            elif act == "BUY" and awaiting_rebuy:
                round_trips += 1
                awaiting_rebuy = False

        if round_trips >= max_round_trips:
            return (
                f"{ticker} churn guard: {round_trips} sell→buy round trips in the last "
                f"{lookback_days}d (limit {max_round_trips}). New SELL paused for this ticker."
            )
        return None

    def _check_max_drawdown(self) -> Optional[str]:
        # alpha_pct is nullable and only resolved_at was filtered, so a resolved
        # row with a NULL alpha reached float(None) → TypeError. Combined with
        # the fail-closed handler above, a single such row blocked every BUY.
        # alpha_pct 可為 NULL，原本只過濾 resolved_at，float(None) 會 TypeError；
        # 配上 fail-closed，一筆 NULL 就會擋掉所有 BUY。
        cfg = self._load_config()
        lookback_n = int(cfg["protection_drawdown_lookback_n"])
        threshold = float(cfg["protection_max_drawdown_alpha_pct"])

        # Scoped to BUY-side signals: pooling BUY and SELL outcomes into one
        # alpha average measured the wrong thing entirely.
        # 限定買方 signal：把買賣結果混在一起算 alpha 是衡量錯對象。
        stmt = text("""
            SELECT alpha_pct FROM decision_outcomes
            WHERE user_id = :user_id AND resolved_at IS NOT NULL
              AND alpha_pct IS NOT NULL
              AND UPPER(signal) IN :signals
            ORDER BY resolved_at DESC LIMIT :n
        """).bindparams(bindparam("signals", expanding=True))

        with self.engine.connect() as conn:
            rows = conn.execute(stmt, {
                "user_id": self.user_id, "n": lookback_n, "signals": list(BUY_SIDE_SIGNALS),
            }).fetchall()
        if len(rows) < 3:
            return None  # not enough resolved history to judge
        avg_alpha = sum(float(r[0]) for r in rows) / len(rows)
        if avg_alpha < threshold:
            return (
                f"Global drawdown halt: last {len(rows)} resolved BUY decisions averaged "
                f"{avg_alpha:+.2f}% alpha (threshold {threshold}%). "
                "New BUY orders paused pending review."
            )
        return None

    def _check_ticker_cooldown(self, ticker: str) -> Optional[str]:
        cfg = self._load_config()
        cooldown_days = int(cfg["protection_ticker_cooldown_days"])

        stmt = text("""
            SELECT alpha_pct, resolved_at FROM decision_outcomes
            WHERE user_id = :user_id AND ticker = :ticker AND resolved_at IS NOT NULL
              AND alpha_pct IS NOT NULL
              AND UPPER(signal) IN :signals
            ORDER BY resolved_at DESC LIMIT 1
        """).bindparams(bindparam("signals", expanding=True))

        with self.engine.connect() as conn:
            row = conn.execute(stmt, {
                "user_id": self.user_id, "ticker": ticker, "signals": list(BUY_SIDE_SIGNALS),
            }).fetchone()
        if not row or row[0] is None:
            return None
        alpha_pct, resolved_at = float(row[0]), row[1]
        if alpha_pct >= 0:
            return None
        from datetime import datetime, timezone
        if resolved_at.tzinfo is None:
            resolved_at = resolved_at.replace(tzinfo=timezone.utc)
        days_since = (datetime.now(timezone.utc) - resolved_at).days
        if days_since < cooldown_days:
            return (
                f"{ticker} cooldown: last resolved BUY decision lost {alpha_pct:+.2f}% alpha "
                f"{days_since}d ago (cooldown {cooldown_days}d). New BUY paused for this ticker."
            )
        return None

    def _check_consecutive_loss_lockout(self) -> Optional[str]:
        cfg = self._load_config()
        lockout_n = int(cfg["protection_consecutive_loss_lockout_n"])

        stmt = text("""
            SELECT alpha_pct FROM decision_outcomes
            WHERE user_id = :user_id AND resolved_at IS NOT NULL
              AND alpha_pct IS NOT NULL
              AND UPPER(signal) IN :signals
            ORDER BY resolved_at DESC LIMIT :n
        """).bindparams(bindparam("signals", expanding=True))

        with self.engine.connect() as conn:
            rows = conn.execute(stmt, {
                "user_id": self.user_id, "n": lockout_n, "signals": list(BUY_SIDE_SIGNALS),
            }).fetchall()
        if len(rows) < lockout_n:
            return None
        if all(float(r[0]) < 0 for r in rows):
            return (
                f"Consecutive-loss lockout: last {lockout_n} resolved BUY "
                "decisions all lost alpha. New BUY orders paused system-wide pending review."
            )
        return None
