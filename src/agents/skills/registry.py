"""
Skill Registry — Dynamic Plugin Discovery.
技能註冊表 — 動態插件發現。

Replaces the hardcoded SKILL_IMPLEMENTATIONS dict with a dynamic
plugin system that discovers implementations via convention:
  - Each skill folder can contain an `impl.py` file
  - Or implementations are registered programmatically

遵循規範:
  - 規範四 (模組化設計): 插件化，獨立可單元測試
  - 規範八 (動態指標原則): 動態發現取代硬編碼
  - 規範十五 (AI-Support First): 聲明式結構化
"""

import importlib
import functools
import json
import logging
import os
from typing import Dict, Callable, Optional, Any

from src.utils.logger import setup_logger

logger = setup_logger("SkillRegistry")


class SkillRegistry:
    """
    Dynamic Skill Registry with plugin discovery.
    具動態插件發現功能的技能註冊表。
    """

    def __init__(self):
        self._implementations: Dict[str, Callable] = {}
        self._builtin_registered = False

    def register(self, name: str, func: Callable) -> None:
        """
        Register a skill implementation by name.
        以名稱註冊技能實作。
        """
        self._implementations[name] = func
        logger.debug(f"SkillRegistry: Registered '{name}'")

    def unregister(self, name: str) -> None:
        """
        Remove a skill implementation (hot-unplug).
        移除技能實作（熱拔除）。
        """
        self._implementations.pop(name, None)

    def get(self, name: str) -> Optional[Callable]:
        """Get a registered skill implementation."""
        return self._implementations.get(name)

    def list_registered(self) -> list:
        """List all registered skill names."""
        return list(self._implementations.keys())

    def has(self, name: str) -> bool:
        """Check if a skill is registered."""
        return name in self._implementations

    def _ensure_builtins(self) -> None:
        """
        Lazy-load built-in skill implementations when first needed.
        在第一次需要時延遲載入內建技能實作。
        """
        if self._builtin_registered:
            return
        self._builtin_registered = True

        # Register built-in skills
        self.register("search_web", _search_web)
        self.register("get_market_data", _get_market_data)
        self.register("get_portfolio", _get_portfolio)
        self.register("investment_skill", _investment_skill)
        self.register("position_sizing", _position_sizing)
        self.register("auto_discover_learning", _auto_discover_learning)
        self.register("get_historical_report", _get_historical_report)
        self.register("strategic_envisioning", _strategic_envisioning)
        self.register("attacker_lens_validation", _attacker_lens_validation)
        self.register("alpha_judgment_synthesis", _alpha_judgment_synthesis)

    def bind_to_agent(self, agent) -> None:
        """
        Bind matching skill implementations to an agent's McpServer.
        將匹配的技能實作綁定到 Agent 的 McpServer。
        """
        from src.tools.mcp_server import McpTool

        self._ensure_builtins()

        if not hasattr(agent, "skill_loader") or not agent.skill_loader.skills:
            return

        user_id = getattr(agent, "user_id", None)

        for name, skill_def in agent.skill_loader.skills.items():
            impl = self._implementations.get(name)
            if impl:
                # Bind user_id via partial
                func = functools.partial(impl, user_id)
                tool = McpTool(
                    name=name, func=func, description=skill_def.description
                )
                agent.register_tool(tool)
                agent.logger.info(f"SkillRegistry: Bound '{name}' to agent.")


# ── Singleton Instance ───────────────────────────────────────

_default_registry = SkillRegistry()


def get_default_registry() -> SkillRegistry:
    """Get the module-level default registry singleton."""
    return _default_registry


# ── Backward Compatible Module-Level Function ────────────────

def bind_skills_to_agent(agent) -> None:
    """
    Backward-compatible entry point (used by BaseAgent.__init__).
    向後兼容的入口（BaseAgent.__init__ 使用）。
    """
    _default_registry.bind_to_agent(agent)


# ── Built-in Skill Implementations ──────────────────────────

def _search_web(user_id: str, query: str) -> str:
    """Executes web search."""
    try:
        from src.services.search_service import InternetSearchService

        svc = InternetSearchService()
        results = svc.search_financial_context(query, max_results=3)
        if not results:
            return "No results found."
        out = ""
        for r in results:
            out += f"- {r.get('title')}: {r.get('snippet')} ({r.get('link')})\n"
        return out
    except Exception as e:
        logger.error(f"Skill search_web failed: {e}")
        return f"Error: {e}"


