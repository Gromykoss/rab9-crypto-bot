"""RugCheck.xyz API client for RAB9 MSF signal pipeline.

Free public API: https://api.rugcheck.xyz/v1
Provides token risk reports to gate AI analysis and enrich Grok context.

Usage:
    from rugcheck_client import check_token
    report = check_token("So11111111111111111111111111111111111111112")
    # report["level"] in ("low", "medium", "high", "unknown")
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import requests

RUGCHECK_BASE = "https://api.rugcheck.xyz/v1"
TIMEOUT = 10

logger = logging.getLogger("rab9.rugcheck")


def check_token(mint: str) -> dict[str, Any]:
    """Fetch RugCheck token report summary and compute risk level.

    Args:
        mint: Solana token mint address.

    Returns:
        Dict with keys: ok, level, score, rugged, risks, warnings,
        mint_authority, freeze_authority, top_holder_pct, raw.
        On failure returns ok=False with error string.
    """
    try:
        r = requests.get(
            f"{RUGCHECK_BASE}/tokens/{mint}/report/summary",
            timeout=TIMEOUT,
        )
        if not r.ok:
            return {"ok": False, "error": f"HTTP {r.status_code}", "level": "unknown"}

        data: dict[str, Any] = r.json()

        score: int = data.get("score", 0) or 0
        rugged: bool = bool(data.get("rugged", False))

        # Extract risks/warnings from top-level and nested fields
        risks: list[str] = data.get("risks", []) or []
        warnings: list[str] = []

        # Token metadata authority
        token_meta = data.get("tokenMeta", {}) or {}
        mint_auth = token_meta.get("mintAuthority")
        freeze_auth = token_meta.get("freezeAuthority")

        # Top holders
        top_holders_raw = data.get("topHolders", []) or []
        total_supply = float(data.get("totalSupply", 1) or 1)
        top_holder_pct: float = 0.0
        if top_holders_raw and total_supply > 0:
            top_holder_pct = float(top_holders_raw[0].get("amount", 0)) / total_supply * 100

        # Collect warnings from risk list + authority fields
        all_warnings: list[str] = list(risks)
        if mint_auth:
            all_warnings.append(f"mint_authority: {mint_auth}")
        if freeze_auth:
            all_warnings.append(f"freeze_authority: {freeze_auth}")

        # ── Determine risk level (mirrors auto-sol logic) ──
        if rugged:
            level = "high"
        elif any(
            kw in str(w).lower()
            for kw in ("mint", "freeze")
            for w in all_warnings
        ):
            level = "high"
        elif score >= 700:
            level = "high"
        elif score >= 350:
            level = "medium"
        else:
            level = "low"

        return {
            "ok": True,
            "level": level,
            "score": score,
            "rugged": rugged,
            "risks": risks,
            "warnings": all_warnings,
            "mint_authority": mint_auth,
            "freeze_authority": freeze_auth,
            "top_holder_pct": round(top_holder_pct, 1),
        }

    except Exception as e:
        logger.warning("RugCheck failed for %s: %s", mint[:12], e)
        return {"ok": False, "error": str(e)[:200], "level": "unknown"}


def format_for_grok(report: dict[str, Any]) -> str:
    """Format RugCheck report as a compact string for Grok context."""
    if not report.get("ok"):
        return "RugCheck: unavailable"

    lines = [
        f"RugCheck: level={report['level']} score={report.get('score', '?')}/1000",
    ]
    if report.get("rugged"):
        lines.append("  ⛔ RUGGED")
    if report.get("mint_authority"):
        lines.append(f"  ⚠️ mint authority: {report['mint_authority']}")
    if report.get("freeze_authority"):
        lines.append(f"  ⚠️ freeze authority: {report['freeze_authority']}")
    if report.get("top_holder_pct"):
        lines.append(f"  top holder: {report['top_holder_pct']:.1f}%")
    for w in report.get("warnings", [])[:3]:
        lines.append(f"  ⚠️ {w}")

    return "\n".join(lines)


if __name__ == "__main__":
    import json

    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: rugcheck_client.py <mint>"}))
        sys.exit(1)

    result = check_token(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
