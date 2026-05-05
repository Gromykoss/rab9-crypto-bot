from config import SCAN_MICRO, SCAN_DEGEN, SCAN_NORMAL, SCAN_HOT
from dex import get_dex_latest_profiles, get_dex_token_pairs, pick_best_pair
from scoring import analyze_pair_metrics
from watchlist import watch_key
from utils import format_usd, format_ratio, format_percent, safe_float


def passes_scan_filters(metrics: dict, params: dict) -> tuple[bool, list[str]]:
    reasons = []

    mc = metrics.get("marketCap") or 0
    liq = metrics.get("liquidityUsd") or 0
    vol = metrics.get("volume24h") or 0
    sell_buy = metrics.get("sellBuyRatio24h")
    score = metrics.get("score") or 0
    age = metrics.get("pairAgeHours")

    if mc < params["min_mc"] or mc > params["max_mc"]:
        reasons.append("MC вне диапазона")

    if liq < params["min_liquidity"]:
        reasons.append("liquidity ниже фильтра")

    if vol < params["min_volume24h"]:
        reasons.append("volume24h ниже фильтра")

    if sell_buy is not None and sell_buy > params["max_sell_buy_24h"]:
        reasons.append("sell/buy 24h слишком высокий")

    if score < params["min_score"]:
        reasons.append("score ниже фильтра")

    if params.get("max_age_hours") is not None and age is not None and age > params["max_age_hours"]:
        reasons.append("пара старше фильтра")

    return len(reasons) == 0, reasons


def candidate_line(item: dict, idx: int) -> str:
    pair = item["pair"]
    metrics = item["metrics"]
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}

    flags = metrics.get("flags") or []
    flags_short = "; ".join(flags[:2]) if flags else "без явных flags"

    age = metrics.get("pairAgeHours")
    age_text = f"{age:.1f}h" if age is not None else "n/a"

    address = base.get("address", "n/a")
    short_address = address[:6] + "..." + address[-6:] if len(address) > 14 else address

    return (
        f"#{idx} {base.get('symbol', 'N/A')} / {quote.get('symbol', '?')}\n"
        f"CA: {short_address}\n"
        f"Chain: {pair.get('chainId')} | DEX: {pair.get('dexId')}\n"
        f"MC: {format_usd(metrics.get('marketCap'))} | Liq: {format_usd(metrics.get('liquidityUsd'))} | Vol24h: {format_usd(metrics.get('volume24h'))}\n"
        f"Score: {metrics.get('score')}/100 | Signal: {metrics.get('rating')} | Risk: {metrics.get('risk')}\n"
        f"Sell/Buy24h: {format_ratio(metrics.get('sellBuyRatio24h'))} | Age: {age_text}\n"
        f"Flags: {flags_short}\n"
        f"Analyze: /token {pair.get('chainId')} {address}\n"
        f"Watch: /watch {pair.get('chainId')} {address} scan candidate\n"
        f"{pair.get('url')}"
    )