def _get_market_data(user_id: str, ticker: str) -> str:
    """Fetches market data."""
    try:
        from src.services.market_data_service import MarketDataService

        svc = MarketDataService(user_id=user_id)
        context = svc.get_market_context([ticker], enrich=False)
        if ticker_data := context.get(ticker):
            price_data = ticker_data.get("price_data", {})
            close_prices = price_data.get("close", [])
            price = close_prices[-1] if close_prices else "N/A"
            indicators = ticker_data.get("indicators", {})
            return f"Price: {price}\nIndicators: {indicators}"
        return "No data found."
    except Exception as e:
        logger.error(f"Skill get_market_data failed: {e}")
        return f"Error: {e}"


def _get_portfolio(user_id: str) -> str:
    """Fetches portfolio summary."""
    try:
        from src.repositories.transaction_repository import AlchemyTransactionRepository

        repo = AlchemyTransactionRepository()
        summary = repo.get_holdings_summary(user_id)
        leverage = repo.get_latest_leverage(user_id)
        return f"Leverage: {leverage:.2f}\nHoldings: {summary}"
    except Exception as e:
        logger.error(f"Skill get_portfolio failed: {e}")
        return f"Error: {e}"


def _investment_skill(
    user_id: str,
    timeframe: str = "",
    market_regime: str = "",
    industry: str = "",
    technique: str = "",
) -> str:
    """Queries applicable investment skills based on current context."""
    try:
        from src.services.investment_skill_learning_service import (
            InvestmentSkillLearningService,
        )

        svc = InvestmentSkillLearningService(user_id=user_id)
        skills = svc.get_applicable_skills(
            timeframe=timeframe,
            market_regime=market_regime,
            industry=industry,
            technique=technique,
        )

        if not skills:
            return "No applicable investment skills found for the given context."

        out = f"Found {len(skills)} applicable investment skills:\n\n"
        for s in skills:
            out += f"### {s.get('name', 'Unnamed')}\n"
            out += f"- **Technique**: {s.get('technique', 'N/A')}\n"
            out += f"- **Timeframe**: {s.get('timeframe', 'N/A')}\n"
            out += f"- **Description**: {s.get('description', 'N/A')}\n"
            out += f"- **Usage Count**: {s.get('usage_count', 0)}\n\n"
        return out

    except Exception as e:
        logger.error(f"Skill investment_skill failed: {e}")
        return f"Error: {e}"


def _position_sizing(
    user_id: str,
    ticker: str,
    action: str,
    desired_quantity: float = 0.0,
    intent: str = "auto",
) -> str:
    """Calculates appropriate trade quantity considering holdings, cash ratio, and risk thresholds."""
    import json
    try:
        from src.services.broker_factory import BrokerFactory
        from src.repositories.settings_repository import AlchemySettingsRepository

        broker = BrokerFactory.get_broker(user_id)
        if not broker:
            return json.dumps({"recommended_quantity": 0, "reason": "No broker configured"})

        account = broker.get_account()
        positions = broker.get_positions()

        nlv = account.total_equity if account else 0
        cash = account.available_cash if account else 0
        cash_ratio_before = (cash / nlv) if nlv > 0 else 0

        # Find actual holding for this ticker
        actual_holding = 0.0
        for p in positions:
            if _is_ticker_match(ticker, p.symbol):
                actual_holding += p.quantity

        settings = AlchemySettingsRepository()
        max_pct = float(settings.get(user_id, "max_single_position_pct") or 0.10)
        min_amount = float(settings.get(user_id, "min_trade_amount") or 10.0)

        action_upper = action.upper()
        reason = ""

        if action_upper == "SELL":
            if actual_holding <= 0:
                return json.dumps({
                    "recommended_quantity": 0,
                    "actual_holding": 0,
                    "cash_ratio_before": round(cash_ratio_before, 4),
                    "reason": f"No active position found for {ticker}. Cannot sell.",
                })

            if intent == "full_close":
                recommended = actual_holding
                reason = f"Full close of {ticker} position ({actual_holding} units)"
            elif intent == "partial_reduce":
                recommended = min(desired_quantity, actual_holding) if desired_quantity > 0 else actual_holding * 0.5
                reason = f"Partial reduce: {recommended} of {actual_holding} units"
            else:  # auto
                if desired_quantity > 0:
                    recommended = min(desired_quantity, actual_holding)
                    if desired_quantity > actual_holding:
                        reason = f"Clamped SELL from {desired_quantity} to {actual_holding} (actual holding)"
                    else:
                        reason = f"SELL {recommended} of {actual_holding} units"
                else:
                    recommended = actual_holding
                    reason = f"No quantity specified, defaulting to full close ({actual_holding} units)"

        elif action_upper == "BUY":
            max_amount = nlv * max_pct if nlv > 0 else 0
            recommended = desired_quantity if desired_quantity > 0 else min_amount

            if recommended > cash:
                reason += f"Clamped from ${recommended:.2f} to ${cash:.2f} (available cash). "
                recommended = cash
            if recommended > max_amount and max_amount > 0:
                reason += f"Clamped to ${max_amount:.2f} ({max_pct*100:.0f}% of NLV ${nlv:.2f}). "
                recommended = max_amount
            if recommended < min_amount:
                reason += f"Below minimum ${min_amount:.2f}. "
                recommended = 0
            if not reason:
                reason = f"Within limits (max position {max_pct*100:.0f}% of NLV)"
        else:
            return json.dumps({"recommended_quantity": 0, "reason": f"Unknown action: {action}"})

        # Estimate post-trade cash ratio
        cash_after = cash
        if action_upper == "BUY":
            cash_after = cash - recommended
        # For SELL, we don't know the price precisely, so skip estimate
        cash_ratio_after = (cash_after / nlv) if nlv > 0 else 0

        return json.dumps({
            "recommended_quantity": round(recommended, 4),
            "actual_holding": round(actual_holding, 4),
            "cash_ratio_before": round(cash_ratio_before, 4),
            "cash_ratio_after_estimate": round(cash_ratio_after, 4),
            "reason": reason.strip(),
        })

    except Exception as e:
        logger.error(f"Skill position_sizing failed: {e}")
        return json.dumps({"recommended_quantity": 0, "reason": f"Error: {e}"})


