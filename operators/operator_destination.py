"""Оператор разрешённых Telegram destination для публикаций RAB9."""

from .verdict import CheckResult, Verdict


ALLOWED_DESTINATIONS = frozenset({"-1004425561477", "-1003979753733"})


def check_destination(chat_id) -> CheckResult:
    """Разрешает отправку только в явно утверждённые Telegram-чаты."""

    if chat_id is None:
        return CheckResult(Verdict.BLOCK, "destination is empty")

    destination = str(chat_id)
    if not destination:
        return CheckResult(Verdict.BLOCK, "destination is empty")

    if destination in ALLOWED_DESTINATIONS:
        return CheckResult(Verdict.ALLOW, "destination is allowed")

    return CheckResult(Verdict.BLOCK, f"destination is not allowed: {destination}")


__all__ = ["ALLOWED_DESTINATIONS", "check_destination"]
