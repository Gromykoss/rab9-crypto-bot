"""Meme coin scoring framework for RAB9.

6-pillar scoring (100 pts) adapted from proven meme coin analysis methodologies.
Uses available data: Birdeye on-chain, DexScreener market, X-radar social.

Usage: python3 meme_score.py <token_address>
"""
import json
import sys
import os
import requests

TIMEOUT = 10


def _read_birdeye_key():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "BIRDEYE_API_KEY" in line:
                    return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def fetch_onchain(address: str) -> dict:
    """Birdeye token_security."""
    key = _read_birdeye_key()
    if not key:
        return {}
    try:
        r = requests.get(
            "https://public-api.birdeye.so/defi/token_security",
            params={"address": address},
            headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
            timeout=TIMEOUT,
        )
        return r.json().get("data", {}) if r.ok else {}
    except Exception:
        return {}


def fetch_market(address: str) -> dict:
    """DexScreener pair data."""
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/pairs/solana/{address}",
            timeout=TIMEOUT,
        )
        if r.ok:
            data = r.json()
            pairs = data.get("pairs", [data] if isinstance(data, dict) else [])
            return pairs[0] if pairs else {}
    except Exception:
        pass
    return {}


def score_security(onchain: dict) -> tuple[int, list[str]]:
    """Pillar 1: Security & On-chain hygiene (20 pts)."""
    score = 20
    notes = []

    if onchain.get("freezeAuthority"):
        score -= 10
        notes.append("⚠️ freeze authority active")
    else:
        notes.append("✓ freeze revoked")

    if onchain.get("mutableMetadata"):
        score -= 8
        notes.append("⚠️ mutable metadata")
    else:
        notes.append("✓ metadata immutable")

    creator_pct = float(onchain.get("creatorPercentage", 0) or 0)
    if creator_pct > 5:
        score -= 8
        notes.append(f"⚠️ creator holds {creator_pct*100:.0f}%")
    elif creator_pct > 0:
        notes.append(f"✓ creator {creator_pct*100:.1f}%")

    top10_pct = float(onchain.get("top10HolderPercent", 0) or 0)
    if top10_pct < 1:  # Value is decimal (0.1927 = 19.27%)
        top10_pct *= 100
    if top10_pct > 50:
        score -= 8
        notes.append(f"⚠️ top10={top10_pct:.0f}% concentrated")
    elif top10_pct > 30:
        score -= 4
        notes.append(f"⚠️ top10={top10_pct:.0f}% moderate")
    else:
        notes.append(f"✓ top10={top10_pct:.0f}% distributed")

    lock = onchain.get("lockInfo")
    if not lock:
        # PumpSwap tokens rarely have locked LP — not a major red flag for memes
        notes.append("· LP not locked (standard for PumpSwap)")
    else:
        notes.append("✓ LP locked")

    if not onchain.get("jupStrictList"):
        score -= 3

    return max(0, score), notes


def score_market(market: dict, chart: dict | None) -> tuple[int, list[str]]:
    """Pillar 2: Market Metrics (20 pts)."""
    score = 20
    notes = []

    mc = market.get("marketCap", 0) or 0
    liq = (market.get("liquidity", {}) or {}).get("usd", 0) or 0
    vol24 = (market.get("volume", {}) or {}).get("h24", 0) or 0

    if mc > 0:
        if mc >= 5_000_000:
            notes.append(f"MC=${mc/1e6:.1f}M — large cap")
        elif mc >= 1_000_000:
            notes.append(f"MC=${mc/1e6:.1f}M — mid cap")
            score -= 2
        elif mc >= 100_000:
            notes.append(f"MC=${mc/1e3:.0f}K — micro cap")
            score -= 5
        else:
            notes.append(f"MC=${mc:.0f} — nano cap")
            score -= 8

    # Liquidity/MC ratio
    if mc > 0 and liq > 0:
        ratio = liq / mc
        if ratio < 0.05:
            score -= 5
            notes.append(f"⚠️ Liq/MC={ratio:.1%} — thin")
        elif ratio < 0.1:
            score -= 2
            notes.append(f"Liq/MC={ratio:.1%}")
        else:
            notes.append(f"✓ Liq/MC={ratio:.1%}")

    # Volume
    if vol24 > 0 and mc > 0:
        vol_ratio = vol24 / mc
        if vol_ratio > 0.5:
            notes.append(f"✓ Vol/MC={vol_ratio:.1f}x — healthy")
        elif vol_ratio < 0.1:
            score -= 3
            notes.append(f"⚠️ Vol/MC={vol_ratio:.1f}x — low")
        else:
            notes.append(f"Vol/MC={vol_ratio:.1f}x")

    # RSI
    if chart and chart.get("ok"):
        rsi = chart.get("rsi")
        if rsi:
            if rsi > 70:
                notes.append(f"RSI={rsi} — overbought")
                score -= 3
            elif rsi < 30:
                notes.append(f"RSI={rsi} — oversold")
            else:
                notes.append(f"RSI={rsi} — neutral")

    # Price trend
    if chart and chart.get("ok"):
        ch = chart.get("changes", {})
        ch24 = ch.get("24h", 0)
        if ch24 < -20:
            score -= 4
            notes.append(f"⚠️ 24h={ch24:+.0f}% dump")
        elif ch24 < -5:
            notes.append(f"24h={ch24:+.0f}%")
        elif ch24 > 20:
            notes.append(f"24h={ch24:+.0f}% pump")
            score -= 2  # FOMO risk

    return max(0, score), notes