def build_scan_text(params: dict) -> str:
    latest = get_dex_latest_profiles()

    if not latest["ok"]:
        return f"Ошибка Dexscreener latest profiles: {latest['status_code']}\n{latest['text'][:500]}"

    profiles = latest["data"]

    if not isinstance(profiles, list) or not profiles:
        return "Dexscreener latest profiles вернул пустой список."

    profiles = profiles[: params["limit_profiles"]]

    passed = []
    rejected = 0
    checked = 0
    seen_addresses = set()

    for profile in profiles:
        chain_id = profile.get("chainId")
        token_address = profile.get("tokenAddress")

        if not chain_id or not token_address:
            rejected += 1
            continue

        exact_key = watch_key(chain_id, token_address)

        if exact_key in seen_addresses:
            rejected += 1
            continue

        seen_addresses.add(exact_key)

        result = get_dex_token_pairs(chain_id, token_address)

        if not result["ok"]:
            rejected += 1
            continue

        pairs = result["data"]
        best_pair = pick_best_pair(pairs)

        if not best_pair:
            rejected += 1
            continue

        checked += 1
        metrics = analyze_pair_metrics(best_pair)
        ok, _ = passes_scan_filters(metrics, params)

        if ok:
            passed.append(
                {
                    "profile": profile,
                    "pair": best_pair,
                    "metrics": metrics,
                }
            )
        else:
            rejected += 1

    passed = sorted(
        passed,
        key=lambda x: (
            x["metrics"].get("score") or 0,
            x["metrics"].get("volume24h") or 0,
            x["metrics"].get("liquidityUsd") or 0,
        ),
        reverse=True,
    )

    header = (
        f"🔍 RAB9 Scan {params['name']}\n\n"
        f"Filters:\n"
        f"MC: {format_usd(params['min_mc'])}–{format_usd(params['max_mc'])}\n"
        f"Min Liquidity: {format_usd(params['min_liquidity'])}\n"
        f"Min Volume24h: {format_usd(params['min_volume24h'])}\n"
        f"Max Sell/Buy24h: {params['max_sell_buy_24h']}x\n"
        f"Min Score: {params['min_score']}\n"
    )

    if params.get("max_age_hours"):
        header += f"Max Age: {params['max_age_hours']}h\n"

    header += f"\nChecked pairs: {checked}\nPassed: {len(passed)}\nRejected/no data: {rejected}\n\n"

    if not passed:
        return header + "Ничего не прошло фильтр. Это нормально: лучше пустой радар, чем мусор в watchlist."

    body = "\n\n".join(candidate_line(item, idx) for idx, item in enumerate(passed[:5], start=1))
    return header + body


def build_micro_scan_text() -> str:
    return build_scan_text(SCAN_MICRO)


def build_degen_scan_text() -> str:
    return build_scan_text(SCAN_DEGEN)


def build_normal_scan_text() -> str:
    return build_scan_text(SCAN_NORMAL)


def passes_hot_filters(pair: dict, metrics: dict, params: dict) -> tuple[bool, list[str]]:
    reasons = []

    volume = pair.get("volume") or {}
    price_change = pair.get("priceChange") or {}

    mc = metrics.get("marketCap") or 0
    liq = metrics.get("liquidityUsd") or 0
    vol1h = safe_float(volume.get("h1"))
    price1h = safe_float(price_change.get("h1"), None)
    sell_buy_1h = metrics.get("sellBuyRatio1h")
    score = metrics.get("score") or 0

    if mc < params["min_mc"] or mc > params["max_mc"]:
        reasons.append("MC вне hot-диапазона")

    if liq < params["min_liquidity"]:
        reasons.append("liquidity ниже hot-фильтра")

    if vol1h < params["min_volume1h"]:
        reasons.append("volume1h ниже hot-фильтра")

    if price1h is None or price1h < params["min_price_change_1h"]:
        reasons.append("price1h ниже hot-фильтра")

    if sell_buy_1h is not None and sell_buy_1h > params["max_sell_buy_1h"]:
        reasons.append("sell/buy 1h слишком высокий")

    if score < params["min_score"]:
        reasons.append("score ниже hot-фильтра")

    return len(reasons) == 0, reasons


