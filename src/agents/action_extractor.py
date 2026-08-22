"""
ActionExtractorAgent (2026-07-12) — extracts structured actionable orders
(ticker/action/quantity/confidence/rationale) from CIO council decision text.

Product spec (哨兵與評議會架構-Sentinel-Council-Architecture.md §2.1.3) calls
for a dedicated ActionExtractorAgent that converts unstructured Council
discussion into a `[CONVINCING_ACTION]` JSON block the trading system can
read. Previously this logic existed only inline inside
`workflow_service._parse_actionable_orders()` — functionally equivalent but
not the independent component the spec describes.

Design: deterministic-first, LLM as fallback only.
- Strategy 0: `[CONVINCING_ACTION]` JSON block (cheapest, most reliable)
- Strategy 1: Markdown pipe table
- Strategy 2: HTML `<table>`
- Strategy 3 (LLM fallback): only when all three deterministic strategies
  find nothing — uses the P0.2 structured-output helper (fast tier) to
  extract actions from free-form text. Avoids LLM cost on the common case
  (CIO already produces one of the three deterministic formats) while adding
  real robustness for reports that don't.

設計：優先走 3 個決定性策略（零成本、可靠），全部找不到才呼叫 LLM
（fast tier，走結構化輸出）做保底擷取。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ActionExtractorAgent:
    """Not a BaseAgent subclass — this is a mostly-deterministic extractor,
    not a chat-completion agent; it only calls an LLM as a last resort."""

    name = "ActionExtractor"

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id or "system"

    async def extract(self, final_report: str) -> List[Dict[str, Any]]:
        """
        Returns a list of actionable-order dicts:
        {ticker, action, quantity, score, reason, target_weight?, current_weight?, delta_weight?}
        Empty list if no actionable orders found by any strategy.
        """
        if not final_report:
            return []

        orders = self._extract_json_block(final_report)
        if orders:
            logger.info("ActionExtractor: %d order(s) via [CONVINCING_ACTION] JSON block", len(orders))
            return orders

        orders = self._extract_markdown_table(final_report)
        if orders:
            logger.info("ActionExtractor: %d order(s) via Markdown table", len(orders))
            return orders

        orders = self._extract_html_table(final_report)
        if orders:
            logger.info("ActionExtractor: %d order(s) via HTML table", len(orders))
            return orders

        orders = await self._extract_via_llm(final_report)
        if orders:
            logger.info("ActionExtractor: %d order(s) via LLM fallback", len(orders))
        else:
            logger.info("ActionExtractor: no actionable orders found by any strategy")
        return orders

    # ── Strategy 0: [CONVINCING_ACTION] JSON block ──────────────────────

    def _extract_json_block(self, final_report: str) -> List[Dict[str, Any]]:
        if "[CONVINCING_ACTION]" not in final_report:
            return []
        try:
            parts = final_report.split("[CONVINCING_ACTION]")
            if len(parts) <= 1:
                return []
            json_str = parts[1].strip()
            brace_count = 0
            start_idx = -1
            end_idx = -1
            for idx, char in enumerate(json_str):
                if char == '{':
                    if brace_count == 0:
                        start_idx = idx
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0 and start_idx != -1:
                        end_idx = idx + 1
                        break
            if start_idx == -1 or end_idx == -1:
                return []
            data = json.loads(json_str[start_idx:end_idx])
            actions = data.get("actions", [])
            orders = []
            for act in actions:
                ticker = str(act.get("ticker", "")).strip().upper()
                action = str(act.get("action", "")).strip().upper()
                signal = "BUY" if "BUY" in action else ("SELL" if "SELL" in action else "HOLD")
                if ticker and signal != "HOLD":
                    orders.append({
                        "ticker": ticker, "action": signal,
                        "quantity": act.get("quantity") or 100.0,
                        "score": act.get("confidence") or 7,
                        "reason": act.get("rationale") or f"CIO Signal ({signal})",
                        "target_weight": act.get("target_weight"),
                        "current_weight": act.get("current_weight"),
                        "delta_weight": act.get("delta_weight"),
                    })
            return orders
        except Exception as exc:
            logger.warning("ActionExtractor: JSON block parse failed: %s", exc)
            return []

    # ── Strategy 1: Markdown pipe table ──────────────────────────────────

    def _extract_markdown_table(self, final_report: str) -> List[Dict[str, Any]]:
        rows: List[List[str]] = []
        lines = final_report.split("\n")
        for i, line in enumerate(lines):
            if "|" in line and "---" in line:
                prev_line = lines[i - 1].lower() if i > 0 else ""
                if any(x in prev_line for x in ["action", "動作", "代號", "ticker"]):
                    for j in range(i + 1, len(lines)):
                        row_line = lines[j].strip()
                        if not row_line.startswith("|"):
                            break
                        cols = [c.strip() for c in row_line.split("|") if c.strip()]
                        if len(cols) >= 4 and "---" not in row_line:
                            rows.append(cols)
                    break
        return self._rows_to_orders(rows)

    # ── Strategy 2: HTML <table> ──────────────────────────────────────────

    def _extract_html_table(self, final_report: str) -> List[Dict[str, Any]]:
        rows: List[List[str]] = []
        tr_blocks = re.findall(r"<tr[^>]*>(.*?)</tr>", final_report, re.DOTALL | re.IGNORECASE)
        for tr in tr_blocks:
            if "<th" in tr.lower():
                continue
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.DOTALL | re.IGNORECASE)
            cleaned = [re.sub(r"<[^>]+>", "", td).strip() for td in tds]
            if len(cleaned) >= 4:
                rows.append(cleaned)
        return self._rows_to_orders(rows)

    def _rows_to_orders(self, rows: List[List[str]]) -> List[Dict[str, Any]]:
        orders = []
        for cols in rows:
            ticker = cols[0].strip().upper()
            action = cols[1]
            quantity = cols[2]
            try:
                score_raw = re.search(r"(\d+)", cols[3])
                score = int(score_raw.group(1)) if score_raw else 5
            except (ValueError, IndexError):
                score = 5

            u_act = action.upper()
            if any(x in u_act for x in ["BUY", "ACCUMULATE", "加碼", "買"]):
                signal = "BUY"
            elif any(x in u_act for x in ["SELL", "TRIM", "REDUCE", "LIQUIDATE", "減碼", "出清", "賣", "避險"]):
                signal = "SELL"
            else:
                signal = "HOLD"

            if signal != "HOLD":
                orders.append({
                    "ticker": ticker, "action": signal, "quantity": quantity, "score": score,
                    "reason": cols[4] if len(cols) >= 5 else f"CIO Signal ({signal})",
                })
        return orders

    # ── Strategy 3: LLM fallback (structured output, fast tier) ──────────

    async def _extract_via_llm(self, final_report: str) -> List[Dict[str, Any]]:
        try:
            from pydantic import BaseModel, Field
            from typing import List as _List, Optional as _Optional
            from src.agents.structured import invoke_structured
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message

            class _ExtractedAction(BaseModel):
                ticker: str = Field(description="Stock ticker symbol, uppercase")
                action: str = Field(description="One of BUY or SELL only (never HOLD)")
                quantity: _Optional[float] = Field(default=None, description="Share quantity if specified, else null")
                confidence: int = Field(ge=1, le=10, description="Confidence 1-10")
                rationale: str = Field(default="", description="1 sentence reason")

            class _ExtractedActions(BaseModel):
                actions: _List[_ExtractedAction] = Field(default_factory=list)

            chain = build_config_chain(self.user_id, "fast")
            if not chain:
                return []
            pipeline = ResilientLLMPipeline(config_chain=chain, user_id=self.user_id,
                                             agent_name=self.name, tier="fast")
            gateway = pipeline._gateway_factory(chain[0])
            config = pipeline._build_llm_config(chain[0], temperature=0.1, max_tokens=800)
            prompt = (
                "Extract all actionable BUY/SELL orders from this investment council "
                "decision text. Ignore HOLD/no-action items. If no actionable orders "
                "exist, return an empty actions list.\n\n" + final_report[:6000]
            )
            parsed, _raw = await invoke_structured(
                gateway, [Message(role="user", content=prompt)], config, _ExtractedActions,
            )
            if not parsed:
                return []
            return [{
                "ticker": a.ticker.strip().upper(),
                "action": a.action.strip().upper(),
                "quantity": a.quantity or 100.0,
                "score": a.confidence,
                "reason": a.rationale or f"CIO Signal ({a.action.upper()})",
            } for a in parsed.actions if a.ticker and a.action.upper() in ("BUY", "SELL")]
        except Exception as exc:
            logger.warning("ActionExtractor: LLM fallback failed (non-blocking): %s", exc)
            return []
