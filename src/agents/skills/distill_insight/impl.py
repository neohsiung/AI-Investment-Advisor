from src.utils.logger import setup_logger

logger = setup_logger("skill_distill_insight")

async def distill_insight(
    user_id: str,
    source_texts: str,
    council_text: str = "",
    agent_name: str = "SentinelService",
    importance: float = 0.6,
) -> str:
    """
    Distill Insight Skill — 用 Fast LLM 萃取 1-2 句洞察並寫入 cognitive_memories。
    
    Returns:
        "ok: {distilled_text}" or "error: {reason}"
    """
    try:
        from src.data.database import get_db_connection
        from src.infrastructure.llm.llm_gateway import LLMGatewayFactory, Message, LLMConfig, RetryLLMGateway
        from src.services.settings_service import SettingsService
        from sqlalchemy import text
        import uuid, json
        from datetime import datetime, timezone

        # Build a brief summary to store — avoid saving the full Council markdown
        # Use a fast, cheap LLM call to distill the key insight
        distilled = ""
        try:
            ss = SettingsService(user_id=user_id)
            provider = ss.get_setting("AI_PROVIDER", "OpenRouter") or "OpenRouter"
            model    = ss.get_setting("AI_MODEL_FAST", "google/gemini-2.0-flash") or "google/gemini-2.0-flash"
            api_key  = ss.get_setting("OPENROUTER_API_KEY") or ss.get_setting("AI_API_KEY", "")
            base_url = ss.get_setting("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")

            gateway = RetryLLMGateway(inner=LLMGatewayFactory.create(provider), max_retries=1)
            distill_cfg = LLMConfig(
                provider=provider, model=model, api_key=api_key, base_url=base_url,
                temperature=0.2, max_retries=1, timeout_seconds=20
            )
            distill_msgs = [
                Message(role="system", content=(
                    "You are a financial memory distiller. Extract the single most important insight "
                    "from the following text. "
                    "Output exactly 1-2 sentences in Traditional Chinese. "
                    "Focus on: what signal fired, what the AI concluded, and any ticker mentioned."
                )),
                Message(role="user", content=(
                    f"Triggers: {source_texts}\n\n"
                    f"Assessment (first 600 chars): {council_text[:600]}"
                )),
            ]
            distilled = await gateway.chat(distill_msgs, distill_cfg)
            distilled = distilled.strip()
        except Exception as llm_e:
            logger.warning(f"Insight distillation LLM call failed: {llm_e}")
            # Fallback: use raw trigger text
            distilled = f"[Alert] {source_texts[:200]}"

        # Write to cognitive_memories using actual schema
        with get_db_connection() as conn:
            content_jsonb = {
                "insight": distilled,
                "trigger_texts": source_texts,
                "council_excerpt": council_text[:400] if council_text else "",
            }
            conn.execute(text("""
                INSERT INTO cognitive_memories 
                (id, user_id, agent_name, memory_type, content, importance, source_id, created_at, updated_at)
                VALUES (:id, :uid, :agent, :mtype, :content::jsonb, :importance, :src_id, :ts, :ts)
            """), {
                "id":         str(uuid.uuid4()),
                "uid":        user_id,
                "agent":      agent_name,
                "mtype":      "alert_insight",
                "content":    json.dumps(content_jsonb, ensure_ascii=False),
                "importance": importance,
                "src_id":     f"distill_{str(uuid.uuid4())[:8]}",
                "ts":         datetime.now(timezone.utc),
            })
        logger.info(f"Alert insight distilled and stored to cognitive_memories")
        return f"ok: {distilled}"

    except Exception as e:
        logger.error(f"Failed to store alert insight: {e}")
        return f"error: {e}"