def hot_candidate_line(item: dict, idx: int) -> str:
    pair = item["pair"]
    metrics = item["metrics"]

    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}
    volume = pair.get("volume") or {}
    price_change = pair.get("priceChange") or {}

    address = base.get("address", "n/a")
    short_address = address[:6] + "..." + address[-6:] if len(address) > 14 else address

    age = metrics.get("pairAgeHours")
    age_text = f"{age:.1f}h" if age is not None else "n/a"

    hot_reasons = []

    price1h = safe_float(price_change.get("h1"), None)
    vol1h = safe_float(volume.get("h1"), None)

    if price1h is not None and price1h >= 10:
        hot_reasons.append(f"Price1h +{price1h:.2f}%")

    if vol1h is not None and vol1h >= 5_000:
        hot_reasons.append(f"Vol1h {format_usd(vol1h)}")

    if metrics.get("sellBuyRatio1h") is not None and metrics.get("sellBuyRatio1h") < 1.0:
        hot_reasons.append("1h buys > sells")

    if metrics.get("liquidityToMc") is not None and metrics.get("liquidityToMc") >= 0.05:
        hot_reasons.append("healthy liquidity/MC")

    reason_text = "; ".join(hot_reasons) if hot_reasons else "hot filters passed"

    return (
        f"#{idx} 🔥 {base.get('symbol', 'N/A')} / {quote.get('symbol', '?')}\n"
        f"CA: {short_address}\n"
        f"Chain: {pair.get('chainId')} | DEX: {pair.get('dexId')}\n"
        f"MC: {format_usd(metrics.get('marketCap'))} | Liq: {format_usd(metrics.get('liquidityUsd'))}\n"
        f"Vol1h: {format_usd(volume.get('h1'))} | Vol24h: {format_usd(metrics.get('volume24h'))}\n"
        f"Price1h: {format_percent(price_change.get('h1'))} | Price24h: {format_percent(price_change.get('h24'))}\n"
        f"Sell/Buy1h: {format_ratio(metrics.get('sellBuyRatio1h'))} | Sell/Buy24h: {format_ratio(metrics.get('sellBuyRatio24h'))}\n"
        f"Score: {metrics.get('score')}/100 | Signal: {metrics.get('rating')} | Risk: {metrics.get('risk')}\n"
        f"Age: {age_text}\n"
        f"Hot Reason: {reason_text}\n"
        f"Analyze: /token {pair.get('chainId')} {address}\n"
        f"Watch: /watch {pair.get('chainId')} {address} hot candidate\n"
        f"{pair.get('url')}"
    )


def build_hot_scan_text() -> str:
    latest = get_dex_latest_profiles()

    if not latest["ok"]:
        return f"Ошибка Dexscreener latest profiles: {latest['status_code']}\n{latest['text'][:500]}"

    profiles = latest["data"]

    if not isinstance(profiles, list) or not profiles:
        return "Dexscreener latest profiles вернул пустой список."

    profiles = profiles[:SCAN_HOT["limit_profiles"]]

    passed = []
    rejected = 0
    checked = 0
    seen_addresses = set()

    for profile in profiles:
        chain_id = profile.get("chainId")
        token_address = profile.get("tokenAddress")

        if not chain_id or not token_address:
            rejected += 1
            continue

        exact_key = watch_key(chain_id, token_address)

        if exact_key in seen_addresses:
            rejected += 1
            continue

        seen_addresses.add(exact_key)

        result = get_dex_token_pairs(chain_id, token_address)

        if not result["ok"]:
            rejected += 1
            continue

        pairs = result["data"]
        best_pair = pick_best_pair(pairs)

        if not best_pair:
            rejected += 1
            continue

        checked += 1
        metrics = analyze_pair_metrics(best_pair)
        ok, _ = passes_hot_filters(best_pair, metrics, SCAN_HOT)

        if ok:
            passed.append(
                {
                    "profile": profile,
                    "pair": best_pair,
                    "metrics": metrics,
                }
            )
        else:
            rejected += 1

    passed = sorted(
        passed,
        key=lambda x: (
            safe_float((x["pair"].get("priceChange") or {}).get("h1")),
            safe_float((x["pair"].get("volume") or {}).get("h1")),
            x["metrics"].get("score") or 0,
        ),
        reverse=True,
    )

    header = (
        "🔥 RAB9 Hot Scan\n\n"
        "Filters:\n"
        f"MC: {format_usd(SCAN_HOT['min_mc'])}–{format_usd(SCAN_HOT['max_mc'])}\n"
        f"Min Liquidity: {format_usd(SCAN_HOT['min_liquidity'])}\n"
        f"Min Volume1h: {format_usd(SCAN_HOT['min_volume1h'])}\n"
        f"Min Price1h: {SCAN_HOT['min_price_change_1h']}%\n"
        f"Max Sell/Buy1h: {SCAN_HOT['max_sell_buy_1h']}x\n"
        f"Min Score: {SCAN_HOT['min_score']}\n\n"
        f"Checked pairs: {checked}\n"
        f"Passed: {len(passed)}\n"
        f"Rejected/no data: {rejected}\n\n"
    )

    if not passed:
        return header + "Сейчас hot-кандидатов нет. Это нормально: импульс не надо высасывать из воздуха."

    body = "\n\n".join(hot_candidate_line(item, idx) for idx, item in enumerate(passed[:5], start=1))

    return header + body
