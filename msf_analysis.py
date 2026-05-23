from address_validation import is_msf_solana_address
from maker_sources import get_birdeye_pair_makers, summarize_pair_makers
from pair_sources import get_birdeye_candidates, get_dexscreener_candidates
from swap_sources import compact, format_usd


def first_valid(items, key):
    for item in items:
        value = item.get(key)
        if value and value != "n/a" and is_msf_solana_address(str(value)):
            return item
    return None


def symbol_from_label(label):
    text = str(label or "").strip()
    if not text or text == "n/a":
        return "n/a"

    return text.split("/", 1)[0].strip() or "n/a"


def find_dex_match(pair, dex_candidates):
    pair_lower = str(pair or "").lower()
    for item in dex_candidates:
        if str(item.get("pair") or "").lower() == pair_lower:
            return item
    return {}


def choose_best_pair(address):
    dex = get_dexscreener_candidates(address)
    birdeye = get_birdeye_candidates(address)
    dex_candidates = dex.get("candidates") or []
    birdeye_candidates = birdeye.get("candidates") or []

    birdeye_best = first_valid(birdeye_candidates, "market")
    if birdeye_best:
        pair = birdeye_best.get("market")
        dex_match = find_dex_match(pair, dex_candidates)
        return {
            "pair": pair,
            "candidate": {**birdeye_best, **{k: v for k, v in dex_match.items() if v not in (None, "n/a")}},
            "source": birdeye_best.get("source") or "birdeye",
            "dex_status": dex,
            "birdeye_status": birdeye,
        }

    dex_best = first_valid(dex_candidates, "pair")
    if dex_best:
        return {
            "pair": dex_best.get("pair"),
            "candidate": dex_best,
            "source": "dexscreener",
            "dex_status": dex,
            "birdeye_status": birdeye,
        }

    return {
        "pair": None,
        "candidate": {},
        "source": None,
        "dex_status": dex,
        "birdeye_status": birdeye,
    }


def behavior_counts(makers):
    return {
        "buy_heavy": len([row for row in makers if row["net_direction"] == "buy-heavy"]),
        "sell_heavy": len([row for row in makers if row["net_direction"] == "sell-heavy"]),
        "mixed": len([row for row in makers if row["net_direction"] == "mixed"]),
        "weak": len([row for row in makers if row["trades"] < 3]),
    }


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def top_maker_concentration(makers):
    total_trades = sum(row.get("trades", 0) for row in makers)
    if not makers or total_trades <= 0:
        return 0.0

    return makers[0].get("trades", 0) / total_trades


def meaning_for_state(state):
    meanings = {
        "Weak/Noisy": (
            "Activity exists on this pair, but most wallets show few trades; "
            "there is no clear accumulation or distribution pattern in this shallow scan."
        ),
        "Accumulation": "Buy-heavy makers currently dominate the scanned window.",
        "Distribution": "Sell-heavy makers currently dominate the scanned window.",
        "Mixed/Choppy": "Both sides are active without clear directional control.",
        "Needs more data": "The scan is too shallow for reliable interpretation.",
    }
    return meanings.get(state, "The first-pass scan is inconclusive.")


def build_why_bullets(raw_trades, unique_makers, buckets, weak_ratio, concentration, top_direction):
    bullets = []

    if raw_trades < 15 or unique_makers < 2:
        bullets.append(f"Normal scan is shallow: {raw_trades} raw trades, {unique_makers} maker(s)")

    if buckets["buy_heavy"] == buckets["sell_heavy"] and (buckets["buy_heavy"] or buckets["sell_heavy"]):
        bullets.append(f"Buy-heavy and sell-heavy are balanced: {buckets['buy_heavy']}/{buckets['sell_heavy']}")
    elif buckets["buy_heavy"] > buckets["sell_heavy"]:
        bullets.append(f"Buy-heavy makers lead sell-heavy: {buckets['buy_heavy']}/{buckets['sell_heavy']}")
    elif buckets["sell_heavy"] > buckets["buy_heavy"]:
        bullets.append(f"Sell-heavy makers lead buy-heavy: {buckets['sell_heavy']}/{buckets['buy_heavy']}")

    if buckets["mixed"] <= 2:
        bullets.append(f"Mixed makers are low: {buckets['mixed']}")
    else:
        bullets.append(f"Mixed makers are active: {buckets['mixed']}")

    if unique_makers == 0:
        bullets.append("No maker wallets were extracted from the normal scan")
    elif weak_ratio > 0.5:
        bullets.append(f"Weak makers dominate: {buckets['weak']}/{unique_makers}")
    else:
        bullets.append(f"Weak makers are not dominant: {buckets['weak']}/{unique_makers}")

    if concentration < 0.25:
        bullets.append(f"Top maker concentration is low: {concentration:.0%}")
    else:
        bullets.append(f"Top maker is {top_direction}; concentration {concentration:.0%}")

    return bullets


