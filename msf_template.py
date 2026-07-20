"""Template fallback for MSF signals when LLMs (Grok + DeepSeek) both fail.

Generates a deterministic, structured Telegram card from DexScreener data,
meme_score, and RugCheck — no LLM call needed. Guarantees delivery during
API outages.

Usage:
    from msf_template import build_template_card
    card = build_template_card(
        token_name="BURNIE",
        address="So111...",
        score={"score": 80, "tier": "SOLID"},
        liq=50000, vol=200000, mc=5000000,
        rugcheck={"level": "low"},
    )
"""

from __future__ import annotations

from typing import Any


def _fmt_usd(value: float | None) -> str:
    """Format USD value compactly."""
    if value is None:
        return "?"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    if value >= 1_000:
        return f"${value / 1_000:.0f}K"
    return f"${value:.0f}"


def build_template_card(
    token_name: str,
    address: str,
    score: dict[str, Any] | None = None,
    liq: float | None = None,
    vol: float | None = None,
    mc: float | None = None,
    rugcheck: dict[str, Any] | None = None,
    buy_ratio: float | None = None,
    sources: list[str] | None = None,
) -> str:
    """Build a compact Telegram card from structured data only.

    No LLM call — pure data formatting. Used when Grok and DeepSeek
    both fail to respond.

    Args:
        token_name: Token symbol.
        address: Solana token address.
        score: Meme score dict from meme_score.compute_score().
        liq: Liquidity in USD.
        vol: 24h volume in USD.
        mc: Market cap in USD.
        rugcheck: RugCheck report dict.
        buy_ratio: Buy/sell ratio.
        sources: List of enrichment source tags.

    Returns:
        Multi-line Telegram-formatted text.
    """
    score_val = score.get("score", "?") if score else "?"
    score_max = score.get("max", 100) if score else 100
    tier = score.get("tier", "?") if score else "?"

    rug_level = rugcheck.get("level", "?") if rugcheck else "?"
    rug_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "unknown": "⚪"}.get(
        rug_level, "⚪"
    )

    lines = [
        f"🔍 {token_name} | MC: {_fmt_usd(mc)}",
        "",
        f"📊 Score: {score_val}/{score_max} → {tier}",
        f"   Liq: {_fmt_usd(liq)} | Vol 24h: {_fmt_usd(vol)}",
        f"   RugCheck: {rug_emoji} {rug_level}",
    ]

    if buy_ratio is not None:
        bs_str = f"{buy_ratio:.1f}x buy" if buy_ratio >= 1 else f"{1/buy_ratio:.1f}x sell"
        lines.append(f"   B/S: {bs_str}")

    lines.append("")
    lines.append("⚠️ AI analysis unavailable — template fallback.")
    lines.append("Проверь вручную: ликвидность, холдеры, X-комьюнити.")
    lines.append("")

    if sources:
        lines.append(f"📎 sources: {', '.join(sources)}")
    else:
        lines.append("📎 sources: msf-template")

    lines.append(f"🔗 https://dexscreener.com/solana/{address}")

    return "\n".join(lines)


if __name__ == "__main__":
    # Self-test
    card = build_template_card(
        token_name="TEST",
        address="So11111111111111111111111111111111111111112",
        score={"score": 72, "max": 100, "tier": "SOLID"},
        liq=50000,
        vol=200000,
        mc=5000000,
        rugcheck={"level": "low"},
        buy_ratio=2.1,
        sources=["msf-telegram", "dexscreener", "rugcheck"],
    )
    print(card)
