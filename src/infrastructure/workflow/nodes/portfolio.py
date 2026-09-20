"""
Code-node implementations for the portfolio workflows.

These functions were defined inline in portfolio_dag.py alongside the imperative
`CodeNode(name=..., func=..., input_keys=[...])` wiring. Splitting them out is
what lets the wiring move into YAML: the graph shape becomes data, while the
deterministic Python stays Python.

Each `@register_node("name")` makes the function referenceable as
`type: code` / `ref: name` from a workflow file — and only functions decorated
here are reachable, so a YAML edit cannot name an arbitrary import path.

這些函式原本與 portfolio_dag.py 的命令式接線寫在一起。抽出後，圖的形狀變成資料
（YAML），確定性的 Python 仍留在 Python。只有在此註冊的函式能被 YAML 指名。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any, Dict, List, Tuple

from src.infrastructure.workflow.nodes import register_node

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────
# Deterministic Helper Functions for CodeNodes
# ──────────────────────────────────────────────────────────────────────

@register_node("filter_holdings")
def filter_holdings(portfolio: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deterministic CodeNode: filters holdings to only include valid items."""
    logger.info(f"DAG Node (filter_holdings): Input portfolio size: {len(portfolio)}")
    filtered = []
    for item in portfolio:
        symbol = item.get("symbol")
        if symbol and isinstance(symbol, str) and symbol.strip():
            filtered.append({
                "symbol": symbol.strip().upper(),
                "quantity": float(item.get("quantity", 0))
            })
    logger.info(f"DAG Node (filter_holdings): Filtered portfolio size: {len(filtered)}")
    return filtered


