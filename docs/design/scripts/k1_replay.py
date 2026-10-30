"""K1 replay (read-only): feed billed daily LLM spend + NAV into src.services.k1_projection.
Usage: k1_replay.py <llm.csv: day,usd> <nav> <monthly_subscription_usd> <today YYYY-MM-DD>
"""
import sys
from datetime import date, timedelta

from src.services.k1_projection import _ratio_pct, project_k1_clear, trailing_average


def _out(msg: str) -> None:
    sys.stdout.write(msg + "\n")


def main(argv: list) -> None:
    path, nav, sub, today = argv[0], float(argv[1]), float(argv[2]), date.fromisoformat(argv[3])
    hist = {}
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                day, usd = line.strip().split(",")
                hist[date.fromisoformat(day)] = float(usd)
    w30 = sum(hist.get(today - timedelta(days=i), 0.0) for i in range(30))
    _out(f"30d billed ${w30:.2f}; K1 now {_ratio_pct(w30, nav, sub):.2f}% (threshold 3.0)")
    _out(f"break-even annual USD at 3% of NAV: ${nav * 0.03 - sub * 12:.2f}")
    for n in (3, 7, 14):
        a = trailing_average(hist, today, n)
        clr = project_k1_clear(hist, today, nav, 3.0, sub, a)
        _out(f"avg{n}d ${a:.3f}/day -> annualised ${a * 365:.0f}; clears {clr}")
    for r in (0.0, 0.10, 0.135, 0.20):
        clr = project_k1_clear(hist, today, nav, 3.0, sub, r)
        _out(f"flat ${r:.3f}/day (annual ${r * 365:.0f}) -> clears {clr}")


if __name__ == "__main__":
    main(sys.argv[1:])
