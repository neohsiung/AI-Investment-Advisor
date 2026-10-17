"""
Counterfactual rows (shadow proposals, `decision_outcomes.is_counterfactual`) must never feed live
decisions. Every SQL `FROM decision_outcomes` in src/ has to mention `is_counterfactual` in the same
statement, or be listed below with the reason it legitimately reads them.
反事實列（影子提案）不得影響實盤決策：src/ 內每個 `FROM decision_outcomes` 必須在同一語句提到
is_counterfactual，或在下方基準中說明為何必須讀到它們。
"""
import re

from tests.invariants.helpers import SRC, REPO

# path -> number of statements allowed to read the table without filtering. Exact equality: the list
# may only shrink. / 路徑 -> 允許不過濾的語句數；精確比對，只能縮小。
KNOWN_UNFILTERED_READERS = {
    # The resolver must see counterfactual rows too: resolving them is its job.
    "src/services/outcome_reflection_service.py": 1,
    # Pipeline-health probe: a stuck counterfactual row is a real pipeline defect and should alert.
    "src/services/self_ops_service.py": 1,
}

_FROM = re.compile(r"FROM decision_outcomes")


def _unfiltered_counts():
    counts = {}
    for p in sorted(SRC.rglob("*.py")):
        text = p.read_text(encoding="utf-8")
        for m in _FROM.finditer(text):
            end = text.find('"""', m.end())
            stmt = text[m.start(): end if end != -1 else m.end() + 800]
            if "is_counterfactual" not in stmt:
                key = str(p.relative_to(REPO))
                counts[key] = counts.get(key, 0) + 1
    return counts


def test_every_decision_outcomes_reader_handles_counterfactuals():
    now = _unfiltered_counts()
    assert now == KNOWN_UNFILTERED_READERS, (
        f"decision_outcomes readers not handling is_counterfactual: {now} "
        f"(allowed: {KNOWN_UNFILTERED_READERS})"
    )
