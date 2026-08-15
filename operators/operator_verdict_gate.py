"""Оператор fail-closed gate для результата loop verifier."""

from .verdict import CheckResult, Verdict


DEFAULT_VERDICT = "REJECT"
REJECT_VERDICTS = frozenset({"FAIL", "REJECT"})


def check_verifier(verdict, available: bool, fixed_text=None) -> CheckResult:
    """Разрешает публикацию только при доступном verifier и допустимом вердикте."""

    if not available:
        return CheckResult(Verdict.REJECT, "verifier unavailable; suppressing analysis")

    normalized = "" if verdict is None else str(verdict).strip().upper()

    if normalized == "PASS":
        return CheckResult(Verdict.ALLOW, "verifier passed")

    if normalized == "FLAG":
        fixed = "" if fixed_text is None else str(fixed_text).strip()
        if fixed:
            return CheckResult(Verdict.ALLOW, "flagged, исправлен переписанным текстом")
        return CheckResult(Verdict.HOLD, "flagged, требует ручного взгляда")

    if normalized in REJECT_VERDICTS:
        return CheckResult(Verdict.REJECT, f"verifier verdict is {normalized}")

    return CheckResult(Verdict.REJECT, f"unknown verifier verdict: {normalized or DEFAULT_VERDICT}")


__all__ = ["DEFAULT_VERDICT", "REJECT_VERDICTS", "check_verifier"]
