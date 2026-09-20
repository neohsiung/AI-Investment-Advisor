import os
import json
import asyncio
from typing import Optional, Dict, Any
from src.agents.base_agent import BaseAgent
from src.infrastructure.llm.arbiter_client import ArbiterClient

class SentinelAgent(BaseAgent):
    """
    Sentinel Agent: Specialized coordinator for classifying and prioritizing incoming triggers.
    哨兵智能體：專門負責對傳入的觸發事件進行分類與優先級評定的協調者。

    Tier: reflex (Jev 1.13 毫秒級強型別條件裁決，置信度不足時自動升級至 smart tier)
    """
    def __init__(
        self,
        use_cache: bool = True,
        tier: str = "smart",
        use_arbiter: Optional[bool] = None,
        shadow_mode: Optional[bool] = None,
        arbiter_client: Optional[ArbiterClient] = None,
        **kwargs
    ):
        super().__init__(
            name="Sentinel", 
            prompt_path="prompts/sentinel_agent.txt", 
            use_cache=use_cache, 
            ttl_hours=1,  # Sentinel results are time-sensitive
            tier=tier, 
            **kwargs
        )
        if use_arbiter is None:
            use_arbiter = os.getenv("SENTINEL_USE_ARBITER", "false").lower() in ("true", "1")
        if shadow_mode is None:
            shadow_mode = os.getenv("SENTINEL_SHADOW_MODE", "false").lower() in ("true", "1")
        self.use_arbiter = use_arbiter
        self.shadow_mode = shadow_mode
        self._arbiter_client = arbiter_client

    def _get_arbiter_client(self) -> ArbiterClient:
        if self._arbiter_client is None:
            # 注入底層 llm_gateway 提供語意升級
            self._arbiter_client = ArbiterClient(llm_gateway=self.llm_gateway)
        return self._arbiter_client

    async def run(self, context):
        """
        Evaluate priority for a trigger.
        context expects:
        - 'trigger_source': Internal/Webhook/etc.
        - 'event_data': The raw data of the event.
        - 'current_vix': Market volatility context.
        """
        trigger_source = context.get('trigger_source', 'unknown')
        event_data = context.get('event_data', {})
        current_vix = context.get('current_vix', 20.0)

        # ── 1. 若啟用 Arbiter 主流程（非影子模式），直接走毫秒級條件裁決 ──
        if self.use_arbiter and not self.shadow_mode:
            return await self._run_arbiter(trigger_source, event_data, current_vix)

        prompt_data = {
            "trigger_source": trigger_source,
            "event_data": json.dumps(event_data, indent=2, ensure_ascii=False),
            "current_vix": current_vix
        }

        try:
            # 2. 原有 System 2 (Smart LLM) 主流程
            response_str = await self.run_tool_loop(context=prompt_data)
        
            # Clean up response if it contains markdown or thinking text
            # 精簡：尋找第一個 { 並從那裡開始解析，或使用正則提取
            if "{" in response_str:
                json_part = response_str[response_str.find("{"):response_str.rfind("}")+1]
                result_data = json.loads(json_part)
            elif "Simulation Mode" in response_str:
                # Simulation Mode fallback for local testing without API keys
                self.logger.info("Sentinel: Simulation Mode detected in LLM response. Returning default P2 priority.")
                return {
                    "priority": "P2",
                    "target_agent": "CIO",
                    "trigger_type": "generic",
                    "affected_tickers": [],
                    "rationale": "System running in simulation mode (Missing API key). Defaulting to P2 for safety.",
                    "is_simulated": True
                }
            else:
                raise ValueError("No JSON object found in response")
            
            # Ensure new fields have defaults
            result_data.setdefault("trigger_type", "generic")
            result_data.setdefault("affected_tickers", [])
            
            # 2. Potential Agent Consultation (If priority is high and target_agent is specified)
            # v2.1: According to user request, we can consult the most relevant agent.
            target_agent = result_data.get("target_agent")
            if target_agent and result_data.get("priority") in ["P1", "P2"]:
                self.logger.info(f"Sentinel consulting {target_agent} for deeper priority validation.")
                
                consult_msg = f"Please confirm if the following event deserves {result_data['priority']} attention: {prompt_data['event_data']}"
                consult_res = await self.call_agent(target_agent, consult_msg)
                
                # If sub-agent explicitly downgrades or provides critical insights, we could update rationale.
                # For now, we just log and append info to the rationale.
                result_data["consultation_note"] = f"Consulted {target_agent}: {consult_res[:100]}..."
            
            # 3. 若為影子模式 (Shadow Mode)，在背景觸發 Arbiter 進行平行對比
            if self.use_arbiter and self.shadow_mode:
                asyncio.create_task(
                    self._shadow_arbiter_eval(
                        trigger_source=trigger_source,
                        event_data=event_data,
                        current_vix=current_vix,
                        primary_priority=result_data.get("priority", "UNKNOWN")
                    )
                )

            return result_data

        except (json.JSONDecodeError, ValueError) as e:
            self.logger.error(f"Failed to parse or find JSON in SentinelAgent response: {e}\nResponse: {response_str}")
            return {
                "priority": "P2", # Fallback to a safe moderate priority
                "target_agent": "CIO",
                "rationale": f"解析錯誤 ({type(e).__name__})，自動降級為 P2 處理。",
                "error": str(e)
            }
        except Exception as e:
            self.logger.error(f"Error during sentinel prioritization: {e}")
            return {"priority": "P3", "target_agent": "CIO", "error": str(e)}

    async def _run_arbiter(self, trigger_source: str, event_data: dict, current_vix: float) -> dict:
        """執行 Arbiter (Reflex Tier / Jev 1.13) 條件裁決"""
        arbiter = self._get_arbiter_client()
        state = {
            "trigger_source": trigger_source,
            "event_data": event_data,
            "current_vix": current_vix
        }
        question_spec = {
            "type": "choice",
            "instructions": "Determine market urgency priority: P0 (catastrophic liquidation), P1 (urgent rebalance), P2 (routine review), P3 (noise)",
            "criteria": {
                "P0": "Catastrophic crash, circuit breaker or emergency stop-loss triggered",
                "P1": "Urgent risk drift, significant earnings shock, yield curve inversion or volatility spike",
                "P2": "Normal scheduled rebalance or minor drift",
                "P3": "Informational noise or insignificant tick"
            }
        }
        fallback_prompt = (
            f"Market trigger event: {trigger_source}, VIX: {current_vix}, Event: {json.dumps(event_data, ensure_ascii=False)}.\n"
            "Output JSON with {\"priority\": \"P0\"|\"P1\"|\"P2\"|\"P3\", \"target_agent\": \"CIO\", \"rationale\": \"...\"}"
        )
        decision = await arbiter.decide(
            domain="sentinel",
            state=state,
            question_key="priority",
            question_spec=question_spec,
            confidence_threshold=0.92,
            system2_fallback_prompt=fallback_prompt,
            deterministic_default="P2"
        )
        
        return {
            "priority": str(decision.choice),
            "target_agent": "CIO",
            "trigger_type": "generic",
            "affected_tickers": [],
            "confidence": decision.confidence,
            "is_escalated": decision.is_escalated,
            "tier": decision.tier,
            "state_hash": decision.state_hash,
            "rationale": f"Arbiter 裁決結果 ({decision.tier}, 信心度 {decision.confidence:.2f})"
        }

    async def _shadow_arbiter_eval(self, trigger_source: str, event_data: dict, current_vix: float, primary_priority: str):
        """背景非同步影子評估：比對 Primary LLM 與 Arbiter Jev 的判定結果與延遲"""
        try:
            start_t = asyncio.get_event_loop().time()
            arb_res = await self._run_arbiter(trigger_source, event_data, current_vix)
            duration_ms = (asyncio.get_event_loop().time() - start_t) * 1000.0
            arb_p = arb_res.get("priority")
            self.logger.info(
                f"[SENTINEL SHADOW] Primary={primary_priority} vs Arbiter={arb_p} "
                f"| Match={primary_priority == arb_p} | Tier={arb_res.get('tier')} "
                f"| Conf={arb_res.get('confidence'):.2f} | Latency={duration_ms:.1f}ms"
            )
        except Exception as e:
            self.logger.warning(f"[SENTINEL SHADOW] Arbiter shadow evaluation failed: {e}")

