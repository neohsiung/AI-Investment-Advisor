"""
Settings families registry — keeps switches / modes / caps from piling up one work package at a time.
設定家族註冊表——避免開關、模式與上限逐個工作包無聲堆積。

The registry (config/settings_families.yaml) says which keys belong together, which one is canonical and how they
relate (e.g. "finnhub_poll_enabled is inert when event_llm_mode=off"). This test enforces:
  (i)   the registry is well formed and every member exists in the schema (no key in two families);
  (ii)  a ratchet: every schema key matching the switch/mode/cap pattern is registered or in the shrinking baseline;
  (iii) the dead duplicate `strategy_evolution_enabled` is gone;
  (iv)  the evolution gate family defaults all agree (all off);
  (v)   the hidden finnhub -> event_llm_mode coupling is documented in the help text;
  (vi)  the order-cap helper reads the schema default and never returns a larger number on failure.
"""
import importlib.util
import re
from pathlib import Path
from unittest.mock import MagicMock

import yaml

REPO = Path(__file__).resolve().parents[2]
SCHEMA = REPO / "config" / "settings_schema.yaml"
REGISTRY = REPO / "config" / "settings_families.yaml"


def _schema_entries():
    return {e["key"]: e for e in yaml.safe_load(SCHEMA.read_text(encoding="utf-8"))["settings"]}


def _registry():
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["families"]


