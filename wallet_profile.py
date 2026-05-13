import time

from maker_sources import behavior_hint, get_birdeye_maker_find, summarize_maker_trades
from price_sources import get_birdeye_price_near
from swap_sources import compact, format_percent


MAX_CASES = 5
PROFILE_DELAY_SECONDS = 0.3


def parse_case(raw_case):
    if ":" not in raw_case:
        return None

    pair, token = raw_case.split(":", 1)
    pair = pair.strip()
    token = token.strip()

    if not pair or not token:
        return None

    return {"pair": pair, "token": token}


def calculate_price_movement(token, first_seen, last_seen):
    if not first_seen or not last_seen or first_seen == "n/a" or last_seen == "n/a":
        return None

    first_price = get_birdeye_price_near(token, first_seen)
    time.sleep(PROFILE_DELAY_SECONDS)
    last_price = get_birdeye_price_near(token, last_seen)

    first_value = first_price.get("price") if first_price.get("ok") else None
    last_value = last_price.get("price") if last_price.get("ok") else None

    if first_value is None or last_value is None or first_value == 0:
        return None

    return ((last_value - first_value) / first_value) * 100


def analyze_wallet_case(wallet, case):
    result = get_birdeye_maker_find(case["pair"], wallet, "deep50")
    items = result.get("items") or []
    summary = summarize_maker_trades(items)
    price_movement = calculate_price_movement(case["token"], summary["first_time"], summary["last_time"])

    return {
        "pair": case["pair"],
        "token": case["token"],
        "matched_trades": summary["total"],
        "buy_count": summary["buy_count"],
        "sell_count": summary["sell_count"],
        "unknown_count": summary["unknown_count"],
        "net_direction": summary["net_direction"],
        "first_seen": summary["first_time"],
        "last_seen": summary["last_time"],
        "price_movement": price_movement,
        "behavior": behavior_hint(summary),
        "status": result.get("status"),
    }


def classify_wallet_role(profile):
    active_cases = profile["active_cases"]

    if active_cases < 2:
        return "Weak / Needs More Data"
    if profile["two_sided_cases"] >= 2:
        return "Repeating Two-sided Active Maker"
    if profile["sell_heavy_cases"] >= 2:
        return "Repeating Distribution Wallet"
    if profile["buy_heavy_cases"] >= 2 and profile["sell_heavy_cases"] == 0:
        return "Repeating Accumulation Wallet"

    return "Mixed Active Wallet"


def summarize_profile(case_results, requested_count):
    active_cases = len([case for case in case_results if case["matched_trades"] > 0])
    buy_heavy_cases = len([case for case in case_results if case["net_direction"] == "buy-heavy"])
    sell_heavy_cases = len([case for case in case_results if case["net_direction"] == "sell-heavy"])
    two_sided_cases = len([case for case in case_results if case["buy_count"] > 0 and case["sell_count"] > 0])
    not_found_cases = len([case for case in case_results if case["matched_trades"] == 0])
    total_matched = sum(case["matched_trades"] for case in case_results)
    movements = [case["price_movement"] for case in case_results if case["price_movement"] is not None]
    avg_movement = sum(movements) / len(movements) if movements else None

    profile = {
        "requested_count": requested_count,
        "analyzed_count": len(case_results),
        "active_cases": active_cases,
        "total_matched": total_matched,
        "buy_heavy_cases": buy_heavy_cases,
        "sell_heavy_cases": sell_heavy_cases,
        "two_sided_cases": two_sided_cases,
        "not_found_cases": not_found_cases,
        "avg_movement": avg_movement,
        "negative_windows": len([movement for movement in movements if movement < 0]),
        "positive_windows": len([movement for movement in movements if movement > 0]),
    }
    profile["primary_role"] = classify_wallet_role(profile)
    return profile


def build_wallet_profile_text(wallet, raw_cases):
    parsed_cases = []
    for raw_case in raw_cases[:MAX_CASES]:
        parsed = parse_case(raw_case)
        if parsed is None:
            return f"Expected PAIR:TOKEN.\nBad case: {raw_case}"
        parsed_cases.append(parsed)

    if not parsed_cases:
        return "Expected PAIR:TOKEN."

    case_results = []
    for case in parsed_cases:
        case_results.append(analyze_wallet_case(wallet, case))
        time.sleep(PROFILE_DELAY_SECONDS)

    profile = summarize_profile(case_results, len(raw_cases))

    lines = [
        "Wallet Profile Diagnostic",
        f"Wallet: {compact(wallet)}",
        f"Cases requested: {len(raw_cases)}",
        f"Cases analyzed: {len(case_results)}",
        "Source: Birdeye pair trades + Birdeye OHLCV",
        "",
        "Case Summary:",
    ]

    for idx, case in enumerate(case_results, start=1):
        lines.extend(
            [
                f"#{idx} {compact(case['pair'])}:{compact(case['token'])}",
                f"- Matched trades: {case['matched_trades']}",
                f"- BUY / SELL / UNKNOWN: {case['buy_count']} / {case['sell_count']} / {case['unknown_count']}",
                f"- Net direction: {case['net_direction']}",
                f"- First seen: {case['first_seen']}",
                f"- Last seen: {case['last_seen']}",
                f"- Price movement during activity: {format_percent(case['price_movement'])}",
                f"- Behavior: {case['behavior']}",
            ]
        )

    lines.extend(
        [
            "",
            "Profile Summary:",
            f"- Active cases: {profile['active_cases']}",
            f"- Total matched trades: {profile['total_matched']}",
            f"- Buy-heavy cases: {profile['buy_heavy_cases']}",
            f"- Sell-heavy cases: {profile['sell_heavy_cases']}",
            f"- Two-sided cases: {profile['two_sided_cases']}",
            f"- Not found cases: {profile['not_found_cases']}",
            f"- Avg price movement during activity: {format_percent(profile['avg_movement'])}",
            f"- Negative price-window cases: {profile['negative_windows']}",
            f"- Positive price-window cases: {profile['positive_windows']}",
            "",
            "Primary Wallet Role:",
            f"- {profile['primary_role']}",
            "",
            "Evidence:",
            f"- appeared in {profile['active_cases']} of {profile['analyzed_count']} analyzed cases",
            f"- total matched trades: {profile['total_matched']}",
            f"- direction mix: buy-heavy {profile['buy_heavy_cases']} / sell-heavy {profile['sell_heavy_cases']} / two-sided {profile['two_sided_cases']}",
            f"- avg price movement during activity: {format_percent(profile['avg_movement'])}",
            f"- price-window count: negative {profile['negative_windows']} / positive {profile['positive_windows']}",
            "",
            "Notes:",
            "- No PnL calculated.",
            "- No trading advice.",
            "- Manual diagnostic only.",
        ]
    )

    if len(raw_cases) > MAX_CASES:
        lines.append("Only first 5 cases analyzed.")

    return "\n".join(lines)
