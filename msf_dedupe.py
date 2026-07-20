"""MSF signal deduplication by address within 24-hour window.

Stores last N unique addresses in rab9/data/msf_dedupe.json.
Second hit within 24h returns a compact "already analyzed" message.

Usage:
    from msf_dedupe import check_dedupe, record_address
    deduped = check_dedupe("So111...")
    if deduped:
        return deduped  # Short message — don't re-analyze
    record_address("So111...", score=72, tier="SOLID")
"""

from __future__ import annotations

import json
import os
import time
from typing import Any


DEDUPE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "msf_dedupe.json"
)
MAX_ENTRIES = 500
WINDOW_SECONDS = 24 * 3600  # 24 hours


def _load() -> list[dict[str, Any]]:
    """Load dedupe store, return empty list if missing/corrupt."""
    try:
        if os.path.exists(DEDUPE_PATH):
            with open(DEDUPE_PATH, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return []


def _save(entries: list[dict[str, Any]]) -> None:
    """Save dedupe store, trimming to MAX_ENTRIES."""
    os.makedirs(os.path.dirname(DEDUPE_PATH), exist_ok=True)
    entries = entries[-MAX_ENTRIES:]  # Keep most recent
    with open(DEDUPE_PATH, "w") as f:
        json.dump(entries, f, indent=2)


def _prune(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove entries older than 24h."""
    cutoff = time.time() - WINDOW_SECONDS
    return [e for e in entries if e.get("ts", 0) >= cutoff]


def check_dedupe(address: str) -> str | None:
    """Check if address was analyzed within last 24h.

    Args:
        address: Solana token/pair address.

    Returns:
        Compact dedup message if found, None if new or expired.
    """
    entries = _prune(_load())
    for entry in entries:
        if entry.get("address", "").lower() == address.lower():
            ts = entry.get("ts", 0)
            hours_ago = (time.time() - ts) / 3600
            score = entry.get("score", "?")
            tier = entry.get("tier", "?")
            return (
                f"🔄 Already analyzed {hours_ago:.0f}h ago — "
                f"Score: {score}/100 {tier} | {address[:6]}...{address[-4:]}"
            )
    return None


def record_address(address: str, score: int = 0, tier: str = "?") -> None:
    """Record address analysis in dedupe store.

    Args:
        address: Solana token/pair address.
        score: Meme score 0–100.
        tier: Score tier (HIGH CONVICTION/SOLID/SPECULATIVE/AVOID).
    """
    entries = _prune(_load())
    entry = {
        "address": address,
        "ts": time.time(),
        "score": score,
        "tier": tier,
    }
    # Update existing or append
    found = False
    for i, e in enumerate(entries):
        if e.get("address", "").lower() == address.lower():
            entries[i] = entry
            found = True
            break
    if not found:
        entries.append(entry)
    _save(entries)


# Backward compat — same interface used by msf_http.py
def should_skip(address: str, cooldown_minutes: int = 15) -> bool:
    """Check if address should be skipped due to cooldown.

    Complements existing loop_memory.should_skip with 24h dedupe logic.
    """
    return check_dedupe(address) is not None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: msf_dedupe.py <address> [record] [score] [tier]")
        sys.exit(1)

    addr = sys.argv[1]
    if len(sys.argv) >= 3 and sys.argv[2] == "record":
        score = int(sys.argv[3]) if len(sys.argv) >= 4 else 0
        tier = sys.argv[4] if len(sys.argv) >= 5 else "?"
        record_address(addr, score, tier)
        print(f"Recorded: {addr[:12]}... score={score} tier={tier}")
    else:
        result = check_dedupe(addr)
        if result:
            print(result)
        else:
            print(f"No duplicate for {addr[:12]}...")
