"""Оператор approval-gate для мутирующих действий конфигурации."""

from .verdict import CheckResult, Verdict


MUTATING_ACTIONS = frozenset({"systemd_edit", "env_edit", "config_edit", "deploy", "restart_service"})


def check_mutation(action: str, approval_token: str | None) -> CheckResult:
    """Требует непустой approval-token для действий, меняющих окружение."""

    normalized_action = "" if action is None else str(action).strip().lower()
    token = (approval_token or "").strip()

    if not normalized_action:
        return CheckResult(Verdict.BLOCK, "empty mutation action")

    if normalized_action not in MUTATING_ACTIONS:
        return CheckResult(Verdict.ALLOW, "action is not mutating")

    if token:
        return CheckResult(Verdict.ALLOW, "approval token present")

    return CheckResult(Verdict.HOLD, "mutating action requires approval")


__all__ = ["MUTATING_ACTIONS", "check_mutation"]
