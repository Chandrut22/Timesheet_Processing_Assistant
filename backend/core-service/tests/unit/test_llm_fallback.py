"""The fallback LLM: settings rules, the model factory, and when the extraction agent
asks it. No network: the chat models are fakes."""

from datetime import UTC, datetime
from typing import Any

import httpx
import openai
import pytest
from langchain_core.messages import AIMessage
from pydantic import SecretStr, ValidationError

from src.config.settings import Settings, settings
from src.control.agents import extraction_agent as agent
from src.core.services.failures import AnswerTooLongError, explain
from src.data.clients import llm
from src.schemas.extraction import ExtractionResult

VALID = ExtractionResult(timesheets=[]).model_dump_json()


def make(**values: Any) -> Settings:
    return Settings(_env_file=None, **values)


# --- settings ------------------------------------------------------------------------------


def test_no_fallback_by_default_and_blank_means_unset() -> None:
    assert make().llm_fallback_model is None
    blank = make(llm_fallback_model="  ", llm_fallback_provider="", llm_fallback_base_url="")
    assert blank.llm_fallback_model is None and blank.llm_fallback_provider is None


def test_same_provider_and_host_reuse_the_main_base_url_and_key() -> None:
    s = make(
        llm_base_url="https://openrouter.ai/api/v1",
        llm_api_key="main-key",
        llm_fallback_model="qwen/qwen3-32b",
    )
    assert s.llm_fallback_provider_effective == "openai"
    assert s.llm_fallback_base_url_effective == "https://openrouter.ai/api/v1"
    assert s.llm_fallback_api_key_effective is not None
    assert s.llm_fallback_api_key_effective.get_secret_value() == "main-key"


def test_a_different_provider_inherits_neither_base_url_nor_key() -> None:
    s = make(
        llm_base_url="https://openrouter.ai/api/v1",
        llm_api_key="main-key",
        llm_fallback_model="claude-sonnet",
        llm_fallback_provider="anthropic",
        llm_fallback_api_key="other-key",
    )
    assert s.llm_fallback_base_url_effective is None
    assert s.llm_fallback_api_key_effective is not None
    assert s.llm_fallback_api_key_effective.get_secret_value() == "other-key"


def test_the_main_key_is_never_sent_to_another_host() -> None:
    with pytest.raises(ValidationError, match="LLM_FALLBACK_API_KEY"):
        make(
            llm_base_url="https://openrouter.ai/api/v1",
            llm_api_key="main-key",
            llm_fallback_model="m",
            llm_fallback_base_url="https://other.example/v1",
        )
    with pytest.raises(ValidationError, match="LLM_FALLBACK_API_KEY"):
        make(llm_api_key="main-key", llm_fallback_model="m", llm_fallback_provider="anthropic")


def test_a_fallback_identical_to_the_main_model_is_refused() -> None:
    with pytest.raises(ValidationError, match="same model"):
        make(llm_api_key="k", llm_model="gpt-x", llm_fallback_model="gpt-x")
    # same model name on another host is a real fallback
    assert make(
        llm_api_key="k",
        llm_model="gpt-x",
        llm_fallback_model="gpt-x",
        llm_fallback_base_url="https://backup.example/v1",
        llm_fallback_api_key="k2",
    )


# --- the factory -----------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_factories() -> Any:
    llm.get_chat_model.cache_clear()
    llm.get_fallback_chat_model.cache_clear()
    yield
    llm.get_chat_model.cache_clear()
    llm.get_fallback_chat_model.cache_clear()


def configure(monkeypatch: pytest.MonkeyPatch, **values: Any) -> None:
    defaults: dict[str, Any] = {
        "llm_api_key": SecretStr("main-key"),
        "llm_base_url": "https://main.example/v1",
        "llm_model": "main-model",
        "llm_provider": "openai",
        "llm_fallback_model": None,
        "llm_fallback_provider": None,
        "llm_fallback_base_url": None,
        "llm_fallback_api_key": None,
    }
    for key, value in {**defaults, **values}.items():
        monkeypatch.setattr(settings, key, value)


def test_no_fallback_model_is_built_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch)
    assert llm.get_fallback_chat_model() is None


