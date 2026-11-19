"""Pure analysis-filter decisions for verdict construction."""


def _as_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def concentration_flag(top10_value, threshold_pct=50.0, *, source="gmgn_percent") -> str:
    """Flag excessive top-10 concentration with an explicit source scale."""
    concentration = _as_number(top10_value)
    threshold = _as_number(threshold_pct)
    if concentration is not None and source == "fraction":
        concentration *= 100
    elif source != "gmgn_percent":
        return ""
    if concentration is None or threshold is None or concentration <= threshold:
        return ""
    return f"⚠️ CONCENTRATION: top-10 {concentration:.1f}% > {threshold:.1f}%"
__all__ = ["concentration_flag"]
