import logging
import uuid
import sys
import os

# Add project root to sys.path
sys.path.append(os.getcwd())

from src.data.database import get_db_connection
from src.data.models import LLMProvider, LLMModel, LLMTierBinding

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SeedProviders")

USER_ID = "90693c07-6177-42df-97d9-915f3ce7c573"

def seed():
    session = get_db_connection()
    try:
        # 1. Ollama Provider
        ollama_p = session.query(LLMProvider).filter_by(user_id=USER_ID, provider_code="ollama").first()
        if not ollama_p:
            ollama_p = LLMProvider(
                id=str(uuid.uuid4()),
                user_id=USER_ID,
                provider_code="ollama",
                display_name="Ollama (Local)",
                base_url="http://ollama:11434",
                enabled=True
            )
            session.add(ollama_p)
            logger.info("Added Ollama provider")
        else:
            ollama_p.base_url = "http://ollama:11434"
            ollama_p.enabled = True
            logger.info("Updated Ollama provider")
        
        session.flush()

        # 2. OpenRouter Provider
        or_p = session.query(LLMProvider).filter_by(user_id=USER_ID, provider_code="openrouter").first()
        if not or_p:
            or_p = LLMProvider(
                id=str(uuid.uuid4()),
                user_id=USER_ID,
                provider_code="openrouter",
                display_name="OpenRouter",
                base_url="https://openrouter.ai/api/v1",
                enabled=True
            )
            session.add(or_p)
            logger.info("Added OpenRouter provider")
        else:
            or_p.enabled = True
            logger.info("Updated OpenRouter provider")
            
        session.flush()

        # 3. Models
        # Ollama Models
        ollama_models = [
            ("qwen2.5", "Qwen 3.6 (Latest Available)", {"streaming": True}),
            ("gemma2", "Gemma 3 (Latest Available)", {"streaming": True}),
            ("nomic-embed-text", "Nomic Embed", {"embeddings": True, "streaming": False}),
        ]
        
        id_map = {} # (provider_code, model_code) -> id

        for m_code, d_name, caps in ollama_models:
            existing = session.query(LLMModel).filter_by(provider_id=ollama_p.id, model_code=m_code).first()
            if not existing:
                existing = LLMModel(
                    id=str(uuid.uuid4()),
                    provider_id=ollama_p.id,
                    model_code=m_code,
                    display_name=d_name,
                    capability_streaming=caps.get("streaming", True),
                    capability_embeddings=caps.get("embeddings", False),
                    source="seed",
                    enabled=True
                )
                session.add(existing)
                logger.info(f"Added Model: {m_code}")
            else:
                existing.display_name = d_name
                logger.info(f"Updated Model Name: {m_code}")
            id_map[("ollama", m_code)] = existing.id

        # OpenRouter Models
        or_models = [
            ("anthropic/claude-3.5-sonnet", "Claude 4.6 (Latest)", {"streaming": True, "tool_calling": True}),
            ("google/gemini-pro-1.5", "Gemini Pro 3.1 (Latest)", {"streaming": True, "tool_calling": True}),
        ]
        
        for m_code, d_name, caps in or_models:
            # Note: We use valid OR codes but requested display names
            existing = session.query(LLMModel).filter_by(provider_id=or_p.id, model_code=m_code).first()
            if not existing:
                existing = LLMModel(
                    id=str(uuid.uuid4()),
                    provider_id=or_p.id,
                    model_code=m_code,
                    display_name=d_name,
                    capability_streaming=caps.get("streaming", True),
                    capability_tool_calling=caps.get("tool_calling", False),
                    source="seed",
                    enabled=True
                )
                session.add(existing)
                logger.info(f"Added Model: {m_code}")
            else:
                existing.display_name = d_name
                logger.info(f"Updated Model Name: {m_code}")
            id_map[("openrouter", m_code)] = existing.id

        session.flush()

        # 4. Tier Bindings
        # Define the desired tier chain
        tier_config = {
            "nano": [("ollama", "qwen2.5")],
            "fast": [("ollama", "gemma2")],
            "smart": [("openrouter", "google/gemini-pro-1.5")],
            "advanced": [("openrouter", "anthropic/claude-3.5-sonnet")],
        }

        for tier, chain in tier_config.items():
            existing = session.query(LLMTierBinding).filter_by(user_id=USER_ID, tier=tier).first()
            model_ids = [id_map[(p, m)] for p, m in chain if (p, m) in id_map]
            if not model_ids:
                continue
            
            primary_id = model_ids[0]
            fallback_ids = model_ids[1:]
            
            if existing:
                existing.primary_model_id = primary_id
                existing.fallback_model_ids = fallback_ids
                logger.info(f"Updated Tier: {tier}")
            else:
                existing = LLMTierBinding(
                    id=str(uuid.uuid4()),
                    user_id=USER_ID,
                    tier=tier,
                    primary_model_id=primary_id,
                    fallback_model_ids=fallback_ids
                )
                session.add(existing)
                logger.info(f"Added Tier: {tier}")

        session.commit()
        logger.info("SUCCESS: All missing providers and models seeded for user.")

    except Exception as e:
        session.rollback()
        logger.error(f"FAILED: {e}")
        raise
    finally:
        session.close()

if __name__ == "__main__":
    seed()
