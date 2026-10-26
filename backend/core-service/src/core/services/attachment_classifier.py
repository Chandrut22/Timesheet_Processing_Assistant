"""Optional attachment classifier: "is this document a timesheet?", asked after the
file is read and before the (slower, costlier) AI extraction.

This module is pure (no network, no database): the result type, the skip rule, and the
decision the worker takes. The Jev client is in handlers/http_clients/jev_client.py.

Safety rules (a wrongly skipped timesheet means hours that never get paid):
  - skip ONLY when the label is not "timesheet" AND P(timesheet) < CLASSIFIER_SKIP_BELOW
  - P(timesheet) unknown (answer format not understood), label "unclear", any error or
    timeout -> continue exactly as today
  - a manual reprocess never uses the classifier (a person asked for a full run)
  - shadow mode records what it WOULD do, and always continues"""

from dataclasses import dataclass
from enum import StrEnum

LABELS: dict[str, str] = {
    "timesheet": "Hours worked by one or more people, per day or per week (a timesheet, "
    "time card, attendance or hours sheet), in any layout, even partly filled or handwritten.",
    "invoice": "A bill or invoice asking for payment for goods or services.",
    "payslip": "A pay slip or salary statement already calculated for an employee.",
    "other": "Any other document: letters, contracts, reports, images, signatures.",
    "unclear": "Too little readable text, or no clear main purpose.",
}
TIMESHEET = "timesheet"


@dataclass(frozen=True, slots=True)
class ClassifierResult:
    label: str  # one of LABELS
    p_timesheet: float | None  # None = the answer had no usable probability for timesheet
    model: str
    duration_ms: int


class ClassifierError(Exception):
    """The classifier could not answer (not set up, timeout, HTTP error, bad answer)."""


class Decision(StrEnum):
    OFF = "off"  # classifier disabled: nothing recorded
    BYPASSED = "bypassed"  # manual reprocess: always extract
    CONTINUE = "continue"  # likely (or possibly) a timesheet: extract
    SKIP = "skip"  # very likely NOT a timesheet: no extraction
    SHADOW_SKIP = "shadow_skip"  # shadow mode: WOULD skip, but extracts anyway
    SHADOW_CONTINUE = "shadow_continue"
    ERROR = "error"  # classifier failed: extract as usual


def should_skip(result: ClassifierResult, threshold: float) -> bool:
    """Pure: skip only when it is clearly not a timesheet."""
    return (
        result.label != TIMESHEET
        and result.label != "unclear"
        and result.p_timesheet is not None
        and result.p_timesheet < threshold
    )


def decide(
    result: ClassifierResult | None,
    *,
    enabled: bool,
    shadow_only: bool,
    is_manual_reprocess: bool,
    threshold: float,
) -> Decision:
    """Pure: what the worker does with a classifier answer (None = it failed)."""
    if not enabled:
        return Decision.OFF
    if is_manual_reprocess:
        return Decision.BYPASSED
    if result is None:
        return Decision.ERROR
    skip = should_skip(result, threshold)
    if shadow_only:
        return Decision.SHADOW_SKIP if skip else Decision.SHADOW_CONTINUE
    return Decision.SKIP if skip else Decision.CONTINUE


def describe(result: ClassifierResult) -> str:
    """'invoice, 4% timesheet' / 'timesheet, 97% timesheet' / 'other, timesheet % unknown'."""
    share = "unknown" if result.p_timesheet is None else f"{result.p_timesheet:.0%}"
    return f"{result.label}, {share} timesheet"
