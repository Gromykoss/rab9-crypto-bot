"""Pure analysis-filter decisions shared by enrichment and queue routing."""


def _as_percent(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number * 100 if 0 <= number <= 1 else number


def concentration_flag(top10_pct, threshold_pct=50.0) -> str:
    """Flag excessive top-10 concentration; accept fraction and percent forms."""
    concentration = _as_percent(top10_pct)
    threshold = _as_percent(threshold_pct)
    if concentration is None or threshold is None or concentration <= threshold:
        return ""
    return f"⚠️ CONCENTRATION: top-10 {concentration:.1f}% > {threshold:.1f}%"


def social_weight(sentiment=None, *, confirmed=False, threshold=0.7, penalty=0.25, has_x=None):
    """Return priority multiplier and verdict flag for per-token sentiment.

    Missing X/sentiment is neutral and never blocks analysis. ``has_x`` is kept
    explicit in the domain API so callers cannot confuse absence with negative.
    """
    score = _as_percent(sentiment)
    limit = _as_percent(threshold)
    if not confirmed or score is None or limit is None or score <= limit:
        return 1.0, ""
    bounded_penalty = min(max(float(penalty), 0.0), 1.0)
    return 1.0 - bounded_penalty, f"⚠️ SOCIAL NEGATIVE: {score:.1f}% > {limit:.1f}%"


__all__ = ["concentration_flag", "social_weight"]
