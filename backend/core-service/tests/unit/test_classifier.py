"""Optional attachment classifier (Jev): the skip rule, the decisions, the request we
send, the answers we accept, and every failure falling back to normal extraction."""

import asyncio
import json
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from src.config.settings import Settings, settings
from src.core.services.attachment_classifier import (
    ClassifierError,
    ClassifierResult,
    Decision,
    decide,
    describe,
    should_skip,
)
from src.handlers.http_clients import jev_client


def result(label: str, p: float | None) -> ClassifierResult:
    return ClassifierResult(label=label, p_timesheet=p, model="jev-1.13.0", duration_ms=12)


# --- the skip rule ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "p", "skip"),
    [
        ("invoice", 0.04, True),  # clearly not a timesheet
        ("invoice", 0.19, True),
        ("invoice", 0.20, False),  # at the threshold: keep it
        ("invoice", 0.55, False),  # unsure: keep it
        ("timesheet", 0.01, False),  # labelled timesheet: never skipped
        ("other", None, False),  # probability unknown: never skipped
        ("unclear", 0.01, False),  # "unclear" is never skipped
        ("payslip", 0.0, True),
    ],
)
def test_skip_only_when_clearly_not_a_timesheet(label: str, p: float | None, skip: bool) -> None:
    assert should_skip(result(label, p), 0.2) is skip


def test_decisions() -> None:
    sure_no = result("invoice", 0.03)
    yes = result("timesheet", 0.97)

    def run(found: ClassifierResult | None, enabled: bool, shadow: bool) -> Decision:
        return decide(
            found, enabled=enabled, shadow_only=shadow, is_manual_reprocess=False, threshold=0.2
        )

    assert run(sure_no, False, False) == Decision.OFF
    assert run(sure_no, True, False) == Decision.SKIP
    assert run(yes, True, False) == Decision.CONTINUE
    assert run(sure_no, True, True) == Decision.SHADOW_SKIP
    assert run(yes, True, True) == Decision.SHADOW_CONTINUE
    assert run(None, True, False) == Decision.ERROR
    assert (
        decide(sure_no, enabled=True, shadow_only=False, is_manual_reprocess=True, threshold=0.2)
        == Decision.BYPASSED
    )
    assert describe(sure_no) == "invoice, 3% timesheet"
    assert describe(result("other", None)) == "other, unknown timesheet"


# --- settings ----------------------------------------------------------------------------


def test_off_by_default_and_needs_a_key_to_switch_on() -> None:
    defaults = Settings(_env_file=None)
    assert defaults.classifier_enabled is False
    assert defaults.classifier_shadow_only is True
    assert defaults.classifier_skip_below == 0.2
    assert defaults.jev_model == "jev-1.13.0"
    with pytest.raises(ValidationError, match="JEV_API_KEY"):
        Settings(_env_file=None, classifier_enabled=True)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, classifier_skip_below=1.5)


# --- the request we send -------------------------------------------------------------------


def test_request_sends_only_the_start_of_the_document(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "classifier_max_chars", 500)
    body = jev_client.build_request("x" * 2000)
    assert body["model"] == "jev-1.13.0"
    assert len(body["state"]) == 500
    question = body["questions"]["document_kind"]
    assert question["type"] == "choice"
    assert set(question["criteria"]) == {"timesheet", "invoice", "payslip", "other", "unclear"}
    assert set(body) == {"model", "state", "questions"}  # no file name, sender or email text