@register_node("fetch_market_data")
async def fetch_market_data(filtered_portfolio: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic CodeNode: programmatically fetches market data for the portfolio."""
    council_service = context["council_service"]
    user_id = context["user_id"]
    
    tickers = [item["symbol"] for item in filtered_portfolio]
    if not tickers:
        return {}

    logger.info(f"DAG Node (fetch_market_data): Fetching prices for tickers {tickers}")
    from src.services.market_data_service import MarketDataService
    market_svc = MarketDataService(user_id=user_id)
    prices = await market_svc.get_current_prices(tickers)
    
    # Formulate a structured market data dict for downstream nodes
    market_data = {
        "prices": prices,
        "raw": context.get("initial_market_data", {})
    }
    return market_data


@register_node("run_ticker_map_analysis")
async def run_ticker_map_analysis(
    filtered_portfolio: List[Dict[str, Any]],
    portfolio_market_data: Dict[str, Any],
    context: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    CodeNode: Runs Momentum + Fundamental mapping on each portfolio holding.
    Implements fine-grained per-ticker caching to maximize token savings.
    """
    council_service = context["council_service"]
    user_id = context["user_id"]
    session_id = context["session_id"]
    workflow_cache = context.get("workflow_cache")

    async def analyze_single_ticker(ticker_item: Dict[str, Any]) -> Dict[str, Any]:
        ticker = ticker_item["symbol"]
        qty = ticker_item["quantity"]
        
        # Construct specific ticker market context for hashing
        ticker_prices = (portfolio_market_data or {}).get("prices") or {}
        ticker_price = ticker_prices.get(ticker) if isinstance(ticker_prices, dict) else None
        
        ticker_market_context = {
            "price": ticker_price,
            "raw": (portfolio_market_data or {}).get("raw") or {}
        }
        
        # Build fine-grained cache key for this specific ticker analysis
        cache_hit = False
        cached_result = None
        
        if workflow_cache:
            # Hash inputs specific to this ticker analysis
            ticker_input_str = json.dumps({
                "ticker": ticker,
                "price": ticker_price,
                "user_id": user_id
            }, sort_keys=True)
            ticker_hash = hashlib.sha256(ticker_input_str.encode("utf-8")).hexdigest()
            cache_key = f"wf_node:TickerMapAnalysis:ticker:{ticker}:{ticker_hash}"
            
            try:
                # We reuse the cache's get method with a pseudo node name
                cached_result = await workflow_cache.get(f"TickerMapAnalysis_{ticker}", {"hash": ticker_hash})
                if cached_result:
                    cache_hit = True
            except Exception as e:
                logger.warning(f"DAG Node (run_ticker_map_analysis): Per-ticker cache get failed for {ticker}: {e}")

        if cache_hit and cached_result:
            logger.info(f"DAG Node (run_ticker_map_analysis): [Fine-grained Cache Hit] Ticker {ticker}")
            # Re-record stance/decision if it is a new session
            # (The outcomes are tracked by session_id, so recording is necessary per session run)
            try:
                # Re-record decision if not already recorded in DB for this session
                # In real scenario, we record and cite if needed, but since it is cached, 
                # we just return the cached analysis output
                pass
            except Exception as e:
                logger.warning(f'Exception in portfolio_dag.py: {e}', exc_info=True)
            return cached_result

        logger.info(f"DAG Node (run_ticker_map_analysis): [Cache Miss] Analyzing Ticker {ticker}")
        
        past_context = council_service.outcome_service.get_past_context(ticker=ticker, limit=3)
        sub_context = {
            "topic": f"Analysis of {ticker}",
            "ticker": ticker,
            "quantity": qty,
            "market_data": ticker_market_context,
            "past_decision_lessons": past_context or "No prior resolved decisions for this ticker.",
        }

        # Run Momentum + Fundamental agent calls in parallel
        res_mom, res_fun = await asyncio.gather(
            council_service._call_agent_llm("Momentum", sub_context, tier="fast"),
            council_service._call_agent_llm("Fundamental", sub_context, tier="fast")
        )

        # Record decision outcome / rules citation
        try:
            from src.agents.structured import AnalystStance
            synth_prompt = (
                f"Ticker: {ticker}\nMomentum view: {res_mom}\nFundamental view: {res_fun}\n"
                "Synthesize these into a single stance."
            )
            stance = await council_service._call_structured("TickerSynthesis", synth_prompt, AnalystStance, tier="fast")
            # 2026-08-10: every failure below used to be invisible.
            # decision_outcomes had 0 rows in production, and this is its only
            # writer — but nothing said why. Two of the three ways to end up
            # with no row (a null stance, a falsy price) logged nothing at all,
            # and the third logged at DEBUG, which prod does not emit.
            #
            # That silence had teeth: TradingProtectionsService's three BUY
            # guards (max drawdown, per-ticker cooldown, consecutive-loss
            # lockout) each return None when decision_outcomes holds fewer
            # than three rows, so an empty table meant every guard passed. The
            # protections appeared active while enforcing nothing.
            #
            # Log level raised to warning and the skip reasons made explicit.
            # This is diagnosis, not a fix — the point is that the next empty
            # table announces itself instead of being inferred from a 0 count.
            #
            # 2026-08-10：此處三種「沒寫入」的路徑中，兩種完全不記錄、一種只記
            # DEBUG（prod 不輸出），導致 decision_outcomes 為 0 筆卻無從得知原因。
            # 而該表為空會讓 TradingProtectionsService 三道 BUY 護欄全部靜默放行。
            # 改為 warning 並寫明跳過原因；這是讓問題可見，而非修好它。
            if stance is None:
                logger.warning(
                    f"Council: no decision recorded for {ticker} — structured stance "
                    f"parse returned None (decision_outcomes stays empty, which "
                    f"disables the BUY protections that read it)"
                )
            elif not ticker_price:
                logger.warning(
                    f"Council: no decision recorded for {ticker} — ticker_price is "
                    f"{ticker_price!r} (decision_outcomes stays empty, which "
                    f"disables the BUY protections that read it)"
                )
            else:
                decision_id = council_service.outcome_service.record_decision(
                    ticker=ticker, agent_name="CouncilSynthesis",
                    signal=stance.rating.value, price=ticker_price,
                    session_id=session_id, horizon_days=5,
                )
                if not decision_id:
                    logger.warning(
                        f"Council: record_decision returned no id for {ticker}; "
                        f"decision outcome was not persisted"
                    )
                else:
                    try:
                        from src.repositories.memory_repository import AgentState
                        from src.services.rule_lifecycle_service import RuleLifecycleService
                        active_rules = AgentState().get_active_rules("CouncilSynthesis", user_id=user_id)
                        if active_rules:
                            await RuleLifecycleService(user_id=user_id).judge_and_cite(
                                "CouncilSynthesis", decision_id, synth_prompt, active_rules,
                            )
                    except Exception as cite_e:
                        # Citation is auxiliary — the decision row is already
                        # written, so this stays non-fatal and low-severity.
                        # 引用為輔助流程，決策列已寫入，故維持非致命。
                        logger.debug(f"Council: rule citation failed for {ticker}: {cite_e}")
        except Exception as synth_e:
            logger.warning(
                f"Council: decision recording failed for {ticker}: {synth_e}", exc_info=True
            )

        result = {
            "ticker": ticker,
            "momentum": res_mom,
            "fundamental": res_fun,
            "quantity": qty
        }

        # Write to per-ticker cache
        if workflow_cache:
            try:
                await workflow_cache.set(f"TickerMapAnalysis_{ticker}", {"hash": ticker_hash}, result, ttl_seconds=3600)
            except Exception as e:
                logger.warning(f"DAG Node (run_ticker_map_analysis): Per-ticker cache set failed for {ticker}: {e}")

        return result

    # Distribute parallel tasks using the council service lane manager
    tasks = [lambda t=t: analyze_single_ticker(t) for t in filtered_portfolio]
    map_results = await council_service.lane_manager.run_batch(tasks, batch_size=5)
    return map_results


@register_node("reduce_holdings")
def reduce_holdings(map_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Deterministic CodeNode: groups, formats, and synthesizes holdings map results into Markdown."""
    logger.info("DAG Node (reduce_holdings): Aggregating map analyses...")
    aggregated_summary = "## 2. 議會焦點辯論 (The Great Debate & Detailed Analysis)\n"
    for res in map_results:
        if isinstance(res, dict) and "ticker" in res:
            from src.utils.format_utils import format_agent_output
            aggregated_summary += f"#### {res['ticker']} (Qty: {res['quantity']})\n"
            aggregated_summary += f"- **Momentum**: {format_agent_output(res['momentum'])}\n"
            aggregated_summary += f"- **Fundamental**: {format_agent_output(res['fundamental'])}\n\n"
        else:
            aggregated_summary += f"- Error in analysis: {res}\n"
    return {"aggregated_summary": aggregated_summary}


@register_node("reduce_scouts")
def reduce_scouts(
    momentum_scout_result: str,
    fundamental_scout_result: str,
    macro_scout_result: str
) -> Dict[str, Any]:
    """Deterministic CodeNode: formats and groups scout agents' recommendations into Markdown."""
    logger.info("DAG Node (reduce_scouts): Aggregating scout recommendations...")
    scout_summary = "## Scout Agents: Buy Opportunities\n"
    scout_summary += f"\n### Momentum Scout\n{momentum_scout_result}\n"
    scout_summary += f"\n### Fundamental Scout\n{fundamental_scout_result}\n"
    scout_summary += f"\n### Macro Scout\n{macro_scout_result}\n"
    return {"scout_summary": scout_summary}


# ──────────────────────────────────────────────────────────────────────
# PortfolioAnalysisDAG Implementation
# ──────────────────────────────────────────────────────────────────────

@register_node("reduce_debate_stances")
def reduce_debate_stances(**kwargs) -> Dict[str, Any]:
    """
    Deterministic CodeNode: merges all agent stance outputs into a single
    council_transcript Markdown block for the CIO to synthesise.
    Accepts any number of keyword arguments matching *_stance pattern.
    """
    logger.info("DAG Node (reduce_debate_stances): Aggregating agent stances...")
    lines = []
    for key in sorted(kwargs.keys()):
        if key.endswith("_stance"):
            agent_label = key.replace("_stance", "").replace("_", " ").title()
            lines.append(f"[{agent_label}]: {kwargs[key]}")
    transcript = "\n".join(lines)
    return {"council_transcript": transcript}


# ──────────────────────────────────────────────────────────────────────
# SingleTickerAnalysisDAG — Replaces procedural _run_debate_logic
# ──────────────────────────────────────────────────────────────────────
