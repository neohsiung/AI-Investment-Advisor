"""K1 replay (read-only): feed billed daily LLM spend + NAV into src.services.k1_projection.
Usage: k1_replay.py <llm.csv: day,usd> <nav> <monthly_subscription_usd> <today YYYY-MM-DD>
"""
import sys
from datetime import date
from src.services.k1_projection import project_k1_clear, trailing_average, _ratio_pct

csv, nav, sub, today = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), date.fromisoformat(sys.argv[4])
hist = {date.fromisoformat(a): float(b) for a, b in (l.split(",") for l in open(csv) if l.strip())}
from datetime import timedelta
w30 = sum(hist.get(today - timedelta(days=i), 0.0) for i in range(30))
print(f"30d billed ${w30:.2f}; K1 now {_ratio_pct(w30, nav, sub):.2f}% (threshold 3.0)")
print(f"break-even annual USD at 3% of NAV: ${nav*0.03 - sub*12:.2f}")
for n in (3, 7, 14):
    a = trailing_average(hist, today, n)
    print(f"avg{n}d ${a:.3f}/day -> annualised ${a*365:.0f}; clears {project_k1_clear(hist, today, nav, 3.0, sub, a)}")
for r in (0.0, 0.10, 0.135, 0.20):
    print(f"flat ${r:.3f}/day (annual ${r*365:.0f}) -> clears {project_k1_clear(hist, today, nav, 3.0, sub, r)}")