# --- the answers we accept -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("answer", "label", "p"),
    [
        (
            {"choice": "invoice", "probabilities": {"timesheet": 0.05, "invoice": 0.9}},
            "invoice",
            0.05,
        ),
        (
            {"choice": "other", "options": [{"option": "timesheet", "probability": 0.12}]},
            "other",
            0.12,
        ),
        (
            {"choice": "invoice", "probabilities": [{"label": "timesheet", "p": 0.07}]},
            "invoice",
            0.07,
        ),
        ({"choice": "timesheet", "confidence": 0.93}, "timesheet", 0.93),
        ({"choice": "invoice", "confidence": 0.93}, "invoice", None),  # no P(timesheet)
        ({"choice": "Timesheet "}, "timesheet", None),
    ],
)
def test_answer_shapes(answer: dict[str, Any], label: str, p: float | None) -> None:
    parsed = jev_client.parse_response({"answers": {"document_kind": answer}})
    assert (parsed.label, parsed.p_timesheet) == (label, p)


@pytest.mark.parametrize(
    "data",
    [{}, {"answers": {}}, {"answers": {"document_kind": {"choice": "receipt"}}}, ["nope"]],
)
def test_unusable_answers_raise(data: Any) -> None:
    with pytest.raises(ClassifierError):
        jev_client.parse_response(data)


# --- the HTTP call ------------------------------------------------------------------------


def call(handler: Any, monkeypatch: pytest.MonkeyPatch, text: str = "Mon 8 Tue 8") -> Any:
    monkeypatch.setattr(settings, "jev_api_key", SecretStr("test-key"))
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return asyncio.run(jev_client.classify(text, client=client))


def test_classify_posts_with_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers["Authorization"]
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        answer = {"choice": "timesheet", "probabilities": {"timesheet": 0.96}}
        return httpx.Response(200, json={"answers": {"document_kind": answer}})

    parsed = call(handler, monkeypatch)
    assert parsed.label == "timesheet" and parsed.p_timesheet == 0.96
    assert seen["auth"] == "Bearer test-key"
    assert seen["url"] == settings.jev_url
    assert seen["body"]["state"] == "Mon 8 Tue 8"


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(500, text="boom"),
        lambda request: httpx.Response(401, json={"error": "bad key"}),
        lambda request: httpx.Response(200, text="not json"),
    ],
)
def test_failures_become_classifier_errors(handler: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ClassifierError):
        call(handler, monkeypatch)


def test_timeout_becomes_a_classifier_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ClassifierError):
        call(handler, monkeypatch)


def test_no_key_or_no_text(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "jev_api_key", None)
    with pytest.raises(ClassifierError, match="JEV_API_KEY"):
        asyncio.run(jev_client.classify("text"))
    with pytest.raises(ClassifierError, match="No text"):
        call(lambda request: httpx.Response(200), monkeypatch, text="   ")


# --- the evaluation tool --------------------------------------------------------------


def test_evaluation_counts_wrong_skips_and_savings(tmp_path: Any) -> None:
    from src.tools.evaluate_classifier import evaluate, report, summary, write_csv

    for folder, names in {
        "timesheet": ["a.txt", "b.txt"],
        "not_timesheet": ["c.txt", "d.txt"],
    }.items():
        (tmp_path / folder).mkdir()
        for name in names:
            (tmp_path / folder / name).write_text(name)
    answers = {
        "a.txt": result("timesheet", 0.95),
        "b.txt": result("other", 0.15),  # a real timesheet the classifier gets wrong
        "c.txt": result("invoice", 0.02),
        "d.txt": result("other", None),  # no probability: never skipped
    }

    async def fake_classify(text: str) -> ClassifierResult:
        return answers[text]

    rows = asyncio.run(evaluate(tmp_path, lambda p: p.read_text(), fake_classify))
    at_02, at_01 = report(rows, 0.2), report(rows, 0.1)
    assert at_02.wrongly_skipped == ["timesheet/b.txt"] and at_02.saved == 1
    assert at_01.wrongly_skipped == [] and at_01.saved == 1
    text = summary(rows)
    assert "Safe thresholds (no timesheet skipped): 0.1" in text
    assert "no usable P(timesheet)" in text
    write_csv(rows, tmp_path / "out.csv")
    assert (tmp_path / "out.csv").read_text().count("\n") == 5