def build_analyst_verdict(candidate, maker_result, makers, buckets, pair):
    raw_trades = int(maker_result.get("raw_pair_trades_scanned") or 0)
    unique_makers = len(makers)
    weak_ratio = buckets["weak"] / unique_makers if unique_makers else 1.0
    concentration = top_maker_concentration(makers)
    top_direction = makers[0]["net_direction"] if makers else "n/a"
    liquidity = safe_float(candidate.get("liquidity"))

    if raw_trades < 15 or unique_makers < 2:
        state = "Needs more data"
    elif weak_ratio > 0.60:
        state = "Weak/Noisy"
    elif buckets["buy_heavy"] > buckets["sell_heavy"]:
        state = "Accumulation"
    elif buckets["sell_heavy"] > buckets["buy_heavy"]:
        state = "Distribution"
    elif buckets["buy_heavy"] and buckets["sell_heavy"]:
        state = "Mixed/Choppy"
    else:
        state = "Needs more data"

    risks = []
    if raw_trades < 30:
        risks.append("Normal scan covers only the latest ~50 pair trades")
    if concentration >= 0.45:
        risks.append("Concentrated maker activity")
    if liquidity is not None and liquidity < 20_000:
        risks.append("Low liquidity")
    if weak_ratio > 0.60:
        risks.append("High share of weak makers reduces signal quality")

    if makers and state not in {"Weak/Noisy", "Needs more data"}:
        next_check = f"/makertrades {pair} {makers[0]['wallet']}"
    else:
        next_check = f"/pairmakers {pair} deep"

    return {
        "state": state,
        "why": build_why_bullets(raw_trades, unique_makers, buckets, weak_ratio, concentration, top_direction),
        "meaning": meaning_for_state(state),
        "risk": risks or ["Normal first-pass scan risk"],
        "next_check": next_check,
    }


def format_top_maker(idx, row):
    return (
        f"{idx}. {compact(row['wallet'])} | "
        f"trades {row['trades']} | "
        f"B/S/U {row['buy_count']}/{row['sell_count']}/{row['unknown_count']} | "
        f"{row['net_direction']} | "
        f"value {format_usd(row['total_usd'] if row['has_usd'] else None)}"
    )


def build_unresolved_text(address, resolved):
    dex = resolved.get("dex_status") or {}
    birdeye = resolved.get("birdeye_status") or {}
    return "\n".join(
        [
            "MSF Signal Analysis",
            f"Input: {address}",
            "Resolved pair: unresolved",
            "Pairmakers: skipped",
            "",
            "Sources:",
            f"- Dexscreener token-pairs: {dex.get('token_status')}",
            f"- Dexscreener pair: {dex.get('pair_status')}",
            f"- Birdeye: {', '.join(birdeye.get('statuses') or ['n/a'])}",
            "",
            "No PnL. No trading advice.",
        ]
    )


def build_msf_signal_analysis_text(address: str):
    address = str(address or "").strip()
    resolved = choose_best_pair(address)
    pair = resolved.get("pair")

    if not pair:
        return build_unresolved_text(address, resolved)

    candidate = resolved.get("candidate") or {}
    maker_result = get_birdeye_pair_makers(pair, mode="normal")
    makers = summarize_pair_makers(maker_result.get("items") or [])
    buckets = behavior_counts(makers)
    verdict = build_analyst_verdict(candidate, maker_result, makers, buckets, pair)

    lines = [
        "MSF Signal Analysis",
        f"Token: {symbol_from_label(candidate.get('base'))}",
        f"Quote: {symbol_from_label(candidate.get('quote'))}",
        f"Input: {address}",
        f"Resolved pair: {pair}",
        f"Dex: {candidate.get('dex') or candidate.get('source') or resolved.get('source') or 'n/a'}",
        f"Liquidity: {format_usd(candidate.get('liquidity'))}",
        f"Volume24h: {format_usd(candidate.get('volume24h'))}",
        "",
        "Analyst verdict:",
        f"- State: {verdict['state']}",
        "- Why:",
        *[f"  - {item}" for item in verdict["why"]],
        f"- Meaning: {verdict['meaning']}",
        "- Risk:",
        *[f"  - {item}" for item in verdict["risk"]],
        f"- Next check: {verdict['next_check']}",
        "",
        "Pairmakers:",
        f"- Scan mode: {maker_result.get('mode')}",
        f"- Raw trades scanned: {maker_result.get('raw_pair_trades_scanned', 0)}",
        f"- Unique makers: {len(makers)}",
        f"- Status: {maker_result.get('status')}",
        "",
        "Behavior buckets:",
        f"- Buy-heavy: {buckets['buy_heavy']}",
        f"- Sell-heavy: {buckets['sell_heavy']}",
        f"- Mixed: {buckets['mixed']}",
        f"- Weak (<3 trades): {buckets['weak']}",
        "",
        "Top makers:",
    ]

    if makers:
        lines.extend(format_top_maker(idx, row) for idx, row in enumerate(makers[:5], start=1))
    else:
        lines.append("- none extracted")
        keys = maker_result.get("maker_like_keys_seen") or []
        if keys:
            lines.append(f"- Maker-like keys seen: {', '.join(keys[:6])}")

    lines.extend(["", "No PnL. No trading advice."])
    return "\n".join(lines)
