"""Enforced-операторы RAB9: чистые проверки без side-effects."""

from .operator_config_guard import MUTATING_ACTIONS, check_mutation
from .operator_destination import ALLOWED_DESTINATIONS, check_destination
from .operator_safety import RUGCHECK_ALLOW_LEVELS, RUGCHECK_DROP_LEVELS, check_safety
from .operator_verdict_gate import DEFAULT_VERDICT, REJECT_VERDICTS, check_verifier
from .verdict import CheckResult, Verdict


__all__ = [
    "ALLOWED_DESTINATIONS",
    "CheckResult",
    "DEFAULT_VERDICT",
    "MUTATING_ACTIONS",
    "REJECT_VERDICTS",
    "RUGCHECK_ALLOW_LEVELS",
    "RUGCHECK_DROP_LEVELS",
    "Verdict",
    "check_destination",
    "check_mutation",
    "check_safety",
    "check_verifier",
]
