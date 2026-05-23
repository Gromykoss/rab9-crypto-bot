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
