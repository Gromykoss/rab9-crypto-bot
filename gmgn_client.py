"""GMGN smart-money enrichment client for RAB9 MSF pipeline.

Queries GMGN public rank endpoints for smart-money signals.
If 403/empty → silent skip (never blocks MSF delivery).

Usage:
    from gmgn_client import get_smart_money_score
    score = get_smart_money_score("So11111111111111111111111111111111111111112")
    # Returns int 0–15 or None if unavailable
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import requests

GMGN_BASE = "https://gmgn.ai/defi/quotation/v1"
TIMEOUT = 10

logger = logging.getLogger("rab9.gmgn")


def _fetch_rank(timeframe: str = "1h", orderby: str = "smartmoney") -> list[dict[str, Any]]:
    """Fetch GMGN rank data for a timeframe/sort.

    Returns empty list on any failure (403, timeout, empty response).
    """
    try:
        r = requests.get(
            f"{GMGN_BASE}/rank/sol/swaps/{timeframe}",
            params={"orderby": orderby},
            timeout=TIMEOUT,
        )
        if r.status_code == 403:
            logger.debug("GMGN 403 forbidden (expected for some modes) — silent skip")
            return []
        if not r.ok:
            logger.debug("GMGN HTTP %s — silent skip", r.status_code)
            return []

        data: dict[str, Any] = r.json()
        # Defensive parsing of nested data structures
        rank_data = data.get("data", data)
        if isinstance(rank_data, dict):
            items = rank_data.get("rank") or rank_data.get("list") or rank_data.get("items") or []
        elif isinstance(rank_data, list):
            items = rank_data
        else:
            items = []

        return items if isinstance(items, list) else []

    except Exception as e:
        logger.debug("GMGN fetch failed: %s — silent skip", e)
        return []


def get_smart_money_score(mint: str) -> int | None:
    """Query GMGN smart-money rank for a token mint.

    Args:
        mint: Solana token mint address.

    Returns:
        Smart-money score 0–100 or None if unavailable (silent skip).
        Mirrors auto-sol: tries multiple timeframes + orderby combos,
        falls back to empty gracefully.
    """
    # Try multiple timeframes — shorter first (faster/more relevant)
    for tf in ("1h", "6h", "24h"):
        for ob in ("smartmoney", "smartmoney_count"):
            items = _fetch_rank(timeframe=tf, orderby=ob)
            if not items:
                continue

            # Search for this token in results
            for item in items:
                addr = (
                    item.get("address")
                    or item.get("token_address")
                    or item.get("mint")
                    or ""
                )
                if addr.lower() == mint.lower():
                    smart_score = item.get("smartMoneyScore") or item.get(
                        "smart_money_score"
                    )
                    if smart_score is not None:
                        return int(smart_score)
                    # If no explicit score field, count smart-money entries as signal
                    sm_count = item.get("smartMoneyCount") or item.get(
                        "smart_money_count"
                    )
                    if sm_count is not None:
                        return min(int(sm_count) * 5, 15)

    return None


def format_for_grok(score: int | None) -> str:
    """Format GMGN smart-money result for Grok context."""
    if score is None:
        return "GMGN smart-money: no data"
    level = "strong" if score >= 10 else "moderate" if score >= 5 else "weak"
    return f"GMGN smart-money: {score}/15 ({level})"


if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: gmgn_client.py <mint>"}))
        sys.exit(1)

    score = get_smart_money_score(sys.argv[1])
    result = {"ok": score is not None, "smart_money_score": score}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)
