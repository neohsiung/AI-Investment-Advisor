"""config/mission.yaml is valid and its numbers are not copied into code.
config/mission.yaml 必須有效，且其數字不得被複製進程式碼。"""
import re

from src.config.mission import load_mission
from tests.invariants.helpers import REPO, py_files, rel


def test_mission_loads_and_has_seven_kill_criteria():
    m = load_mission()
    assert m.objective.benchmark == "SPY"
    assert m.objective.default_allocation == "benchmark"
    assert [k.id for k in m.kill_criteria] == [f"K{i}" for i in range(1, 8)]
    assert m.invariants.single_order_executor is True
    assert m.promotion.min_deflated_sharpe >= 0.95


def test_agent_entry_docs_point_to_mission_file():
    text = (REPO / "AGENTS.md").read_text(encoding="utf-8")
    assert "config/mission.yaml" in text, "AGENTS.md must reference config/mission.yaml (the mission single source of truth)"


def test_mission_thresholds_not_duplicated_in_code():
    """Decision code must read limits via load_mission(), never re-declare them as constants."""
    pat = re.compile(r"\b(MAX_NONSAFETY_SELL\w*|MIN_BENCHMARK_WEIGHT\w*|MAX_ANNUAL_TURNOVER\w*|MIN_DEFLATED_SHARPE\w*)\s*=")
    offenders = [rel(p) for p in py_files() if p.name != "mission.py" and pat.search(p.read_text(encoding="utf-8"))]
    assert offenders == [], f"mission constants re-declared outside src/config/mission.py: {offenders}"
