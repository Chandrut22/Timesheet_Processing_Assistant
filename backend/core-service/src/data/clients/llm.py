"""The chat model used for extraction, built with LangChain's init_chat_model.

The provider is a setting, so switching between OpenAI-compatible APIs (Ollama Cloud,
Groq, OpenRouter, OpenAI) or native providers (Anthropic, Gemini) needs no code change:

    LLM_PROVIDER=openai   LLM_BASE_URL=https://ollama.com/v1   LLM_MODEL=gpt-oss:20b
"""

from functools import lru_cache
from typing import Any

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from src.config.settings import settings


class LLMNotConfiguredError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_chat_model() -> BaseChatModel:
    """Built once per process and reused (keeps the HTTP connection pool warm)."""
    if settings.llm_api_key is None:
        raise LLMNotConfiguredError("LLM_API_KEY is not set in .env.")

    options: dict[str, Any] = {
        "api_key": settings.llm_api_key.get_secret_value(),
        "temperature": 0,
        "timeout": settings.llm_timeout_s,
        "max_retries": 5,
    }
    if settings.llm_base_url:  # only for OpenAI-compatible endpoints
        options["base_url"] = settings.llm_base_url

    model: BaseChatModel = init_chat_model(
        settings.llm_model,
        model_provider=settings.llm_provider,
        **options,
    )
    return model
