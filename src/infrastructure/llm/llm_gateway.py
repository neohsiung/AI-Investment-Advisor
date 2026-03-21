"""
LLM Gateway — Infrastructure Layer Implementations.
模型層閘道 — 基礎設施層實作。

Implements ILLMGateway for each supported LLM provider (OpenRouter, Google Gemini, OpenAI).
All HTTP-level details are isolated here, keeping BaseAgent and Domain layers pure.

遵循規範:
  - 規範一 (Clean Architecture): 基礎設施層隔離所有外部 HTTP 依賴
  - 規範十 (MCP 整合): 標準化 LLM 通訊介面
  - 規範十三 (Atomic Workflows): 原子化 LLM 調用
"""

import re
import time
import logging
import requests
from typing import List, Optional

from src.domain.interfaces import ILLMGateway, Message, LLMConfig

logger = logging.getLogger(__name__)


def _redact_secrets(text_value: str) -> str:
    """
    Best-effort redaction of common secret patterns before logging.
    規範十三: 敏感資訊零容忍 (No-Hardcoded-Secrets)
    """
    if not isinstance(text_value, str):
        return text_value

    redacted = text_value
    redacted = re.sub(
        r"(Authorization:\s*Bearer\s+)[^\s\"']+",
        r"\1[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"(Bearer\s+)[^\s\"']+",
        r"\1[REDACTED]",
        redacted,
        flags=re.IGNORECASE,
    )
    redacted = re.sub(
        r"([\"']?api_key[\"']?\s*[:=]\s*[\"'])[A-Za-z0-9_\-\.]+([\"'])",
        r"\1[REDACTED]\2",
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted


class OpenRouterGateway(ILLMGateway):
    """
    LLM Gateway for OpenRouter API.
    OpenRouter API 的 LLM 閘道實作。
    """

    def chat(self, messages: List[Message], config: LLMConfig) -> str:
        url = config.base_url or "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:8501",
            "X-Title": "AI Investment Advisor",
        }
        data = {
            "model": config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if config.temperature is not None:
            data["temperature"] = config.temperature

        response = requests.post(
            url, headers=headers, json=data,
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def embed(self, text: str, config: LLMConfig) -> List[float]:
        """OpenRouter embedding (uses /embeddings endpoint)."""
        url = config.base_url or "https://openrouter.ai/api/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": config.model,
            "input": text,
        }
        response = requests.post(
            url, headers=headers, json=data,
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]


class GeminiGateway(ILLMGateway):
    """
    LLM Gateway for Google Gemini API.
    Google Gemini API 的 LLM 閘道實作。
    """

    def chat(self, messages: List[Message], config: LLMConfig) -> str:
        model_id = config.model if config.model.startswith("models/") else f"models/{config.model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:generateContent?key={config.api_key}"
        headers = {"Content-Type": "application/json"}

        # Gemini uses a flat content structure:
        # Combine system + user messages into a single prompt
        combined_text = ""
        for m in messages:
            combined_text += m.content + "\n\n"

        data = {
            "contents": [{"parts": [{"text": combined_text.strip()}]}],
        }
        if config.temperature is not None:
            data["generationConfig"] = {"temperature": config.temperature}

        response = requests.post(
            url, headers=headers, json=data,
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]

    def embed(self, text: str, config: LLMConfig) -> List[float]:
        """Gemini embedding via embedContent API."""
        model_id = config.model if config.model.startswith("models/") else f"models/{config.model}"
        url = f"https://generativelanguage.googleapis.com/v1beta/{model_id}:embedContent?key={config.api_key}"
        headers = {"Content-Type": "application/json"}
        data = {"content": {"parts": [{"text": text}]}}

        response = requests.post(
            url, headers=headers, json=data,
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["embedding"]["values"]


class OpenAIGateway(ILLMGateway):
    """
    LLM Gateway for OpenAI-compatible APIs.
    OpenAI 相容 API 的 LLM 閘道實作。
    """

    def chat(self, messages: List[Message], config: LLMConfig) -> str:
        url = config.base_url or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": config.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }
        if config.temperature is not None:
            data["temperature"] = config.temperature

        response = requests.post(
            url, headers=headers, json=data,
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def embed(self, text: str, config: LLMConfig) -> List[float]:
        """OpenAI embedding via /v1/embeddings."""
        url = config.base_url.rstrip("/").replace("/chat/completions", "") + "/embeddings" if config.base_url else "https://api.openai.com/v1/embeddings"
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": config.model,
            "input": text,
        }
        response = requests.post(
            url, headers=headers, json=data,
            timeout=config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]


class LLMGatewayFactory:
    """
    Factory for creating ILLMGateway instances based on provider name.
    基於供應商名稱建立 ILLMGateway 實例的工廠。

    遵循規範二 (DDD): 使用業務語言命名 (Gateway, Factory)
    遵循規範一 (Clean Architecture): 控制反轉，由 Factory 決定實作
    """

    _REGISTRY = {
        "OpenRouter": OpenRouterGateway,
        "openrouter": OpenRouterGateway,
        "Google Gemini": GeminiGateway,
        "google_gemini": GeminiGateway,
        "gemini": GeminiGateway,
        "OpenAI": OpenAIGateway,
        "openai": OpenAIGateway,
    }

    @classmethod
    def create(cls, provider: str) -> ILLMGateway:
        """
        Create an ILLMGateway for the given provider.
        為指定供應商建立 ILLMGateway。

        Args:
            provider: Provider name (e.g., "OpenRouter", "Google Gemini", "OpenAI")

        Returns:
            ILLMGateway implementation

        Raises:
            ValueError: If provider is not supported
        """
        gateway_cls = cls._REGISTRY.get(provider)
        if gateway_cls is None:
            supported = sorted(set(cls._REGISTRY.values()), key=lambda c: c.__name__)
            supported_names = [c.__name__ for c in supported]
            raise ValueError(
                f"Unsupported LLM provider: '{provider}'. "
                f"Supported: {supported_names}"
            )
        return gateway_cls()

    @classmethod
    def register(cls, provider_name: str, gateway_cls: type) -> None:
        """
        Register a custom provider gateway (for extension/testing).
        註冊自訂供應商閘道（用於擴展/測試）。
        """
        cls._REGISTRY[provider_name] = gateway_cls


class RetryLLMGateway(ILLMGateway):
    """
    Decorator Gateway that adds retry logic with exponential backoff.
    裝飾器閘道，新增指數退避重試邏輯。

    遵循規範七 (Graceful Degradation): 回退鏈模式
    """

    def __init__(self, inner: ILLMGateway, max_retries: int = 3):
        self._inner = inner
        self._max_retries = max_retries

    def chat(self, messages: List[Message], config: LLMConfig) -> str:
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return self._inner.chat(messages, config)
            except Exception as e:
                last_error = e
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"LLM chat attempt {attempt + 1}/{self._max_retries} failed: "
                    f"{_redact_secrets(str(e))}. Retrying in {wait}s..."
                )
                time.sleep(wait)
        raise last_error  # type: ignore[misc]

    def embed(self, text: str, config: LLMConfig) -> List[float]:
        last_error = None
        for attempt in range(self._max_retries):
            try:
                return self._inner.embed(text, config)
            except Exception as e:
                last_error = e
                wait = 2 ** (attempt + 1)
                logger.warning(
                    f"LLM embed attempt {attempt + 1}/{self._max_retries} failed: "
                    f"{_redact_secrets(str(e))}. Retrying in {wait}s..."
                )
                time.sleep(wait)
        raise last_error  # type: ignore[misc]


class MockLLMGateway(ILLMGateway):
    """
    Mock Gateway for testing and simulation mode (no API key).
    測試與模擬模式的 Mock 閘道（無 API 金鑰時使用）。
    """

    def __init__(self, default_response: str = None):
        self._default_response = default_response

    def chat(self, messages: List[Message], config: LLMConfig) -> str:
        if self._default_response:
            return self._default_response

        prompt_len = sum(len(m.content) for m in messages)
        return (
            f"### ⚠️ Simulation Mode (Missing API Key)\n\n"
            f"**Provider**: {config.provider}\n"
            f"**Model**: {config.model}\n\n"
            f"#### Analysis\n"
            f"- **Trend**: Neutral/Simulated.\n"
            f"- **Signal**: HOLD.\n"
            f"- **Reasoning**: System is running in simulation mode.\n\n"
            f"(Context received: {prompt_len} chars)"
        )

    def embed(self, text: str, config: LLMConfig) -> List[float]:
        """Returns zero vector for mock embedding."""
        return [0.0] * 1536
