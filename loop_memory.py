"""Loop Memory for RAB9 — persistent state across analysis cycles.

Tracks: analyzed tokens, verdict history, sentiment trends, duplicates.
Survives restarts via JSON file on disk.

Pattern: loop-engineering — memory on disk, not in context.
"""
import json
import os
import time
from collections import deque

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "loop_state.json")
MAX_HISTORY = 200  # Keep last 200 analyses


def load_state() -> dict:
    """Load or initialize loop state."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {
        "analyses": [],       # Recent analyses [{address, token, ts, verdict, tier}]
        "duplicates": 0,      # Count of re-analyzed tokens
        "total": 0,           # Total analyses ever
        "last_cleanup": 0,    # Timestamp of last state cleanup
    }


def save_state(state: dict):
    """Persist state atomically."""
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def record_analysis(address: str, token_name: str, verdict: str, tier: str = ""):
    """Record a completed analysis. Detects and flags duplicates."""
    state = load_state()
    now = int(time.time())
    state["total"] += 1

    # Check for duplicate (same address analyzed recently)
    recent_addresses = {a["address"] for a in state["analyses"][-50:]}
    is_duplicate = address in recent_addresses

    entry = {
        "address": address[:12] + "...",
        "token": token_name,
        "ts": now,
        "verdict": verdict,
        "tier": tier,
        "duplicate": is_duplicate,
    }
    state["analyses"].append(entry)
    if is_duplicate:
        state["duplicates"] += 1

    # Trim history
    if len(state["analyses"]) > MAX_HISTORY:
        state["analyses"] = state["analyses"][-MAX_HISTORY:]

    # Periodic cleanup (every 6 hours)
    if now - state.get("last_cleanup", 0) > 21600:
        state["analyses"] = state["analyses"][-MAX_HISTORY:]
        state["last_cleanup"] = now

    save_state(state)
    return {"duplicate": is_duplicate, "total": state["total"], "duplicates": state["duplicates"]}


def get_sentiment_trend(token_name: str, hours: int = 24) -> dict:
    """Get sentiment trend for a token over last N hours."""
    state = load_state()
    now = int(time.time())
    cutoff = now - hours * 3600

    recent = [
        a for a in state["analyses"]
        if a["ts"] > cutoff and token_name.upper() in a.get("token", "").upper()
    ]

    verdicts = [a["verdict"] for a in recent]
    return {
        "count": len(recent),
        "verdicts": verdicts,
        "trend": "improving" if "🟢" in str(verdicts[-1:]) and "🔴" in str(verdicts[:1])
                else "stable" if len(set(verdicts[-3:])) <= 1
                else "mixed",
    }


def should_skip(address: str, cooldown_minutes: int = 30) -> bool:
    """Check if token was analyzed recently — skip if within cooldown."""
    state = load_state()
    now = int(time.time())
    cutoff = now - cooldown_minutes * 60

    for a in reversed(state["analyses"]):
        if a["address"].startswith(address[:8]) and a["ts"] > cutoff:
            return True
    return False


def get_stats() -> dict:
    """Return loop statistics."""
    state = load_state()
    analyses = state["analyses"]
    if not analyses:
        return {"total": 0, "duplicates": 0, "last_24h": 0}

    now = int(time.time())
    last_24h = sum(1 for a in analyses if a["ts"] > now - 86400)
    dupes_24h = sum(1 for a in analyses if a.get("duplicate") and a["ts"] > now - 86400)

    return {
        "total": state["total"],
        "duplicates": state["duplicates"],
        "last_24h": last_24h,
        "dupes_24h": dupes_24h,
        "history_size": len(analyses),
    }
