"""
Enforces the fail-silent rule on decision-path modules.
對決策路徑模組強制執行「不得靜默失敗」規則。

Rule (AGENTS.md constraint #0, wiki/05_Quality_Assurance/靜默失敗防治):
an `except` on a decision path must not BOTH log below `warning` AND return a
value that looks like a real answer. Pick one.

Why this test exists rather than just the doc: every serious incident in this
system has been a silent one, and a rule nobody can run is a rule that decays.

  - three-day outage, every monitor green (dispatcher reported success)
  - confidence scores that were hashes of the ticker (LLM failure -> plausible
    substitute, logged at debug)
  - three BUY guards inert because their table was empty
  - momentum factor pinned at neutral 5.0 by a swallowed constructor error

規則：決策路徑的 except 不得同時「以低於 warning 記錄」與「回傳看似真實的答案」。
本測試存在的理由是——無法執行的規則會腐敗；本系統每一次重大事故都是靜默的。
"""
import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Modules where a wrong-but-plausible value moves money, blocks a guard, or
# hides an outage. Deliberately a short list — the rule is about decision
# paths, not about every file in the repo.
# 錯誤但看似合理的值會在此類模組中動用資金、癱瘓護欄或掩蓋故障。
DECISION_PATH_MODULES = [
    "src/services/automated_trading_service.py",
    "src/services/sentinel_service.py",
    "src/services/trading_protections_service.py",
    "src/services/confidence_compositor_service.py",
    "src/services/exit_compositor_service.py",
    "src/services/outcome_reflection_service.py",
    "src/services/strategy_validation_service.py",
    "src/services/capital_policy.py",
    "src/services/self_ops_service.py",
    "src/infrastructure/risk_manager.py",
    "src/infrastructure/llm/llm_config_chain.py",
]

QUIET_LOG_METHODS = {"debug"}

# (module, function, reason). A waiver must say why the silence is correct.
# 豁免必須寫明「為何這裡的靜默是正確的」。
ALLOWLIST: set[tuple[str, str]] = set()

WAIVER_REASONS = {
    # (module, function): reason
}


# Only broad handlers are in scope. `except ValueError` around an int() parse,
# or `except RuntimeError` to detect a running asyncio loop, are deliberate
# control flow with a known failure mode — they are not "swallowing", and
# flagging them trains people to ignore this test.
# 只針對廣泛攔截。針對 int() 的 except ValueError、或用來偵測 asyncio loop 的
# except RuntimeError 屬刻意的控制流程，把它們標為違規只會讓人學會忽略此測試。
BROAD_EXCEPTIONS = {"Exception", "BaseException"}


def _is_broad(handler) -> bool:
    if handler.type is None:
        return True  # bare `except:`
    names = []
    node = handler.type
    if isinstance(node, ast.Tuple):
        names = [n.id for n in node.elts if isinstance(n, ast.Name)]
    elif isinstance(node, ast.Name):
        names = [node.id]
    return any(n in BROAD_EXCEPTIONS for n in names)


def _iter_handlers(tree, source_lines):
    """Yield (function_name, ExceptHandler) for every broad except."""
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.ExceptHandler) and _is_broad(sub):
                yield node.name, sub


def _logs_quietly(handler) -> bool:
    """True when the handler's only logging is debug-level (or absent)."""
    log_levels = set()
    for node in ast.walk(handler):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in ("logger", "log", "logging"):
                log_levels.add(func.attr)
    if not log_levels:
        return True  # bare pass / no logging at all
    return log_levels.issubset(QUIET_LOG_METHODS)


def _returns_a_plausible_value(handler) -> bool:
    """
    True when the handler returns something that could pass for a real answer.

    `return`, `return None` and `raise` are honest — they say "no answer".
    A literal number, string, dict, list or a call result is what gets
    mistaken for a real reading.
    return / return None / raise 都是誠實的；回傳數值、字串、dict、list 或呼叫
    結果才是會被誤認為真實量測的東西。
    """
    for node in ast.walk(handler):
        if not isinstance(node, ast.Return):
            continue
        value = node.value
        if value is None:
            continue
        if isinstance(value, ast.Constant) and value.value is None:
            continue
        # An empty container is a defensible "nothing found".
        if isinstance(value, (ast.List, ast.Dict, ast.Tuple, ast.Set)) and not (
            getattr(value, "elts", None) or getattr(value, "keys", None)
        ):
            continue
        if isinstance(value, ast.Constant) and value.value in ("", False):
            continue
        return True
    return False