def _is_ticker_match(t1: str, t2: str) -> bool:
    """Check if two ticker symbols match, ignoring eToro suffixes."""
    if not t1 or not t2:
        return False
    def normalize(s):
        s = s.strip().upper()
        for suffix in [".US", ".RTH", ".EXT", ".L", ".UK"]:
            if s.endswith(suffix):
                return s[: -len(suffix)]
        return s
    return normalize(t1) == normalize(t2)


def _auto_discover_learning(user_id: str) -> str:
    """
    Trigger auto-discovery investment skill learning.
    自動搜尋最佳投資文章並萃取為技能。
    """
    try:
        from src.services.investment_skill_learning_service import (
            InvestmentSkillLearningService,
        )

        svc = InvestmentSkillLearningService(user_id=user_id)
        result = svc.run_daily_learning()  # No content = triggers auto-discovery
        return json.dumps(result, ensure_ascii=False, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def _get_historical_report(user_id: str, report_type: str = "WeeklyWorkflow", weeks_ago: int = 1) -> str:
    """
    Fetches the historical investment report for the given report type.
    """
    import json
    try:
        from src.data.database import get_db_engine
        from sqlalchemy import text
        import pandas as pd
        
        offset = max(0, weeks_ago - 1)
        engine = get_db_engine()
        with engine.connect() as conn:
            query = text("""
                SELECT created_at, content 
                FROM reports 
                WHERE user_id = :uid AND report_type = :rtype
                ORDER BY created_at DESC 
                LIMIT 1 OFFSET :offset
            """)
            df = pd.read_sql(query, conn, params={"uid": user_id, "rtype": report_type, "offset": offset})
            
            if df.empty:
                return f"No historical ({report_type}) report found from {weeks_ago} weeks ago."
                
            record = df.iloc[0]
            date_str = str(record['created_at'])
            content = str(record['content'])
            return f"Report Date: {date_str}\\n\\nContent:\\n{content}"
    except Exception as e:
        logger.error(f"Skill get_historical_report failed: {e}")
        return json.dumps({"error": str(e)})


def _strategic_envisioning(user_id: str) -> str:
    """Returns the Strategic Envisioning analytical framework instructions."""
    import pathlib
    try:
        path = pathlib.Path(__file__).parent / "strategic_envisioning" / "SKILL.md"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Skill strategic_envisioning failed: {e}")
        return f"Error: {e}"


def _attacker_lens_validation(user_id: str) -> str:
    """Returns the Attacker's Lens Validation analytical framework instructions."""
    import pathlib
    try:
        path = pathlib.Path(__file__).parent / "attacker_lens_validation" / "SKILL.md"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Skill attacker_lens_validation failed: {e}")
        return f"Error: {e}"


def _alpha_judgment_synthesis(user_id: str) -> str:
    """Returns the Alpha Judgment & Synthesis analytical framework instructions."""
    import pathlib
    try:
        path = pathlib.Path(__file__).parent / "alpha_judgment_synthesis" / "SKILL.md"
        return path.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"Skill alpha_judgment_synthesis failed: {e}")
        return f"Error: {e}"

