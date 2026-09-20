#!/usr/bin/env python3
"""
Compare TimesFM against the numpy random-walk baseline on real price history.

Why this exists: TimesFM costs ~900MB of PyTorch and ~1.5GB of RSS, feeds
exactly one consumer (market_data_service's agent context), and has never been
backtested in this repo. "It's a 200M-parameter foundation model" is not
evidence that it beats a random walk on daily equity closes at a 5-day horizon —
for that horizon the random walk is a genuinely strong baseline.

Two metrics, both on held-out data:

  coverage    fraction of realised prices landing inside the q10-q90 band.
              Should be ~0.80. Below that the band is overconfident; well above
              it the band is so wide it says nothing.

  pinball     average pinball (quantile) loss across q10/q50/q90. Lower is
              better. This is the metric that actually rewards a sharper band,
              and it is the one to compare the two methods on.

Usage:
    python scripts/backtest_forecast.py                     # default tickers
    python scripts/backtest_forecast.py AAPL NVDA --horizon 5

若 TimesFM 在 pinball loss 上沒有明顯優於基準，就不值得那 900MB。
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.getcwd())


def pinball_loss(actual: float, predicted: float, tau: float) -> float:
    delta = actual - predicted
    return max(tau * delta, (tau - 1) * delta)


def evaluate(closes, horizon, method, window=250, step=5):
    """Walk forward through the series, forecasting from each window."""
    os.environ["FORECAST_METHOD"] = method
    # Re-import so the module-level method switch is picked up cleanly.
    from src.services import forecast_service

    covered = total = 0
    losses = []
    used_method = None

    for start in range(0, len(closes) - window - horizon, step):
        history = closes[start:start + window]
        future = closes[start + window:start + window + horizon]
        if len(future) < horizon:
            break

        fc = forecast_service.forecast("BT", history, horizon=horizon)
        if fc is None:
            continue
        used_method = fc.method

        for h in range(horizon):
            actual = future[h]
            if fc.q10[h] <= actual <= fc.q90[h]:
                covered += 1
            total += 1
            losses.append(pinball_loss(actual, fc.q10[h], 0.10))
            losses.append(pinball_loss(actual, fc.q50[h], 0.50))
            losses.append(pinball_loss(actual, fc.q90[h], 0.90))

    if not total:
        return None
    return {
        "method": used_method or method,
        "coverage": covered / total,
        "pinball": sum(losses) / len(losses),
        "points": total,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tickers", nargs="*", default=["AAPL", "NVDA", "JPM", "NKE"])
    ap.add_argument("--horizon", type=int, default=5)
    ap.add_argument("--window", type=int, default=250)
    args = ap.parse_args()

    from src.services.market_data_service import MarketDataService

    # Uses the project's own provider stack (Polygon/Tiingo/FMP/... with the
    # keys already in the settings table) rather than yfinance directly —
    # yfinance's Yahoo endpoint is frequently broken, and the provider chain is
    # what the application actually reads prices through anyway.
    # 改用專案自身的 provider 串鏈（金鑰已在 settings 表），不直接依賴 yfinance。
    svc = MarketDataService()

    print(f"horizon={args.horizon}d  window={args.window}d\n")
    header = f"{'ticker':<8}{'method':<14}{'coverage':>10}{'pinball':>12}{'points':>9}"
    print(header)
    print("-" * len(header))

    totals = {}
    for ticker in args.tickers:
        try:
            ohlcv = svc.get_ohlcv(ticker, days=args.window + args.horizon + 400)
            closes = [float(v) for v in (ohlcv or {}).get("close", []) if v is not None]
        except Exception as exc:
            print(f"{ticker:<8}fetch failed: {exc}")
            continue
        if len(closes) < args.window + args.horizon + 10:
            print(f"{ticker:<8}not enough history ({len(closes)} closes)")
            continue

        for method in ("random_walk", "auto"):
            res = evaluate(closes, args.horizon, method, window=args.window)
            if not res:
                continue
            print(f"{ticker:<8}{res['method']:<14}{res['coverage']:>10.3f}"
                  f"{res['pinball']:>12.4f}{res['points']:>9}")
            t = totals.setdefault(res["method"], {"cov": [], "pin": []})
            t["cov"].append(res["coverage"])
            t["pin"].append(res["pinball"])

    print("-" * len(header))
    for method, t in totals.items():
        cov = sum(t["cov"]) / len(t["cov"])
        pin = sum(t["pin"]) / len(t["pin"])
        print(f"{'MEAN':<8}{method:<14}{cov:>10.3f}{pin:>12.4f}")

    print("\nRead it like this: coverage should sit near 0.80 for both. The"
          "\ndecision metric is pinball loss — if TimesFM is not clearly lower,"
          "\nit is not buying anything for its ~900MB and should stay opt-in.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