def _collect_violations(rel_path: str):
    path = REPO_ROOT / rel_path
    if not path.exists():
        pytest.skip(f"{rel_path} not present")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = path.read_text(encoding="utf-8").splitlines()

    violations = []
    for func_name, handler in _iter_handlers(tree, lines):
        if (rel_path, func_name) in ALLOWLIST:
            continue
        if _logs_quietly(handler) and _returns_a_plausible_value(handler):
            violations.append((func_name, handler.lineno))
    return violations


@pytest.mark.parametrize("rel_path", DECISION_PATH_MODULES)
def test_decision_path_has_no_silent_substitution(rel_path):
    """
    An except may be quiet, or it may substitute a value. Not both.
    except 可以安靜，也可以代換值，但不能兩者兼具。
    """
    violations = _collect_violations(rel_path)
    assert not violations, (
        f"{rel_path}: {len(violations)} except block(s) both swallow to debug/pass "
        f"AND return a plausible value — "
        f"{', '.join(f'{fn}() line {ln}' for fn, ln in violations)}.\n"
        f"Either log at warning or above, or let the error propagate. "
        f"If you must substitute a default, mark it (_fallback_reason / "
        f"_insufficient_data) and surface the mark to the caller. "
        f"See wiki/05_Quality_Assurance/靜默失敗防治-Fail-Silent-Prevention.md"
    )


class TestTheDetectorItself:
    """
    A policy test that cannot fail is worse than no test — it grants false
    confidence. These pin the detector against hand-written samples.
    無法失敗的政策測試比沒有測試更糟，因為它給出虛假的信心。
    """

    @staticmethod
    def _handler(src):
        tree = ast.parse(src)
        return next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))

    def test_flags_debug_plus_substituted_number(self):
        h = self._handler(
            "def f():\n"
            "    try:\n        x()\n"
            "    except Exception as e:\n"
            "        logger.debug(e)\n        return 5.0\n"
        )
        assert _logs_quietly(h) and _returns_a_plausible_value(h)

    def test_flags_bare_pass_with_substitution(self):
        h = self._handler(
            "def f():\n"
            "    try:\n        x()\n"
            "    except Exception:\n"
            "        return {'score': 5}\n"
        )
        assert _logs_quietly(h) and _returns_a_plausible_value(h)

    def test_allows_warning_plus_substitution(self):
        """Loud substitution is permitted — that is the documented escape."""
        h = self._handler(
            "def f():\n"
            "    try:\n        x()\n"
            "    except Exception as e:\n"
            "        logger.warning(e)\n        return 5.0\n"
        )
        assert not (_logs_quietly(h) and _returns_a_plausible_value(h))

    def test_allows_quiet_return_none(self):
        """Quiet honesty is permitted — None says 'no answer'."""
        h = self._handler(
            "def f():\n"
            "    try:\n        x()\n"
            "    except Exception as e:\n"
            "        logger.debug(e)\n        return None\n"
        )
        assert not (_logs_quietly(h) and _returns_a_plausible_value(h))

    def test_allows_quiet_reraise(self):
        h = self._handler(
            "def f():\n"
            "    try:\n        x()\n"
            "    except Exception:\n"
            "        raise\n"
        )
        assert not _returns_a_plausible_value(h)

    def test_empty_container_is_not_a_plausible_value(self):
        h = self._handler(
            "def f():\n"
            "    try:\n        x()\n"
            "    except Exception as e:\n"
            "        logger.debug(e)\n        return []\n"
        )
        assert not _returns_a_plausible_value(h)


def test_every_waiver_states_a_reason():
    """
    An allowlist without reasons decays into a place to hide violations.
    沒有理由的白名單會退化成藏匿違規的地方。
    """
    undocumented = ALLOWLIST - set(WAIVER_REASONS)
    assert not undocumented, f"waivers missing a reason: {sorted(undocumented)}"
