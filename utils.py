from datetime import datetime, timezone


def utc_now_text():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except Exception:
        return default


def safe_div(a, b):
    a = safe_float(a)
    b = safe_float(b)

    if b == 0:
        return None

    return a / b


def format_usd(value):
    value = safe_float(value, None)

    if value is None:
        return "n/a"

    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"

    if value >= 1_000:
        return f"${value / 1_000:.2f}K"

    return f"${value:.2f}"


def format_percent(value):
    value = safe_float(value, None)

    if value is None:
        return "n/a"

    return f"{value:.2f}%"


def format_ratio(value):
    if value is None:
        return "n/a"

    return f"{value:.2f}x"


def ms_to_utc(ms):
    value = safe_int(ms, None)

    if value is None:
        return None

    try:
        return datetime.fromtimestamp(value / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return None


def pair_age_hours(ms):
    value = safe_int(ms, None)

    if value is None:
        return None

    try:
        created = datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        return (now - created).total_seconds() / 3600
    except Exception:
        return None


def split_text(text: str, limit: int = 3800):
    if len(text) <= limit:
        return [text]

    chunks = []
    current = ""

    for line in text.splitlines():
        if len(current) + len(line) + 1 > limit:
            if current:
                chunks.append(current)
            current = line
        else:
            current += ("\n" if current else "") + line

    if current:
        chunks.append(current)

    return chunks
