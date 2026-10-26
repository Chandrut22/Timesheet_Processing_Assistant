"""The chat model used for extraction, built with LangChain's init_chat_model.

The provider is a setting, so switching between OpenAI-compatible APIs (Ollama Cloud,
Groq, OpenRouter, OpenAI) or native providers (Anthropic, Gemini) needs no code change:

    LLM_PROVIDER=openai   LLM_BASE_URL=https://ollama.com/v1   LLM_MODEL=gpt-oss:20b

An optional fallback model (LLM_FALLBACK_MODEL, see get_fallback_chat_model) is asked when
the main one cannot answer: the extraction agent decides when (extraction_agent.py).
"""

from functools import lru_cache
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from src.config.settings import settings


class LLMNotConfiguredError(RuntimeError):
    pass


def _build(model: str, provider: str, base_url: str | None, api_key: SecretStr) -> BaseChatModel:
    options: dict[str, Any] = {
        "api_key": api_key.get_secret_value(),
        "temperature": 0,
        "timeout": settings.llm_timeout_s,
        # One quick retry for a dropped connection. The worker retries longer outages
        # itself (WORKER_MAX_ATTEMPTS), so retries are not multiplied layer on layer.
        "max_retries": settings.llm_max_retries,
    }
    if settings.llm_max_output_tokens:  # a cut-off answer is detected and reported
        options["max_tokens"] = settings.llm_max_output_tokens
    if base_url:  # only for OpenAI-compatible endpoints
        options["base_url"] = base_url

    built: BaseChatModel = init_chat_model(model, model_provider=provider, **options)
    return built


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """Built once per process and reused (keeps the HTTP connection pool warm)."""
    if settings.llm_api_key is None:
        raise LLMNotConfiguredError("LLM_API_KEY is not set in .env.")
    return _build(
        settings.llm_model, settings.llm_provider, settings.llm_base_url, settings.llm_api_key
    )


@lru_cache(maxsize=1)
def get_fallback_chat_model() -> BaseChatModel | None:
    """The fallback model, or None when LLM_FALLBACK_MODEL is not set. Same options as the
    main model (timeout, retries, output cap); its own provider, base URL and key, with the
    safe defaults described in settings.py."""
    if settings.llm_fallback_model is None:
        return None
    key = settings.llm_fallback_api_key_effective
    if key is None:  # the settings validator already refuses this
        raise LLMNotConfiguredError("LLM_FALLBACK_API_KEY is not set in .env.")
    return _build(
        settings.llm_fallback_model,
        settings.llm_fallback_provider_effective,
        settings.llm_fallback_base_url_effective,
        key,
    )


@lru_cache(maxsize=1)
def get_vision_model() -> BaseChatModel:
    """The vision-language model that classifies and transcribes photos and scans
    (VISION_*), built like the extraction model, once per process."""
    if not settings.vision_model or not settings.vision_base_url:
        raise LLMNotConfiguredError("VISION_BASE_URL and VISION_MODEL are not set in .env.")
    key = settings.vision_api_key.get_secret_value() if settings.vision_api_key else ""
    model: BaseChatModel = init_chat_model(
        settings.vision_model,
        model_provider=settings.vision_provider,
        # Self-hosted servers usually need no key, but the OpenAI client insists on one.
        api_key=key or "not-needed",
        base_url=settings.vision_base_url,
        temperature=0,
        timeout=settings.vision_timeout_s,
        max_retries=settings.vision_max_retries,
        max_tokens=settings.vision_max_output_tokens,
    )
    return model
