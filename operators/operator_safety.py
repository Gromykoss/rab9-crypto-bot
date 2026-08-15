"""Оператор safety-фильтра для scam/rug/dead-фаз."""

from .verdict import CheckResult, Verdict


RUGCHECK_DROP_LEVELS = frozenset({"rugged"})
RUGCHECK_ALLOW_LEVELS = frozenset({"low", "medium"})


def check_safety(honeypot_status, rugcheck_level, phase) -> CheckResult:
    """Блокирует публикацию анализа при детерминированных scam/safety признаках."""

    honeypot = "" if honeypot_status is None else str(honeypot_status).strip().lower()
    rugcheck = "" if rugcheck_level is None else str(rugcheck_level).strip().lower()
    phase_value = "" if phase is None else str(phase).strip().lower()

    if honeypot in {"fail", "true", "1"}:
        return CheckResult(Verdict.DROP, "honeypot check failed")

    if rugcheck in RUGCHECK_DROP_LEVELS:
        return CheckResult(Verdict.DROP, f"rugcheck level is {rugcheck}")

    if phase_value == "dead":
        return CheckResult(Verdict.INCONCLUSIVE, "token phase is DEAD (uncertain)")

    if honeypot == "pass" and rugcheck in RUGCHECK_ALLOW_LEVELS:
        return CheckResult(Verdict.ALLOW, "honeypot and rugcheck passed")

    return CheckResult(Verdict.INCONCLUSIVE, "safety not confirmed")


__all__ = ["RUGCHECK_ALLOW_LEVELS", "RUGCHECK_DROP_LEVELS", "check_safety"]
