"""Общие типы вердиктов для enforced-операторов RAB9."""

from dataclasses import dataclass
from enum import Enum


class Verdict(Enum):
    """Детерминированный результат проверки оператора."""

    ALLOW = "allow"
    BLOCK = "block"
    HOLD = "hold"
    DROP = "drop"
    REJECT = "reject"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True)
class CheckResult:
    """Результат проверки: вердикт и человекочитаемая причина."""

    verdict: Verdict
    reason: str


__all__ = ["CheckResult", "Verdict"]
