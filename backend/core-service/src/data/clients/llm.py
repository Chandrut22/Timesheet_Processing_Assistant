from functools import lru_cache

from langchain_openai import ChatOpenAI

from src.config.settings import settings


class LLMNotConfiguredError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_chat_model() -> ChatOpenAI:
    if settings.llm_api_key is None:
        raise LLMNotConfiguredError("LLM_API_KEY is not set in .env.")
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=0,  # same document -> same answer
        timeout=settings.llm_timeout_s,
        max_retries=2,
    )