def _pattern():
    spec = importlib.util.spec_from_file_location("settings_inventory", REPO / "scripts" / "settings_inventory.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.KEY_PATTERN


# Today's unregistered switch/mode/cap keys. This set may only SHRINK: register a key in
# config/settings_families.yaml and delete it here. Never add to it.
# 目前尚未登記的開關/模式/上限鍵；只能縮小，不得新增。
KNOWN_UNREGISTERED = frozenset({
    "adaptive_council_meta_learning_enabled",
    "adaptive_intelligence_enabled",
    "alloc_cluster_cap",
    "alloc_sector_cap",
    "autonomous_confidence_boost_enabled",
    "autonomous_exit_enabled",
    "autonomous_reporting_mode",
    "channel_discord_enabled",
    "channel_email_enabled",
    "channel_google_chat_enabled",
    "channel_line_enabled",
    "channel_messenger_enabled",
    "channel_slack_enabled",
    "channel_telegram_enabled",
    "circuit_breaker_enabled",
    "cognitive_blindspot_detection_enabled",
    "convex_sharpe_max_weight_cap",
    "council_contagion_enabled",
    "council_counterfactual_enabled",
    "council_diversity_enabled",
    "council_memory_retrieval_enabled",
    "debate_termination_enabled",
    "decay_rebalance_enforce_friction_hurdle",
    "enable_alpha_spread_bidding",
    "enable_bayesian_hmm_entropy_guard",
    "enable_bayesian_hmm_factor_allocation",
    "enable_bayesian_jump_guard",
    "enable_breakout_volume_filter",
    "enable_convex_conviction_sizing",
    "enable_convex_sharpe_optimization",
    "enable_cross_sector_beta_damping",
    "enable_cross_sector_harvest_rebalance",
    "enable_cross_sector_momentum_injection",
    "enable_dark_pool_pricing",
    "enable_deterministic_council_fallback",
    "enable_dynamic_fill_quality_tracking",
    "enable_dynamic_kelly_sizing",
    "enable_dynamic_risk_parity",
    "enable_earnings_blackout_guard",
    "enable_etoro",
    "enable_event_graph_auto_trim",
    "enable_factor_auto_healing",
    "enable_factor_drift_guard",
    "enable_factor_genetic_evolution",
    "enable_factor_interaction_terms",
    "enable_factor_orthogonal_attribution",
    "enable_factor_orthogonalization",
    "enable_factor_stress_testing",
    "enable_fixed_stops",
    "enable_friction_aware_tranche_sizing",
    "enable_futu",
    "enable_fx_dynamic_hedging",
    "enable_hard_token_budget_guard",
    "enable_ibkr",
    "enable_inverse_etf_hedge",
    "enable_iv_surface_skew_hedging",
    "enable_kalman_pairs_cointegration",
    "enable_live_spread_feed",
    "enable_macro_calendar_blackout_guard",
    "enable_macro_event_causal_graph",
    "enable_macro_trend_long_only_lock",
    "enable_macro_volatility_hedging",
    "enable_market_open_cash_deployment",
    "enable_microstructure_ofi_defense",
    "enable_microstructure_spoofing_shield",
    "enable_net_alpha_attribution",
    "enable_option_gamma_exposure_gex",
    "enable_pyramiding",
    "enable_ratchet_take_profit",
    "enable_rebound_cash_reinvestment",
    "enable_rl_execution_sor",
    "enable_sector_drift_guard",
    "enable_sentinel_zero_llm_mode",
    "enable_slippage_guard",
    "enable_staggered_dip_buying",
    "enable_staggered_fills_reconciliation",
    "enable_staggered_moc_conversion",
    "enable_staggered_order_stalking",
    "enable_stagnation_pruning",
    "enable_tactical_decay_rebalancing",
    "enable_tactical_factor_replay_tuning",
    "enable_tactical_factor_rotation",
    "enable_trailing_stops",
    "enable_tranche_auto_healing",
    "enable_trend_hysteresis_lockout",
    "enable_unified_risk_gateway",
    "enable_universe_momentum_pruning",
    "enable_vpin_toxicity_guard",
    "etoro_mode",
    "event_bias_enabled",
    "evolution_annealing_enabled",
    "evt_tail_risk_enabled",
    "execution_feedback_enabled",
    "external_mcp_enabled",
    "factor_ensemble_enabled",
    "gex_negative_volatility_damping_cap",
    "hmm_regime_enabled",
    "inference_cost_hurdle_enabled",
    "liquidity_hunt_guard_enabled",
    "macro_surprise_enabled",
    "min_friction_hurdle_pct",
    "pyramid_screener_enabled",
    "rebalance_risk_diversification_enabled",
    "risk_parity_max_weight_cap",
    "shadow_auto_rotation_enabled",
    "slippage_compensator_enabled",
    "sor_enabled",
    "source_alpha_vantage_enabled",
    "source_finnhub_enabled",
    "source_fmp_enabled",
    "source_polygon_enabled",
    "source_tavily_enabled",
    "source_tiingo_enabled",
    "source_yfinance_enabled",
    "telemetry_enabled",
    "tiered_approval_enabled",
    "toxicity_detector_enabled",
    "universe_auto_refresh_enabled",
    "volatility_spillover_enabled",
})

REQUIRED_FAMILIES = {
    "evolution_gate", "event_analysis", "proposal_validator", "emergency_protocol",
    "rotation", "parking", "order_caps", "capital",
}


def test_registry_parses_and_members_exist():
    fams = _registry()
    ids = [f["id"] for f in fams]
    assert len(ids) == len(set(ids)), "duplicate family id"
    assert REQUIRED_FAMILIES <= set(ids)
    schema = _schema_entries()
    seen = {}
    for f in fams:
        for field in ("id", "purpose_en", "purpose_zh", "canonical", "members", "notes"):
            assert f.get(field), f"family {f.get('id')} missing {field}"
        assert f["canonical"] in f["members"], f"{f['id']}: canonical must be a member"
        for k in f["members"]:
            assert k in schema, f"{f['id']}: member {k} not in settings_schema.yaml"
            assert k not in seen, f"{k} is in two families: {seen[k]} and {f['id']}"
            seen[k] = f["id"]
    order = next(f for f in fams if f["id"] == "order_caps")
    assert order.get("precedence"), "order_caps must state its precedence"
    assert "parking" in " ".join(map(str, order["precedence"])).lower()


def test_unregistered_switches_ratchet():
    registered = {k for f in _registry() for k in f["members"]}
    pat = _pattern()
    unregistered = {k for k in _schema_entries() if pat.search(k) and k not in registered}
    new = unregistered - KNOWN_UNREGISTERED
    assert not new, (
        f"New switch/mode/cap settings not in a family: {sorted(new)}. Register each in "
        "config/settings_families.yaml (join an existing family or add one) with a purpose and its relationship "
        "to the neighbouring switches. Do NOT add it to KNOWN_UNREGISTERED."
    )
    stale = KNOWN_UNREGISTERED - unregistered
    assert not stale, f"Now registered or removed - delete from KNOWN_UNREGISTERED (it may only shrink): {sorted(stale)}"


def test_legacy_strategy_evolution_enabled_removed():
    assert "strategy_evolution_enabled" not in _schema_entries()
    hits = [str(p.relative_to(REPO)) for p in (REPO / "src").rglob("*.py")
            if "strategy_evolution_enabled" in p.read_text(encoding="utf-8")]
    assert not hits, f"strategy_evolution_enabled still referenced in src/: {hits}"


def test_evolution_gate_defaults_agree_all_off():
    schema = _schema_entries()
    fam = next(f for f in _registry() if f["id"] == "evolution_gate")
    assert fam["canonical"] == "enable_autonomous_evolution_beat"
    for k in fam["members"]:
        assert schema[k]["default"] is False, f"{k} default must be off"


def test_finnhub_poll_help_mentions_event_llm_mode():
    e = _schema_entries()["finnhub_poll_enabled"]
    assert "event_llm_mode" in e["help_en"] and "event_llm_mode" in e["help_zh"]


def test_order_cap_helper_default_and_fallback():
    from unittest.mock import patch

    from src.config.settings_schema import schema_default
    from src.services.order_cap_policy import single_order_cap_usd

    default = float(_schema_entries()["batch_deploy_max_order_usd"]["default"])
    assert schema_default("batch_deploy_max_order_usd") == default

    svc = MagicMock()
    svc.get_setting.return_value = None  # absent
    assert single_order_cap_usd(svc, "u1") == default

    svc.get_setting.return_value = 40
    assert single_order_cap_usd(svc, "u1") == 40.0

    for bad in (0, -5, "abc", float("nan")):
        svc.get_setting.return_value = bad
        with patch("src.services.order_cap_policy.logger") as lg:
            assert single_order_cap_usd(svc, "u1") == default
            assert lg.warning.called, f"no warning for {bad!r}"

    svc.get_setting.side_effect = RuntimeError("db down")
    with patch("src.services.order_cap_policy.logger") as lg:
        assert single_order_cap_usd(svc, "u1") == default
        assert lg.warning.called


def test_order_cap_readers_use_the_helper():
    """No reader repeats the literal default for batch_deploy_max_order_usd."""
    offenders = []
    for p in (REPO / "src").rglob("*.py"):
        if p.name == "order_cap_policy.py":
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "batch_deploy_max_order_usd" in line and re.search(r"get_setting|_setting_float", line):
                offenders.append(f"{p.relative_to(REPO)}:{i}")
    assert not offenders, f"read batch_deploy_max_order_usd via order_cap_policy.single_order_cap_usd: {offenders}"
