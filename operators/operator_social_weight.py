"""Offline per-token social sentiment (no network, no LLM)."""

from __future__ import annotations

import re

from radar_x import SPAM_PATTERNS, is_spam_text

_POST_RE = re.compile(r"^@(\S+)\s+\([^)]+\):\s*(.*)$", re.DOTALL)

NEGATIVE_TERMS = (
    "scam",
    "rug",
    "rugged",
    "honeypot",
    "drain",
    "dump",
    "stay away",
    "avoid",
    "don't buy",
    "dont buy",
    "скам",
    "развод",
    "мошен",
    "обман",
    "слив",
    "дамп",
)

# Порядок: длинные фразы первыми (stay away, don't buy).
_SORTED_TERMS = sorted(NEGATIVE_TERMS, key=len, reverse=True)
_TERM_PATTERNS = [
    (
        term,
        re.compile(
            r"(?<![\w$])"
            + re.escape(term).replace(r"\ ", r"\s+")
            + r"(?![\w$])",
            re.IGNORECASE,
        ),
    )
    for term in _SORTED_TERMS
]

_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|anti|ain'?t|нет|не|без)\b",
    re.IGNORECASE,
)


def _mask_token_mentions(text: str, token_symbol: str | None) -> str:
    if not token_symbol or token_symbol == "?":
        return text
    sym = token_symbol.strip().lstrip("$#")
    if not sym:
        return text
    masked = text
    for variant in (sym, f"${sym}", f"#{sym}"):
        masked = re.sub(re.escape(variant), " ", masked, flags=re.IGNORECASE)
    return masked


def _negated_near(text: str, start: int) -> bool:
    window = text[max(0, start - 24) : start]
    if _NEGATION_RE.search(window):
        return True
    if re.search(r"anti[\s-]*$", window, re.IGNORECASE):
        return True
    return False


def _text_has_negative_term(text: str, token_symbol: str | None) -> bool:
    cleaned = _mask_token_mentions(text or "", token_symbol)
    lowered = cleaned.lower()
    for _term, pattern in _TERM_PATTERNS:
        match = pattern.search(lowered)
        if not match:
            continue
        if _negated_near(lowered, match.start()):
            continue
        return True
    return False


def _post_negative(text: str, *, token_symbol: str | None = None) -> bool:
    if is_spam_text(text):
        return False
    return _text_has_negative_term(text, token_symbol)


def _records_from_radar(radar: dict) -> list[dict]:
    records = radar.get("post_records")
    if isinstance(records, list) and records:
        return [r for r in records if isinstance(r, dict)]
    out = []
    for line in radar.get("posts") or []:
        m = _POST_RE.match(str(line).strip())
        if not m:
            continue
        out.append({"username": m.group(1).lower(), "text": m.group(2)})
    return out


def classify_negative(
    posts: list,
    *,
    min_authors: int = 2,
    negative_share_threshold: float = 0.7,
    token_symbol: str | None = None,
) -> tuple[float, bool, list[str]]:
    """Score 0..1, confirmed if ≥min_authors distinct authors and share ≥ threshold."""
    negatives: list[tuple[str, str]] = []
    non_spam = 0
    for item in posts:
        if isinstance(item, dict):
            username = str(item.get("username") or "?").lower().lstrip("@")
            text = str(item.get("text") or "")
        else:
            m = _POST_RE.match(str(item).strip())
            if not m:
                continue
            username, text = m.group(1).lower(), m.group(2)
        if is_spam_text(text):
            continue
        non_spam += 1
        if _post_negative(text, token_symbol=token_symbol):
            negatives.append((username, text[:80]))

    if non_spam == 0:
        return 0.0, False, ["no_non_spam_posts"]

    neg_authors = {u for u, _ in negatives}
    share = len(negatives) / non_spam
    score = min(1.0, share)
    reasons = [f"negative_share={share:.2f}", f"authors={len(neg_authors)}"]
    confirmed = len(neg_authors) >= min_authors and share >= negative_share_threshold
    if confirmed:
        reasons.append("confirmed")
    return score, confirmed, reasons


def classify_from_radar(
    radar: dict,
    *,
    min_authors: int = 2,
    negative_share_threshold: float = 0.7,
    token_symbol: str | None = None,
) -> tuple[float, bool, list[str]]:
    sym = token_symbol
    if not sym:
        sym = (radar.get("query") or "").split()[0] if radar.get("query") else None
    return classify_negative(
        _records_from_radar(radar),
        min_authors=min_authors,
        negative_share_threshold=negative_share_threshold,
        token_symbol=sym,
    )


def negative_sentiment_flag(confirmed: bool) -> str:
    if not confirmed:
        return ""
    return "⚠️ SOCIAL: подтверждённый негатив в X-обсуждении"


__all__ = [
    "classify_negative",
    "classify_from_radar",
    "negative_sentiment_flag",
    "_post_negative",
    "_text_has_negative_term",
]