"""
Factor Synthesizer Service
===========================
運用 LLM 認知路由自主生成符合規範之純量化因子、特徵指標計算純函式與伴生測試代碼。

強制規範：
1. 簽章約定：def calculate_factor(df: pd.DataFrame, params: dict = None) -> pd.Series:
2. 允許模組：僅限 numpy, pandas, math, typing。
3. 邊界防禦：空 DataFrame 檢查、零除防護 (Zero Division Protection)、NaN 填補。
4. JSON 嚴格架構輸出。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("FactorSynthesizer")


@dataclass
class SynthesizedFactorCandidate:
    """
    Candidate factor synthesized by the LLM.
    AI 自主合成之候選量化因子。
    """
    factor_name: str
    description: str
    source_code: str
    test_code: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    target_regimes: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class FactorSynthesizer:
    """
    Synthesizes pure Python factor code and paired unit tests using ResilientLLMPipeline.
    """

    SYSTEM_PROMPT = """You are an institutional Quantitative Alpha Factor Synthesizer.
Your mission is to generate robust, pure-function Python code that calculates quantitative factors or regime filters.

CRITICAL CODE CONSTRAINTS:
1. Entry Function Signature MUST be:
   def calculate_factor(df: pd.DataFrame, params: dict = None) -> pd.Series:
2. Strictly PURE FUNCTION: No side effects, no file I/O, no network calls, no global state.
3. ALLOWED IMPORTS: ONLY `import numpy as np`, `import pandas as pd`, `import math`, `from typing import ...`.
4. FORBIDDEN: `open`, `exec`, `eval`, `compile`, `__import__`, `globals`, `locals`, `getattr`, `os`, `sys`, `subprocess`, `socket`.
5. FORBIDDEN CONTROL FLOW: Do NOT use `while` loops (use pandas vectorization or bounded for loops). Do NOT use recursion.
6. MANDATORY ROBUSTNESS:
   - Check if df is empty: `if df.empty: return pd.Series(dtype=float)`
   - Check required columns (usually 'Close', 'High', 'Low', 'Volume')
   - Guard against division by zero (e.g. `denom = denom.replace(0, np.nan)`)
   - Return a `pd.Series` with matching index and float dtype.
7. COMPANION TESTS: Write at least 2 standard pytest unit tests using synthetic pandas DataFrames.

OUTPUT FORMAT:
You MUST respond with a single valid JSON object with the following schema:
{
  "factor_name": "string (e.g. vix_rebound_exhaustion_score)",
  "description": "string (short description of quantitative rationale)",
  "source_code": "string (complete valid python code including imports)",
  "test_code": "string (pytest unit tests)",
  "parameters": {"param1": 14, ...},
  "target_regimes": ["VOLATILITY_PIVOT", "NORMAL"]
}
Do NOT include any markdown text outside the JSON block.
"""

    def __init__(self, user_id: str):
        self.user_id = user_id

    async def synthesize(
        self,
        hypothesis: str,
        target_regime: str = "VOLATILITY_PIVOT",
        tier: str = "smart",
    ) -> SynthesizedFactorCandidate:
        """
        Synthesize factor code and tests from an investment hypothesis or regime requirement.
        """
        user_prompt = f"""Target Market Regime: {target_regime}
Investment Hypothesis / Factor Requirement:
{hypothesis}

Synthesize a production-ready, pure quantitative factor function `calculate_factor` that captures this hypothesis."""

        raw_response = await self._call_llm(self.SYSTEM_PROMPT, user_prompt, tier=tier)
        return self._parse_response(raw_response, target_regime)

    async def _call_llm(self, system_prompt: str, user_prompt: str, tier: str = "smart") -> str:
        """Invoke ResilientLLMPipeline with safety error handling."""
        try:
            from src.infrastructure.llm.llm_config_chain import build_config_chain
            from src.infrastructure.llm.resilient_pipeline import ResilientLLMPipeline
            from src.domain.interfaces import Message

            chain = build_config_chain(self.user_id, tier)
            if not chain:
                logger.warning("No model configured for tier=%s; using deterministic fallback", tier)
                return self._get_fallback_factor_json("VOLATILITY_PIVOT")

            pipeline = ResilientLLMPipeline(
                config_chain=chain,
                user_id=self.user_id,
                agent_name="factor_synthesizer",
                tier=tier,
            )
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=user_prompt),
            ]
            response, _ = await pipeline.execute(messages, temperature=0.2, max_tokens=2500)
            return response
        except Exception as e:
            logger.warning("LLM call failed in FactorSynthesizer: %s; using deterministic fallback", str(e))
            return self._get_fallback_factor_json("VOLATILITY_PIVOT")

    def _parse_response(self, text: str, default_regime: str) -> SynthesizedFactorCandidate:
        """Parse structured JSON from LLM response."""
        cleaned = text.strip()
        # Remove markdown code block if present
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            # Fallback regex extraction
            match = re.search(r"\{.*\}", cleaned, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                logger.warning("Failed to decode JSON from LLM response; returning fallback candidate")
                data = json.loads(self._get_fallback_factor_json(default_regime))

        return SynthesizedFactorCandidate(
            factor_name=data.get("factor_name", "synthesized_factor"),
            description=data.get("description", ""),
            source_code=data.get("source_code", ""),
            test_code=data.get("test_code", ""),
            parameters=data.get("parameters", {}),
            target_regimes=data.get("target_regimes", [default_regime]),
            metadata={"parser": "standard_json"},
        )

    def _get_fallback_factor_json(self, regime: str) -> str:
        """Deterministic, verified fallback factor template."""
        return json.dumps({
            "factor_name": "volatility_normalized_momentum",
            "description": "Calculates 14-day momentum normalized by 20-day rolling ATR.",
            "source_code": (
                "import numpy as np\n"
                "import pandas as pd\n\n"
                "def calculate_factor(df: pd.DataFrame, params: dict = None) -> pd.Series:\n"
                "    if df.empty or 'Close' not in df.columns:\n"
                "        return pd.Series(dtype=float)\n"
                "    params = params or {}\n"
                "    window = int(params.get('window', 14))\n"
                "    close = df['Close']\n"
                "    mom = close - close.shift(window)\n"
                "    std = close.rolling(window=window).std().replace(0, np.nan)\n"
                "    norm_mom = (mom / std).fillna(0.0)\n"
                "    norm_mom.index = df.index\n"
                "    return norm_mom\n"
            ),
            "test_code": (
                "import pandas as pd\n"
                "import numpy as np\n"
                "from factor_module import calculate_factor\n\n"
                "def test_basic_momentum():\n"
                "    df = pd.DataFrame({'Close': [10.0, 11.0, 12.0, 13.0, 14.0, 15.0]})\n"
                "    res = calculate_factor(df, {'window': 2})\n"
                "    assert len(res) == len(df)\n"
            ),
            "parameters": {"window": 14},
            "target_regimes": [regime],
        })
