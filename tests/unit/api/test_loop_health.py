"""
Unit tests for the loop-health aggregation endpoint (B-P3.2).
Tests call the module-level helper functions directly against a mocked
SQLAlchemy connection — no FastAPI TestClient needed (matches the router's
own circular-import-safe import convention, see test_auth_exchange.py).
"""
from unittest.mock import MagicMock

import src.api.v1.router  # noqa: F401 - establishes safe import order (see test_auth_exchange.py)
from src.api.v1.endpoints.loop_health import (
    _learning_metrics, _self_ops_metrics, _feedback_metrics,
)


def _mock_conn(calls):
    """
    `calls` is an ordered list matching the exact sequence of
    conn.execute(...).fetchone()/.fetchall() calls the real function under
    test makes. Each item is ("fetchone", value) or ("fetchall", value).
    """
    conn = MagicMock()
    remaining = list(calls)

    def execute(query, params=None):
        kind, value = remaining.pop(0)
        result = MagicMock()
        if kind == "fetchone":
            result.fetchone.return_value = value
        else:
            result.fetchall.return_value = value
        return result

    conn.execute.side_effect = execute
    return conn


class TestLearningMetrics:
    def test_resolution_rate_computed(self):
        decisions = MagicMock(total=10, resolved=6)
        rule_rows = [MagicMock(status="active", n=3, avg_score=0.5), MagicMock(status="retired", n=2, avg_score=-1.0)]
        conn = _mock_conn([("fetchone", decisions), ("fetchall", rule_rows)])

        result = _learning_metrics(conn, "u1")

        assert result["decisions_total"] == 10
        assert result["decisions_resolved"] == 6
        assert result["resolution_rate"] == 0.6
        assert result["rules_by_status"] == {"active": 3, "retired": 2}
        assert result["avg_active_rule_score"] == 0.5

    def test_zero_decisions_no_division_error(self):
        decisions = MagicMock(total=0, resolved=0)
        conn = _mock_conn([("fetchone", decisions), ("fetchall", [])])

        result = _learning_metrics(conn, "u1")

        assert result["resolution_rate"] is None
        assert result["avg_active_rule_score"] is None


class TestSelfOpsMetrics:
    def test_aggregates_breaches_remediation_and_cost(self):
        remediation_rows = [MagicMock(tier="T1", n=5), MagicMock(tier="T3", n=1)]
        conn = _mock_conn([
            ("fetchone", (2,)),
            ("fetchall", remediation_rows),
            ("fetchone", (12.5,)),
        ])

        result = _self_ops_metrics(conn, "u1")

        assert result["breaches_this_week"] == 2
        assert result["remediation_by_tier"] == {"T1": 5, "T3": 1}
        assert result["weekly_cost_usd"] == 12.5
        assert result["weekly_budget_usd"] == 30.0


class TestFeedbackMetrics:
    def test_approval_rate_and_reason_capture(self):
        by_decision_rows = [MagicMock(decision="approved", n=7), MagicMock(decision="rejected", n=3)]
        reason_capture = MagicMock(with_reason=2, total=3)
        pref_row = MagicMock(sample_size=42, risk_appetite_score=0.4)
        conn = _mock_conn([
            ("fetchall", by_decision_rows),
            ("fetchone", reason_capture),
            ("fetchone", pref_row),
        ])

        result = _feedback_metrics(conn, "u1")

        assert result["approval_rate"] == 0.7
        assert result["by_decision"] == {"approved": 7, "rejected": 3}
        assert result["rejection_reason_capture_rate"] == round(2 / 3, 3)
        assert result["preference_sample_size"] == 42
        assert result["risk_appetite_score"] == 0.4

    def test_no_history_returns_none_rates(self):
        reason_capture = MagicMock(with_reason=0, total=0)
        conn = _mock_conn([
            ("fetchall", []),
            ("fetchone", reason_capture),
            ("fetchone", None),
        ])

        result = _feedback_metrics(conn, "u1")

        assert result["approval_rate"] is None
        assert result["rejection_reason_capture_rate"] is None
        assert result["preference_sample_size"] == 0
        assert result["risk_appetite_score"] is None