def test_the_fallback_model_is_built_with_its_own_options(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(
        monkeypatch,
        llm_fallback_model="backup-model",
        llm_fallback_base_url="https://backup.example/v1",
        llm_fallback_api_key=SecretStr("backup-key"),
    )
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake_init(model: str, **options: Any) -> str:
        calls.append((model, options))
        return f"model:{model}"

    monkeypatch.setattr(llm, "init_chat_model", fake_init)

    assert llm.get_fallback_chat_model() == "model:backup-model"  # type: ignore[comparison-overlap]
    assert llm.get_chat_model() == "model:main-model"  # type: ignore[comparison-overlap]
    backup, main = calls[0], calls[1]
    assert backup[1]["base_url"] == "https://backup.example/v1"
    assert backup[1]["api_key"] == "backup-key" and backup[1]["model_provider"] == "openai"
    assert backup[1]["timeout"] == settings.llm_timeout_s  # same limits as the main model
    assert main[1]["base_url"] == "https://main.example/v1" and main[1]["api_key"] == "main-key"


# --- the agent -----------------------------------------------------------------------------------


class FakeModel:
    def __init__(self, *answers: str | Exception, finish_reason: str = "stop") -> None:
        self.answers = list(answers)
        self.calls = 0
        self.finish_reason = finish_reason

    async def ainvoke(self, _messages: Any) -> AIMessage:
        self.calls += 1
        answer = self.answers[min(self.calls, len(self.answers)) - 1]
        if isinstance(answer, Exception):
            raise answer
        return AIMessage(content=answer, response_metadata={"finish_reason": self.finish_reason})


def provider_down() -> openai.InternalServerError:
    request: Any = httpx.Request("POST", "https://main.example/v1/chat")
    response: Any = httpx.Response(503, request=request)
    return openai.InternalServerError("overloaded", response=response, body=None)


async def extract() -> ExtractionResult:
    return await agent.extract_timesheets(
        document_text="Mon 8", filename="a.csv", received_at=datetime.now(UTC)
    )


def use(monkeypatch: pytest.MonkeyPatch, main: FakeModel, fallback: FakeModel | None) -> None:
    monkeypatch.setattr(agent, "get_chat_model", lambda: main)
    monkeypatch.setattr(agent, "get_fallback_chat_model", lambda: fallback)
    monkeypatch.setattr(settings, "llm_fallback_model", "backup-model" if fallback else None)
    monkeypatch.setattr(settings, "llm_json_retries", 2)


async def test_the_main_model_answering_never_touches_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, fallback = FakeModel(VALID), FakeModel(VALID)
    use(monkeypatch, main, fallback)
    await extract()
    assert (main.calls, fallback.calls) == (1, 0)


async def test_a_provider_outage_is_answered_by_the_fallback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    main, fallback = FakeModel(provider_down()), FakeModel(VALID)
    use(monkeypatch, main, fallback)
    with caplog.at_level("WARNING"):
        result = await extract()
    assert result.timesheets == [] and (main.calls, fallback.calls) == (1, 1)
    assert "fallback model backup-model" in caplog.text
    assert "Mon 8" not in caplog.text  # the document never goes into the log


async def test_invalid_json_from_the_main_model_falls_back_after_its_own_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main, fallback = FakeModel("this is not json"), FakeModel(VALID)
    use(monkeypatch, main, fallback)
    await extract()
    assert main.calls == 3  # first try + llm_json_retries (2): the main model gets its chances
    assert fallback.calls == 1


async def test_a_cut_off_answer_does_not_fall_back(monkeypatch: pytest.MonkeyPatch) -> None:
    main, fallback = FakeModel('{"timesheets": [', finish_reason="length"), FakeModel(VALID)
    use(monkeypatch, main, fallback)
    with pytest.raises(AnswerTooLongError):
        await extract()
    assert fallback.calls == 0


async def test_without_a_fallback_errors_are_as_before(monkeypatch: pytest.MonkeyPatch) -> None:
    use(monkeypatch, FakeModel(provider_down()), None)
    with pytest.raises(agent.ExtractionError, match="The LLM call failed") as caught:
        await extract()
    assert isinstance(caught.value.__cause__, openai.InternalServerError)
    use(monkeypatch, FakeModel("not json"), None)
    with pytest.raises(agent.ExtractionError, match="No valid ExtractionResult"):
        await extract()


async def test_both_models_failing_names_both_and_keeps_an_outage_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, FakeModel(provider_down()), FakeModel("not json"))
    with pytest.raises(agent.ExtractionError) as caught:
        await extract()
    message = str(caught.value)
    assert "main model failed" in message and "InternalServerError" in message
    assert "fallback model" in message
    # the main model's outage was temporary, so the job is still retried later
    assert explain(caught.value).temporary


async def test_both_returning_unusable_answers_is_retried_later_like_any_ai_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    use(monkeypatch, FakeModel("not json"), FakeModel("also not json"))
    with pytest.raises(agent.ExtractionError) as caught:
        await extract()
    assert explain(caught.value).temporary  # as before: the worker tries the job again later