def score_holders(onchain: dict) -> tuple[int, list[str]]:
    """Pillar 3: Holder Distribution (15 pts)."""
    score = 15
    notes = []

    top10 = float(onchain.get("top10HolderPercent", 0) or 0)
    creator = float(onchain.get("creatorPercentage", 0) or 0)

    if top10 > 0:
        top10_pct = top10 * 100
        if top10_pct > 40:
            score -= 8
            notes.append(f"⚠️ top10={top10_pct:.0f}% — whale zone")
        elif top10_pct > 25:
            score -= 4
            notes.append(f"top10={top10_pct:.0f}% — moderate")
        elif top10_pct > 10:
            notes.append(f"✓ top10={top10_pct:.0f}% — good")
        else:
            notes.append(f"✓ top10={top10_pct:.0f}% — excellent")

    if creator > 0:
        if creator > 0.10:
            score -= 5
            notes.append(f"⚠️ creator={creator*100:.0f}% — large bag")
        elif creator < 0.02:
            notes.append(f"✓ creator={creator*100:.1f}% — minimal")

    return max(0, score), notes


def score_community(market: dict) -> tuple[int, list[str]]:
    """Pillar 4: Community & Social (25 pts)."""
    score = 15  # Base — can go up or down
    notes = []

    info = market.get("info", {}) or {}
    socials = info.get("socials", []) or []

    has_twitter = any(s.get("type") == "twitter" for s in socials)
    has_telegram = any(s.get("type") == "telegram" for s in socials)
    has_website = bool(info.get("websites"))

    if has_twitter:
        score += 3
        notes.append("✓ X account")
    else:
        notes.append("✗ no X — red flag")

    if has_telegram:
        score += 2
        notes.append("✓ Telegram")
    if has_website:
        score += 1
        notes.append("✓ website")

    # TXN activity as proxy for community
    txns = market.get("txns", {}) or {}
    h24 = txns.get("h24", {}) or {}
    total_txns = (h24.get("buys", 0) or 0) + (h24.get("sells", 0) or 0)
    if total_txns > 5000:
        score += 3
        notes.append(f"✓ {total_txns} txns/24h — active")
    elif total_txns > 1000:
        score += 2
        notes.append(f"{total_txns} txns/24h")
    elif total_txns < 100:
        score -= 3
        notes.append(f"⚠️ only {total_txns} txns/24h — dead")

    # Note: real X engagement score requires live X API
    # Placeholder until X-radar is live

    return max(0, min(25, score)), notes


def score_narrative(token_name: str, market: dict) -> tuple[int, list[str]]:
    """Pillar 5: Meme/Narrative Potency (10 pts)."""
    # Auto-assessment based on available signals
    score = 5  # Base — neutral
    notes = []

    mc = market.get("marketCap", 0) or 0

    # High MC suggests narrative has traction
    if mc > 5_000_000:
        score += 3
        notes.append("proven narrative (MC>5M)")
    elif mc > 1_000_000:
        score += 2
        notes.append("traction (MC>1M)")

    # Token age
    created = market.get("pairCreatedAt", 0) or 0
    if created:
        import time
        age_days = (time.time() * 1000 - created) / (86400 * 1000)
        if age_days > 30:
            score += 2
            notes.append(f"survived {age_days:.0f}d — resilience")
        elif age_days > 3:
            notes.append(f"age={age_days:.0f}d")
        else:
            score -= 2
            notes.append(f"⚠️ {age_days*24:.0f}h old — fresh risk")

    # Note: narrative quality assessment needs Grok
    # Placeholder for manual/Grok narrative score

    return max(0, min(10, score)), notes


def score_influencers() -> tuple[int, list[str]]:
    """Pillar 6: Influencer Backing (10 pts)."""
    # Will be overridden if radar data available
    return 5, ["⚠️ influencer check not yet run — run radar_x first"]


def compute_score(address: str, chart_data: dict | None = None) -> dict:
    """Main scoring function. Returns structured score."""
    onchain = fetch_onchain(address)
    market = fetch_market(address)

    if not onchain and not market:
        return {"ok": False, "error": "No data for address", "score": 0, "max": 100}

    pillars = {}
    total = 0
    max_total = 0

    s, n = score_security(onchain)
    pillars["security"] = {"score": s, "max": 20, "notes": n}
    total += s
    max_total += 20

    s, n = score_market(market, chart_data)
    pillars["market"] = {"score": s, "max": 20, "notes": n}
    total += s
    max_total += 20

    s, n = score_holders(onchain)
    pillars["holders"] = {"score": s, "max": 15, "notes": n}
    total += s
    max_total += 15

    s, n = score_community(market)
    pillars["community"] = {"score": s, "max": 25, "notes": n}
    total += s
    max_total += 25

    token_name = (market.get("baseToken") or {}).get("symbol", "?")
    s, n = score_narrative(token_name, market)
    pillars["narrative"] = {"score": s, "max": 10, "notes": n}
    total += s
    max_total += 10

    s, n = score_influencers()
    pillars["influencers"] = {"score": s, "max": 10, "notes": n}
    total += s
    max_total += 10

    # Tier
    if total >= 85:
        tier = "HIGH CONVICTION"
    elif total >= 70:
        tier = "SOLID"
    elif total >= 50:
        tier = "SPECULATIVE"
    else:
        tier = "AVOID"

    return {
        "ok": True,
        "score": total,
        "max": max_total,
        "tier": tier,
        "pillars": pillars,
        "token": token_name,
    }


def format_for_grok(result: dict) -> str:
    if not result.get("ok"):
        return "Score: нет данных."

    lines = [
        f"Meme Score: {result['score']}/{result['max']} → {result['tier']}",
        "",
    ]
    for name, p in result["pillars"].items():
        lines.append(f"  {name}: {p['score']}/{p['max']}")
        for n in p["notes"][:3]:
            lines.append(f"    {n}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: meme_score.py <address>"}))
        sys.exit(1)

    result = compute_score(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
