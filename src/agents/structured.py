"""
Structured agent output — typed decisions instead of concatenated prose.

The council/CIO pipeline historically passed free-text strings and re-parsed
them with regex/`json_loads_safe`, which is fragile (see the invalid-JSON guard
in `cio._run_strategy`). This helper lets an agent emit a Pydantic-validated
object while remaining compatible with the existing `ILLMGateway.chat(...)->str`
interface (no gateway changes): the schema is rendered into the prompt, the
reply is parsed + validated, and on ANY failure we fall back to the raw text so
the pipeline never blocks.

結構化輸出：讓 agent 產出 Pydantic 型別物件（評級/目標價可機器讀取），
但不改既有 gateway 介面；解析/驗證失敗則 fallback 原始文字，永不阻塞流程。

Pattern adapted from TradingAgents `agents/utils/structured.py` (schema field
descriptions carry the output instructions), reimplemented for this stack.
"""
from __future__ import annotations

import json
import logging
import re
from enum import Enum
from typing import List, Optional, Tuple, Type, TypeVar

from pydantic import BaseModel, Field, ValidationError

from src.domain.interfaces import ILLMGateway, LLMConfig, Message

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ── Shared vocabulary ────────────────────────────────────────────────────

class Rating(str, Enum):
    """5-tier decisiveness scale. Reserve HOLD only when evidence is genuinely
    balanced — countering hedge-everything drift."""
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"


class AnalystStance(BaseModel):
    """One agent's stance in a council debate."""
    rating: Rating = Field(description="One of STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL")
    confidence: float = Field(ge=0.0, le=1.0, description="0.0-1.0 confidence in this stance")
    thesis: str = Field(description="1-3 sentence core argument")
    key_risks: List[str] = Field(default_factory=list, description="Top risks that could invalidate the thesis")


class CIOConsensus(BaseModel):
    """The CIO's synthesized final decision."""
    rating: Rating = Field(description="Final call: STRONG_BUY/BUY/HOLD/SELL/STRONG_SELL")
    confidence: float = Field(ge=0.0, le=1.0, description="0.0-1.0 confidence in the consensus")
    executive_summary: str = Field(description="2-4 sentence summary of the decision and why")
    price_target: Optional[float] = Field(default=None, description="Target price if applicable, else null")
    time_horizon: Optional[str] = Field(default=None, description="e.g. '1-3 months', '6-12 months'")
    key_drivers: List[str] = Field(default_factory=list, description="Main factors behind the call")


# ── Prompt rendering + parsing ───────────────────────────────────────────

def build_schema_instruction(schema: Type[BaseModel]) -> str:
    """Render field descriptions + a JSON skeleton the model must fill."""
    fields = []
    skeleton = {}
    for name, field in schema.model_fields.items():
        desc = field.description or ""
        fields.append(f'  - "{name}": {desc}')
        skeleton[name] = "..."
    fields_txt = "\n".join(fields)
    return (
        "\n\nRespond with ONLY a single JSON object (no prose, no code fences) "
        f"matching this schema:\n{fields_txt}\n"
        f"Shape: {json.dumps(skeleton, ensure_ascii=False)}"
    )


def extract_json(text: str) -> Optional[dict]:
    """Best-effort extraction of the first JSON object from a model reply."""
    if not text:
        return None
    # strip ```json ... ``` fences
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else None
    if candidate is None:
        # first balanced-looking {...} block
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


async def invoke_structured(
    gateway: ILLMGateway,
    messages: List[Message],
    config: LLMConfig,
    schema: Type[T],
) -> Tuple[Optional[T], str]:
    """
    Call the gateway asking for structured output.

    Returns ``(parsed, raw_text)``. ``parsed`` is a validated instance of
    ``schema`` or ``None`` if parsing/validation failed (raw_text always holds
    the model's reply so callers can fall back to prose).
    """
    augmented = list(messages)
    instruction = build_schema_instruction(schema)
    if augmented and augmented[-1].role == "user":
        augmented[-1] = Message(role="user", content=augmented[-1].content + instruction)
    else:
        augmented.append(Message(role="user", content=instruction))

    raw = await gateway.chat(augmented, config)
    if not isinstance(raw, str):
        return None, str(raw)

    data = extract_json(raw)
    if data is None:
        logger.debug("invoke_structured: no JSON found; falling back to raw text")
        return None, raw
    try:
        return schema.model_validate(data), raw
    except ValidationError as exc:
        logger.debug("invoke_structured: validation failed (%s); falling back to raw text", exc)
        return None, raw


def render_stance(stance: AnalystStance, agent_name: str = "") -> str:
    """Convert a typed stance back to the markdown the rest of the system consumes."""
    risks = ("; ".join(stance.key_risks)) or "—"
    prefix = f"[{agent_name}] " if agent_name else ""
    return (
        f"{prefix}{stance.rating.value} (confidence {stance.confidence:.0%})\n"
        f"Thesis: {stance.thesis}\nKey risks: {risks}"
    )
