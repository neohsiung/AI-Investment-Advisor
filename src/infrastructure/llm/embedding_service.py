"""
Local embedding service — nomic-embed-text via Ollama (768-dim).

Produces real vector embeddings for semantic recall (e.g. council-minute
similarity search). Uses the same local Ollama the rest of the stack uses
(llama_index_service, mem0_client) so there is no API cost and no extra
dependency. 768 dims matches nomic-embed-text and the migrated
council_minutes.embedding column.

本地嵌入服務：透過 Ollama 的 nomic-embed-text（768 維）產生真 embedding，
供語意召回使用。與其餘元件共用本地 Ollama，零 API 成本、無額外依賴。

Every function is defensive: on any failure it returns None so callers can
fall back to keyword/text search rather than break.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_DIM = 768  # nomic-embed-text dimension
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
_TIMEOUT = float(os.getenv("EMBED_TIMEOUT_SECONDS", "15"))


def embed_text(text: str) -> Optional[List[float]]:
    """
    Return a 768-dim embedding for `text`, or None on empty input / any error.
    Never raises — callers fall back to text search if this returns None.
    """
    if not text or not text.strip():
        return None
    try:
        resp = httpx.post(
            f"{_OLLAMA_BASE_URL}/api/embeddings",
            json={"model": EMBED_MODEL, "prompt": text[:8000]},
            timeout=_TIMEOUT,
        )
        resp.raise_for_status()
        vec = resp.json().get("embedding")
        if not vec or len(vec) != EMBED_DIM:
            logger.warning(
                "embed_text: unexpected embedding (len=%s, want %d)",
                len(vec) if vec else 0,
                EMBED_DIM,
            )
            return None
        return vec
    except Exception as exc:
        logger.warning("embed_text failed (%s); caller should fall back to text search", exc)
        return None
