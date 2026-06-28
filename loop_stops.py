"""RAB9 Loop Stop Conditions — budget gates and quality thresholds.

Every loop needs explicit stop conditions (CyrilXBT pattern).
Without them, the loop either runs forever or stops silently.
"""
import time

# ── Budget Gates ──
MAX_DAILY_ANALYSES = 100     # Hard cap per 24h
MAX_PER_HOUR = 20             # Rate limit
COOLDOWN_MINUTES = 5          # Minimum gap between same token

# ── Quality Gates ──
MIN_VERIFIER_SCORE = 40       # Below this → FAIL (suppress)
FLAG_THRESHOLD = 70           # Below this → FLAG (correct)
# Above FLAG_THRESHOLD → PASS

# ── Cost Gates ──
MAX_TOKENS_PER_ANALYSIS = 5000  # Grok max_tokens cap
MAX_COST_PER_DAY_USD = 0.50     # ~$0.50/day budget

# ── Runtime state ──
_daily_count = 0
_hourly_count = 0
_last_hour_reset = 0
_last_day_reset = 0
_daily_cost_est = 0.0


def _reset_counters():
    global _daily_count, _hourly_count, _last_hour_reset, _last_day_reset, _daily_cost_est
    now = int(time.time())
    
    # Reset hourly
    if now - _last_hour_reset >= 3600:
        _hourly_count = 0
        _last_hour_reset = now
    
    # Reset daily
    if now - _last_day_reset >= 86400:
        _daily_count = 0
        _daily_cost_est = 0.0
        _last_day_reset = now


def check_budget(token_cost_est: float = 0.005) -> dict:
    """Check budget gates before processing. Returns {allowed, reason}."""
    _reset_counters()
    
    if _daily_count >= MAX_DAILY_ANALYSES:
        return {"allowed": False, "reason": f"daily cap ({MAX_DAILY_ANALYSES})"}
    
    if _hourly_count >= MAX_PER_HOUR:
        return {"allowed": False, "reason": f"hourly cap ({MAX_PER_HOUR})"}
    
    if _daily_cost_est + token_cost_est > MAX_COST_PER_DAY_USD:
        return {"allowed": False, "reason": f"daily cost cap (${MAX_COST_PER_DAY_USD})"}
    
    return {"allowed": True, "reason": ""}


def record_usage(token_cost_est: float = 0.005):
    """Record that an analysis was performed."""
    global _daily_count, _hourly_count, _daily_cost_est
    _daily_count += 1
    _hourly_count += 1
    _daily_cost_est += token_cost_est


def get_verdict(verifier_score: int) -> str:
    """Map verifier score to action."""
    if verifier_score < MIN_VERIFIER_SCORE:
        return "FAIL"
    elif verifier_score < FLAG_THRESHOLD:
        return "FLAG"
    return "PASS"
