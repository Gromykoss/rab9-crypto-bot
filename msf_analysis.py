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


def format_market_cap_fdv(candidate):
    market_cap = candidate.get("marketCap")
    if market_cap not in (None, "n/a"):
        return format_usd(market_cap)

    fdv = candidate.get("fdv")
    if fdv not in (None, "n/a"):
        return format_usd(fdv)

    return "n/a"


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


def meaning_for_state(state, mode="normal"):
    weak_noisy_meaning = (
        "Activity exists on this pair, but wallet behavior remained noisy even after deeper scan; "
        "no clear accumulation or distribution structure emerged."
        if mode == "deep"
        else (
            "Activity exists on this pair, but most wallets show few trades; "
            "there is no clear accumulation or distribution pattern in this shallow scan."
        )
    )
    meanings = {
        "Weak/Noisy": weak_noisy_meaning,
        "Accumulation": "Buy-heavy makers currently dominate the scanned window.",
        "Distribution": "Sell-heavy makers currently dominate the scanned window.",
        "Mixed/Choppy": "Both sides are active without clear directional control.",
        "Mixed/Unstable": "The deeper scan changed the first-pass direction, so the pair needs broader review.",
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


def filter_msf_dust(items):
    kept = []
    dust_ignored = 0
    usd_unknown_kept = 0

    for item in items:
        usd_value = safe_float(item.get("usd_value"))
        if usd_value is None:
            usd_unknown_kept += 1
            kept.append(item)
            continue
        if usd_value < 10:
            dust_ignored += 1
            continue
        kept.append(item)

    return kept, {
        "meaningful_trades_used": len(kept),
        "dust_ignored": dust_ignored,
        "usd_unknown_kept": usd_unknown_kept,
    }


def weak_ratio_for(buckets, unique_makers):
    return buckets["weak"] / unique_makers if unique_makers else 1.0


def build_analyst_verdict(candidate, maker_result, makers, buckets, pair, mode="normal"):
    raw_trades = int(maker_result.get("raw_pair_trades_scanned") or 0)
    unique_makers = len(makers)
    weak_ratio = weak_ratio_for(buckets, unique_makers)
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
        "meaning": meaning_for_state(state, mode),
        "risk": risks or ["Normal first-pass scan risk"],
        "next_check": next_check,
    }


def run_spiral_scan(pair, mode, candidate):
    maker_result = get_birdeye_pair_makers(pair, mode=mode)
    filtered_items, dust = filter_msf_dust(maker_result.get("items") or [])
    makers = summarize_pair_makers(filtered_items)
    buckets = behavior_counts(makers)
    verdict = build_analyst_verdict(candidate, maker_result, makers, buckets, pair, mode)

    unique_makers = len(makers)
    weak_ratio = weak_ratio_for(buckets, unique_makers)
    return {
        "mode": mode,
        "pair": pair,
        "maker_result": maker_result,
        "makers": makers,
        "buckets": buckets,
        "verdict": verdict,
        "weak_ratio": weak_ratio,
        **dust,
    }


def scan_failed(scan):
    result = scan.get("maker_result") or {}
    status = result.get("status")
    return result.get("rate_limited") or status == 429 or (result.get("error") and not result.get("items"))


def should_deepen(scan):
    state = scan["verdict"]["state"]
    if scan_failed(scan):
        return False
    return state in {"Weak/Noisy", "Mixed/Choppy", "Needs more data"}


def top_wallets(scan, limit=5):
    return {row["wallet"] for row in (scan.get("makers") or [])[:limit]}


def strong_flip(normal_scan, deep_scan):
    normal_state = normal_scan["verdict"]["state"]
    deep_state = deep_scan["verdict"]["state"]
    directional = {"Accumulation", "Distribution"}
    return normal_state in directional and deep_state in directional and normal_state != deep_state


def apply_spiral_stability(scans):
    final = scans[-1]
    if len(scans) >= 2 and scan_failed(final):
        return scans[-2]
    if len(scans) < 2:
        return final

    normal_scan = scans[0]
    deep_scan = scans[-1]
    overlap = len(top_wallets(normal_scan) & top_wallets(deep_scan))
    weak_improvement = normal_scan["weak_ratio"] - deep_scan["weak_ratio"]

    final["stability"] = {
        "state_persisted": normal_scan["verdict"]["state"] == deep_scan["verdict"]["state"],
        "weak_improvement": weak_improvement,
        "top_overlap": overlap,
    }

    if strong_flip(normal_scan, deep_scan):
        final["verdict"] = {
            **deep_scan["verdict"],
            "state": "Mixed/Unstable",
            "meaning": meaning_for_state("Mixed/Unstable"),
            "why": [
                f"Normal scan was {normal_scan['verdict']['state']}, deep scan was {deep_scan['verdict']['state']}",
                f"Top maker overlap between normal and deep: {overlap}",
                f"Weak maker ratio changed by {weak_improvement:.0%}",
            ],
            "risk": deep_scan["verdict"]["risk"] + ["State changed strongly between scan depths"],
            "next_check": f"/pairmakers {deep_scan['pair']} deep",
        }

    return final


def run_spiral(pair, candidate):
    scans = [run_spiral_scan(pair, "normal", candidate)]
    if should_deepen(scans[0]):
        scans.append(run_spiral_scan(pair, "deep", candidate))
    return scans, apply_spiral_stability(scans)


def format_spiral_trace(scans, final_scan):
    lines = ["Spiral:"]
    for scan in scans:
        lines.append(f"- {scan['mode']} -> {scan['verdict']['state']} | weak {scan['weak_ratio']:.0%}")
        if scan_failed(scan):
            lines.append("- stop -> rate limit/API failure")
            break
    lines.append(f"- final -> {final_scan['verdict']['state']}")
    return lines


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
    scans, final_scan = run_spiral(pair, candidate)
    maker_result = final_scan["maker_result"]
    makers = final_scan["makers"]
    buckets = final_scan["buckets"]
    verdict = final_scan["verdict"]

    lines = [
        "MSF Signal Analysis",
        f"Token: {symbol_from_label(candidate.get('base'))}",
        f"Quote: {symbol_from_label(candidate.get('quote'))}",
        f"Market Cap / FDV: {format_market_cap_fdv(candidate)}",
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
        *format_spiral_trace(scans, final_scan),
        "",
        "Pairmakers:",
        f"- Scan mode: {maker_result.get('mode')}",
        f"- Raw trades scanned: {maker_result.get('raw_pair_trades_scanned', 0)}",
        f"- Meaningful trades used: {final_scan['meaningful_trades_used']}",
        f"- Dust ignored: {final_scan['dust_ignored']}",
        f"- USD unknown kept: {final_scan['usd_unknown_kept']}",
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
