import time
from datetime import datetime, timezone

import requests

from config import BIRDEYE_API_KEY
from swap_sources import (
    compact,
    extract_items,
    first_value,
    format_amount,
    format_time,
    format_usd,
    to_float,
    token_address,
    token_symbol,
    token_text,
)


BIRDEYE_BASE_URL = "https://public-api.birdeye.so"
SOL_MINT = "So11111111111111111111111111111111111111112"
DEEP_PAGE_SIZE = 50
DEEP_MAX_PAGES = 5
DEEP10_MAX_PAGES = 10
DEEP_MAX_RAW_TRADES = 250
DEEP10_MAX_RAW_TRADES = 500
DEEP_DELAY_SECONDS = 1.2
MAKER_EARLY_STOP_COUNT = 20
MAKER_FIND_DEEP_MAX_PAGES = 20
MAKER_FIND_DEEP50_MAX_PAGES = 50
MAKER_FIND_DEEP_MAX_RAW_TRADES = 1000
MAKER_FIND_DEEP50_MAX_RAW_TRADES = 2500
MAKER_FIND_DEEP_EARLY_STOP_COUNT = 20
MAKER_FIND_DEEP50_EARLY_STOP_COUNT = 50
MAKER_FIND_AROUND_WINDOW_SECONDS = 2 * 60 * 60
MAKER_FIND_AROUND_MAX_PAGES = 20
MAKER_FIND_AROUND_MAX_RAW_TRADES = 1000
MAKER_FIND_AROUND_EARLY_STOP_COUNT = 50
MAKER_DIRECT_KEYS = {
    "owner",
    "wallet",
    "maker",
    "trader",
    "user",
    "address",
    "sourceOwner",
    "source_owner",
    "tx_from",
    "signer",
    "signer_address",
    "signerAddress",
    "authority",
    "signerAuthority",
}
MAKER_KEY_HINTS = ("owner", "wallet", "maker", "trader", "user", "authority")


def is_sol_token(value):
    if value is None:
        return False

    text = str(value).strip().lower()
    return text in {"sol", "wsol", SOL_MINT.lower()}


def normalize_side(value):
    if value is None:
        return "UNKNOWN"

    text = str(value).strip().lower()
    if text in {"buy", "bought", "bid"} or "buy" in text:
        return "BUY"
    if text in {"sell", "sold", "ask"} or "sell" in text:
        return "SELL"

    return "UNKNOWN"


def collect_maker_like_values(value, parent_key=""):
    matches = []

    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            key_lower = key_text.lower()
            is_maker_key = (
                key_text in MAKER_DIRECT_KEYS
                or key_lower in {item.lower() for item in MAKER_DIRECT_KEYS}
                or any(hint in key_lower for hint in MAKER_KEY_HINTS)
                or key_lower == "tx_from"
                or key_lower == "signer"
                or (key_lower == "address" and any(hint in parent_key.lower() for hint in MAKER_KEY_HINTS))
            )

            if is_maker_key and not isinstance(child, (dict, list)):
                matches.append((key_text, str(child)))

            matches.extend(collect_maker_like_values(child, key_text))
    elif isinstance(value, list):
        for child in value:
            matches.extend(collect_maker_like_values(child, parent_key))

    return matches


def maker_like_values(item):
    pairs = collect_maker_like_values(item)
    values = []
    seen = set()

    for key, value in pairs:
        normalized = str(value).strip()
        if not normalized:
            continue

        marker = (key, normalized)
        if marker not in seen:
            values.append({"key": key, "value": normalized})
            seen.add(marker)

    return values


def maker_like_keys_seen(items):
    keys = []
    seen = set()

    for item in items:
        for row in maker_like_values(item):
            key = row["key"]
            if key not in seen:
                keys.append(key)
                seen.add(key)

    return keys


def item_matches_maker(item, maker):
    wanted = str(maker).strip().lower()
    return any(row["value"].strip().lower() == wanted for row in maker_like_values(item))


def maker_like_text(item):
    values = maker_like_values(item)
    if not values:
        return "n/a"

    return ", ".join(f"{row['key']}={compact(row['value'])}" for row in values[:3])


def normalize_maker_trade(item):
    raw_token_in = first_value(item, ["from", "from_token", "token_in", "base", "sell_token", "source_token"])
    raw_token_out = first_value(item, ["to", "to_token", "token_out", "quote", "buy_token", "destination_token"])
    token_in = token_symbol(raw_token_in) or token_text(raw_token_in)
    token_out = token_symbol(raw_token_out) or token_text(raw_token_out)
    token_in_address = token_address(raw_token_in)
    token_out_address = token_address(raw_token_out)
    side = normalize_side(
        first_value(
            item,
            [
                "side",
                "trade_side",
                "tradeSide",
                "type",
                "base_type",
                "baseType",
                "swap_type",
                "swapType",
            ],
        )
    )

    if side == "UNKNOWN":
        in_is_sol = is_sol_token(token_in) or is_sol_token(token_in_address)
        out_is_sol = is_sol_token(token_out) or is_sol_token(token_out_address)
        if in_is_sol and not out_is_sol:
            side = "BUY"
        elif out_is_sol and not in_is_sol:
            side = "SELL"

    amount = None
    if side == "BUY":
        amount = first_value(item, ["to_amount", "amount_out", "buy_amount", "toAmount", "to_ui_amount", "toUiAmount"])
    elif side == "SELL":
        amount = first_value(item, ["from_amount", "amount_in", "sell_amount", "fromAmount", "from_ui_amount", "fromUiAmount"])

    if amount is None:
        amount = first_value(
            item,
            [
                "base_amount",
                "baseAmount",
                "amount",
                "ui_amount",
                "uiAmount",
                "from_amount",
                "to_amount",
                "amount_in",
                "amount_out",
            ],
        )

    return {
        "time": format_time(first_value(item, ["block_unix_time", "blockUnixTime", "block_time", "time", "timestamp"])),
        "side": side,
        "token_in": token_in,
        "token_out": token_out,
        "amount": amount,
        "usd_value": first_value(item, ["volume_usd", "value", "value_usd", "usd_value", "amount_usd", "amountUsd"]),
        "tx": first_value(item, ["tx_hash", "txHash", "signature", "tx_id", "hash"]),
    }


def parse_anchor_timestamp(value):
    text = str(value or "").strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return int(parsed.timestamp())


def get_birdeye_pair_trades_page(pair, limit=50, offset=0, before_time=None, after_time=None):
    use_time_filter = before_time is not None and after_time is not None
    endpoint = "/defi/txs/pair/seek_by_time" if use_time_filter else "/defi/txs/pair"
    params = {
        "address": pair,
        "limit": min(max(int(limit), 1), 50),
        "offset": offset,
        "tx_type": "swap",
    }
    if use_time_filter:
        params["before_time"] = int(before_time)
        params["after_time"] = int(after_time)
    else:
        params["sort_type"] = "desc"

    try:
        response = requests.get(
            f"{BIRDEYE_BASE_URL}{endpoint}",
            headers={"accept": "application/json", "X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"},
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        return {"ok": False, "status": "request_error", "error": str(exc), "items": [], "params": params}

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text[:500]}

    return {
        "ok": response.ok,
        "status": response.status_code,
        "error": None if response.ok else str(payload)[:500],
        "items": [item for item in extract_items(payload) if isinstance(item, dict)],
        "params": params,
        "endpoint": endpoint,
    }


def get_birdeye_maker_trades(pair, maker, limit=50, mode="normal"):
    if not BIRDEYE_API_KEY:
        return {
            "ok": False,
            "source": "Birdeye /defi/txs/pair",
            "status": "BIRDEYE_API_KEY missing",
            "items": [],
            "pair_items": [],
            "error": "BIRDEYE_API_KEY missing",
            "maker_filter_applied": True,
            "maker_like_keys_seen": [],
            "params": {"address": pair, "limit": limit},
            "mode": mode,
            "pages_scanned": 0,
            "raw_pair_trades_scanned": 0,
            "rate_limited": False,
        }

    mode = str(mode).lower()
    mode = mode if mode in {"deep", "deep10"} else "normal"
    safe_limit = min(max(int(limit), 1), 50)
    max_pages = 1
    max_raw_trades = safe_limit
    page_size = safe_limit

    if mode == "deep":
        max_pages = DEEP_MAX_PAGES
        max_raw_trades = DEEP_MAX_RAW_TRADES
        page_size = DEEP_PAGE_SIZE
    elif mode == "deep10":
        max_pages = DEEP10_MAX_PAGES
        max_raw_trades = DEEP10_MAX_RAW_TRADES
        page_size = DEEP_PAGE_SIZE

    pair_items_raw = []
    maker_items_raw = []
    pages_scanned = 0
    last_status = None
    last_error = None
    rate_limited = False

    for page_index in range(max_pages):
        if page_index:
            time.sleep(DEEP_DELAY_SECONDS)

        offset = page_index * page_size
        page_result = get_birdeye_pair_trades_page(pair, page_size, offset)
        last_status = page_result.get("status")
        last_error = page_result.get("error")

        if not page_result.get("ok"):
            if page_result.get("status") == 429:
                rate_limited = True
            break

        page_items = page_result.get("items") or []
        pages_scanned += 1
        pair_items_raw.extend(page_items)
        pair_items_raw = pair_items_raw[:max_raw_trades]
        maker_items_raw.extend(item for item in page_items if item_matches_maker(item, maker))

        if len(maker_items_raw) >= MAKER_EARLY_STOP_COUNT:
            break
        if len(pair_items_raw) >= max_raw_trades or len(page_items) < page_size:
            break

    maker_items_raw = maker_items_raw[:max_raw_trades]
    items = [normalize_maker_trade(item) for item in maker_items_raw]
    pair_items = [normalize_maker_trade(item) for item in pair_items_raw]
    status = last_status
    if rate_limited:
        status = "partial (rate limited 429)" if pair_items_raw or maker_items_raw else "rate limited 429"
    ok_status = isinstance(last_status, int) and 200 <= last_status < 300

    return {
        "ok": bool(pair_items_raw or maker_items_raw) or (ok_status and not rate_limited),
        "source": "Birdeye /defi/txs/pair",
        "status": status,
        "items": items,
        "pair_items": pair_items,
        "items_from_pair_endpoint": len(pair_items_raw),
        "pages_scanned": pages_scanned,
        "raw_pair_trades_scanned": len(pair_items_raw),
        "mode": mode,
        "rate_limited": rate_limited,
        "maker_filter_applied": True,
        "maker_like_keys_seen": maker_like_keys_seen(pair_items_raw),
        "debug_pair_rows": [
            {**normalize_maker_trade(item), "maker_like": maker_like_text(item)}
            for item in pair_items_raw[:3]
        ],
        "error": None if pair_items_raw or maker_items_raw or ok_status else last_error,
        "params": {
            "address": pair,
            "offset": "page_index * page_size",
            "limit": page_size,
            "tx_type": "swap",
            "sort_type": "desc",
        },
    }


def scan_birdeye_maker_find(pair, maker, mode, max_pages, max_raw_trades, early_stop, before_time=None, after_time=None):
    pair_items_raw = []
    matched_raw = []
    pages_scanned = 0
    last_status = None
    last_error = None
    rate_limited = False
    rate_limit_page = None

    for page_index in range(max_pages):
        if page_index:
            time.sleep(DEEP_DELAY_SECONDS)

        offset = page_index * DEEP_PAGE_SIZE
        page_result = get_birdeye_pair_trades_page(
            pair,
            DEEP_PAGE_SIZE,
            offset,
            before_time=before_time,
            after_time=after_time,
        )
        last_status = page_result.get("status")
        last_error = page_result.get("error")

        if not page_result.get("ok"):
            if page_result.get("status") == 429:
                rate_limited = True
                rate_limit_page = page_index + 1
            break

        page_items = page_result.get("items") or []
        pages_scanned += 1

        for item in page_items:
            if len(pair_items_raw) < max_raw_trades:
                pair_items_raw.append(item)
            if item_matches_maker(item, maker):
                matched_raw.append({**item, "_makerfind_page": page_index + 1})

        if len(matched_raw) >= early_stop:
            break
        if len(pair_items_raw) >= max_raw_trades or len(page_items) < DEEP_PAGE_SIZE:
            break

    items = []
    for item in matched_raw:
        normalized = normalize_maker_trade(item)
        normalized["page"] = item.get("_makerfind_page")
        items.append(normalized)

    status = last_status
    if rate_limited:
        status = "partial (rate limited 429)" if pair_items_raw or matched_raw else "rate limited 429"

    return {
        "source": "Birdeye /defi/txs/pair",
        "status": status,
        "items": items,
        "error": None if pair_items_raw or matched_raw else last_error,
        "mode": mode,
        "pages_scanned": pages_scanned,
        "raw_pair_trades_scanned": len(pair_items_raw),
        "rate_limited": rate_limited,
        "rate_limit_page": rate_limit_page,
        "time_filter_applied": before_time is not None and after_time is not None,
        "time_params": (
            f"after_time={after_time}, before_time={before_time}"
            if before_time is not None and after_time is not None
            else "n/a"
        ),
        "anchored_scan_fallback": False,
        "anchored_scan_message": None,
        "maker_like_keys_seen": maker_like_keys_seen(pair_items_raw),
        "debug_pair_rows": [
            {**normalize_maker_trade(item), "maker_like": maker_like_text(item)}
            for item in pair_items_raw[:3]
        ],
    }


def get_birdeye_maker_find(pair, maker, mode="deep", anchor_time=None, allow_fallback=False):
    mode = str(mode).lower()
    mode = mode if mode in {"around", "deep50"} else "deep"

    if not BIRDEYE_API_KEY:
        return {
            "source": "Birdeye /defi/txs/pair",
            "status": "BIRDEYE_API_KEY missing",
            "items": [],
            "error": "BIRDEYE_API_KEY missing",
            "mode": mode,
            "anchor_time": anchor_time or "n/a",
            "window": "+/-2h" if mode == "around" else "n/a",
            "pages_scanned": 0,
            "raw_pair_trades_scanned": 0,
            "rate_limited": False,
            "rate_limit_page": None,
            "time_filter_applied": False,
            "time_params": "n/a",
            "anchored_scan_fallback": False,
            "anchored_scan_message": None,
            "anchored_strict": mode == "around",
            "fallback_used": False,
            "anchored_unavailable": False,
            "maker_like_keys_seen": [],
            "debug_pair_rows": [],
        }

    if mode == "around":
        anchor_unix = parse_anchor_timestamp(anchor_time)
        if anchor_unix is None:
            return {
                "source": "Birdeye /defi/txs/pair",
                "status": "invalid anchor timestamp",
                "items": [],
                "error": "invalid anchor timestamp",
                "mode": mode,
                "anchor_time": anchor_time or "n/a",
                "window": "+/-2h",
                "pages_scanned": 0,
                "raw_pair_trades_scanned": 0,
                "rate_limited": False,
                "rate_limit_page": None,
                "time_filter_applied": False,
                "time_params": "n/a",
                "anchored_scan_fallback": False,
                "anchored_scan_message": None,
                "anchored_strict": True,
                "fallback_used": False,
                "anchored_unavailable": True,
                "maker_like_keys_seen": [],
                "debug_pair_rows": [],
            }

        after_time = anchor_unix - MAKER_FIND_AROUND_WINDOW_SECONDS
        before_time = anchor_unix + MAKER_FIND_AROUND_WINDOW_SECONDS
        time_result = scan_birdeye_maker_find(
            pair,
            maker,
            mode,
            MAKER_FIND_AROUND_MAX_PAGES,
            MAKER_FIND_AROUND_MAX_RAW_TRADES,
            MAKER_FIND_AROUND_EARLY_STOP_COUNT,
            before_time=before_time,
            after_time=after_time,
        )
        time_result["anchor_time"] = anchor_time
        time_result["window"] = "+/-2h"
        time_result["source"] = "Birdeye /defi/txs/pair/seek_by_time"
        time_result["anchored_strict"] = not allow_fallback
        time_result["fallback_used"] = False
        time_result["anchored_unavailable"] = False

        if time_result.get("rate_limited"):
            time_result["time_filter_applied"] = False
            time_result["anchored_scan_message"] = (
                "Anchored scan stopped: Birdeye rate limit hit before time-window results were available."
            )
            return time_result
        if time_result.get("raw_pair_trades_scanned", 0) > 0 or time_result.get("items"):
            return time_result

        if not allow_fallback:
            time_result["time_filter_applied"] = False
            time_result["anchored_unavailable"] = True
            time_result["anchored_scan_message"] = (
                "Anchored scan unavailable: time-window query did not return usable results."
            )
            return time_result

        time.sleep(DEEP_DELAY_SECONDS)
        fallback = scan_birdeye_maker_find(
            pair,
            maker,
            mode,
            MAKER_FIND_AROUND_MAX_PAGES,
            MAKER_FIND_AROUND_MAX_RAW_TRADES,
            MAKER_FIND_AROUND_EARLY_STOP_COUNT,
        )
        fallback["anchor_time"] = anchor_time
        fallback["window"] = "+/-2h"
        fallback["anchored_scan_fallback"] = True
        fallback["anchored_strict"] = False
        fallback["fallback_used"] = True
        fallback["anchored_unavailable"] = False
        fallback["time_filter_applied"] = False
        fallback["time_params"] = f"after_time={after_time}, before_time={before_time}"
        if time_result.get("status") == 200:
            fallback["anchored_scan_message"] = "Time-window returned no rows; latest-window fallback used."
        else:
            fallback["anchored_scan_message"] = "Anchored scan fallback: time params unavailable."
        return fallback

    max_pages = MAKER_FIND_DEEP50_MAX_PAGES if mode == "deep50" else MAKER_FIND_DEEP_MAX_PAGES
    max_raw_trades = MAKER_FIND_DEEP50_MAX_RAW_TRADES if mode == "deep50" else MAKER_FIND_DEEP_MAX_RAW_TRADES
    early_stop = MAKER_FIND_DEEP50_EARLY_STOP_COUNT if mode == "deep50" else MAKER_FIND_DEEP_EARLY_STOP_COUNT
    result = scan_birdeye_maker_find(pair, maker, mode, max_pages, max_raw_trades, early_stop)
    result["anchor_time"] = "n/a"
    result["window"] = "n/a"
    result["anchored_strict"] = False
    result["fallback_used"] = False
    result["anchored_unavailable"] = False
    return result


def summarize_maker_trades(items):
    buy_count = 0
    sell_count = 0
    total_buy_usd = 0.0
    total_sell_usd = 0.0
    has_buy_usd = False
    has_sell_usd = False
    times = []

    for item in items:
        side = item.get("side")
        usd = to_float(item.get("usd_value"))

        if side == "BUY":
            buy_count += 1
            if usd is not None:
                total_buy_usd += usd
                has_buy_usd = True
        elif side == "SELL":
            sell_count += 1
            if usd is not None:
                total_sell_usd += usd
                has_sell_usd = True

        time_value = item.get("time")
        if time_value and time_value != "n/a":
            times.append(time_value)

    if buy_count > sell_count:
        net_direction = "buy-heavy"
    elif sell_count > buy_count:
        net_direction = "sell-heavy"
    elif buy_count or sell_count:
        net_direction = "mixed"
    else:
        net_direction = "n/a"

    return {
        "total": len(items),
        "buy_count": buy_count,
        "sell_count": sell_count,
        "unknown_count": len([item for item in items if item.get("side") not in {"BUY", "SELL"}]),
        "total_buy_usd": total_buy_usd if has_buy_usd else None,
        "total_sell_usd": total_sell_usd if has_sell_usd else None,
        "first_time": min(times) if times else "n/a",
        "last_time": max(times) if times else "n/a",
        "net_direction": net_direction,
    }


def classify_maker_behavior(summary):
    total = summary.get("total", 0)
    buy_count = summary.get("buy_count", 0)
    sell_count = summary.get("sell_count", 0)

    if total < 3:
        return "Weak Sample"
    if buy_count >= 3 and sell_count == 0:
        return "Maker Accumulation"
    if sell_count >= 3 and buy_count == 0:
        return "Maker Distribution"
    if buy_count > 0 and sell_count > 0:
        return "Two-sided Active Maker"

    return "Needs More Data"


def build_classification_evidence(summary):
    return [
        f"{summary['buy_count']} buys",
        f"{summary['sell_count']} sells",
        f"Total buy value: {format_usd(summary['total_buy_usd'])}",
        f"Total sell value: {format_usd(summary['total_sell_usd'])}",
    ]


def behavior_hint(summary):
    total = summary.get("total", 0)
    buy_count = summary.get("buy_count", 0)
    sell_count = summary.get("sell_count", 0)

    if total == 0:
        return "Not Found"
    if total < 3:
        return "Weak Sample"
    if buy_count >= 3 and sell_count == 0:
        return "Possible Accumulation Watch"
    if sell_count >= 3 and buy_count == 0:
        return "Possible Distribution Watch"
    if buy_count > 0 and sell_count > 0:
        return "Two-sided Active Maker"

    return "Weak Sample"


def build_maker_find_text(pair, maker, mode="deep", anchor_time=None, allow_fallback=False):
    result = get_birdeye_maker_find(pair, maker, mode, anchor_time, allow_fallback)
    items = result.get("items") or []
    summary = summarize_maker_trades(items)
    pages = [item.get("page") for item in items if item.get("page")]
    behavior = "Not Found / Anchored Unavailable" if result.get("anchored_unavailable") else behavior_hint(summary)

    lines = [
        "Maker Find Diagnostic",
        f"Pair: {compact(pair)}",
        f"Maker: {compact(maker)}",
        f"Mode: {result.get('mode')}",
        f"Anchor time: {result.get('anchor_time', 'n/a')}",
        f"Window: {result.get('window', 'n/a')}",
        f"Source used: {result.get('source')}",
        f"Status: {result.get('status')}",
        f"Pages scanned: {result.get('pages_scanned', 0)}",
        f"Raw pair trades scanned: {result.get('raw_pair_trades_scanned', 0)}",
        f"Matched maker trades: {len(items)}",
        f"Rate limited: {'yes' if result.get('rate_limited') else 'no'}",
        f"Time filter applied: {'yes' if result.get('time_filter_applied') else 'no'}",
        f"Time params: {result.get('time_params', 'n/a')}",
        f"Anchored strict: {'yes' if result.get('anchored_strict') else 'no'}",
        f"Fallback used: {'yes' if result.get('fallback_used') else 'no'}",
    ]

    if result.get("rate_limited"):
        lines.append(f"Rate limit hit after page: {result.get('rate_limit_page') or 'n/a'}")
    if result.get("anchored_scan_message"):
        lines.append(result["anchored_scan_message"])
    if result.get("anchored_unavailable"):
        lines.append("Latest-window fallback skipped for strict anchored scan.")
    if result.get("fallback_used"):
        lines.append("Warning: results are latest-window, not anchored.")
    if result.get("error") and not items:
        lines.append(f"Error: {result['error']}")

    lines.extend(
        [
            "",
            "Summary:",
            f"- Buy count: {summary['buy_count']}",
            f"- Sell count: {summary['sell_count']}",
            f"- Unknown count: {summary['unknown_count']}",
            f"- First seen trade: {summary['first_time']}",
            f"- Last seen trade: {summary['last_time']}",
            f"- First seen page: {min(pages) if pages else 'n/a'}",
            f"- Last seen page: {max(pages) if pages else 'n/a'}",
            f"- Net direction: {summary['net_direction']}",
            "",
            "Behavior Hint:",
            f"- {behavior}",
            "",
            "Events:",
        ]
    )

    visible_items = items[:10]
    if not visible_items:
        lines.append("Maker not found in scanned pair-trade window.")
        keys = result.get("maker_like_keys_seen") or []
        lines.append(f"Maker-like keys seen: {', '.join(keys) if keys else 'n/a'}")
        debug_rows = result.get("debug_pair_rows") or []
        if debug_rows:
            lines.extend(["", "Pair endpoint sample rows:"])
            for idx, item in enumerate(debug_rows[:3], start=1):
                lines.append(
                    f"#{idx} {item.get('time') or 'n/a'} | "
                    f"{item.get('side') or 'UNKNOWN'} | "
                    f"value: {format_usd(item.get('usd_value'))} | "
                    f"tx: {compact(item.get('tx'))} | "
                    f"maker-like: {item.get('maker_like') or 'n/a'}"
                )
    else:
        for idx, item in enumerate(visible_items, start=1):
            lines.append(
                f"#{idx} {item.get('time') or 'n/a'} | "
                f"{item.get('side') or 'UNKNOWN'} | "
                f"page: {item.get('page') or 'n/a'} | "
                f"value: {format_usd(item.get('usd_value'))} | "
                f"tx: {compact(item.get('tx'))}"
            )

    if len(items) > 10:
        lines.append("Showing first 10 matched trades only")

    lines.extend(
        [
            "",
            "Notes:",
            "- No PnL calculated.",
            "- No trading advice.",
            "- Manual diagnostic only.",
        ]
    )

    return "\n".join(lines)


def build_maker_trades_text(pair, maker, limit=50, mode="normal"):
    safe_limit = min(max(int(limit), 1), 50)
    mode = str(mode).lower()
    mode = mode if mode in {"deep", "deep10"} else "normal"
    result = get_birdeye_maker_trades(pair, maker, safe_limit, mode)
    items = result.get("items") or []
    summary = summarize_maker_trades(items)
    classification = classify_maker_behavior(summary)

    lines = [
        "Maker Trades Diagnostic",
        f"Pair: {compact(pair)}",
        f"Maker: {compact(maker)}",
        f"Source used: {result.get('source')}",
        f"Mode: {result.get('mode', mode)}",
        f"Status: {result.get('status')}",
        f"Items returned: {len(items)}",
        f"Pages scanned: {result.get('pages_scanned', 0)}",
        f"Raw pair trades scanned: {result.get('raw_pair_trades_scanned', result.get('items_from_pair_endpoint', 0))}",
        f"Rate limited: {'yes' if result.get('rate_limited') else 'no'}",
    ]

    if result.get("maker_filter_applied"):
        lines.extend(
            [
                f"Items from pair endpoint: {result.get('items_from_pair_endpoint', 0)}",
                f"Items after maker filter: {len(items)}",
                "Maker filter applied: yes",
            ]
        )

    if result.get("error") and not items:
        lines.append(f"Error: {result['error']}")

    lines.extend(
        [
            "",
            "Summary:",
            f"- Total trades: {summary['total']}",
            f"- Buy count: {summary['buy_count']}",
            f"- Sell count: {summary['sell_count']}",
            f"- Total buy USD: {format_usd(summary['total_buy_usd'])}",
            f"- Total sell USD: {format_usd(summary['total_sell_usd'])}",
            f"- First trade time: {summary['first_time']}",
            f"- Last trade time: {summary['last_time']}",
            f"- Net direction: {summary['net_direction']}",
            "",
            "Behavior Classification:",
            f"- Primary: {classification}",
            "- Evidence:",
        ]
    )
    lines.extend(f"  - {item}" for item in build_classification_evidence(summary))
    lines.extend(["", "Events:"])

    visible_items = items[:20]
    if not visible_items:
        lines.append("No maker trades returned for this pair/maker window.")
        lines.append("Maker not found in scanned pair-trade window.")
        if result.get("maker_filter_applied"):
            keys = result.get("maker_like_keys_seen") or []
            lines.append(f"Maker-like keys seen: {', '.join(keys) if keys else 'n/a'}")
            debug_rows = result.get("debug_pair_rows") or []
            if debug_rows:
                lines.extend(["", "Pair endpoint sample rows:"])
                for idx, item in enumerate(debug_rows[:3], start=1):
                    lines.append(
                        f"#{idx} {item.get('time') or 'n/a'} | "
                        f"{item.get('side') or 'UNKNOWN'} | "
                        f"value: {format_usd(item.get('usd_value'))} | "
                        f"tx: {compact(item.get('tx'))} | "
                        f"maker-like: {item.get('maker_like') or 'n/a'}"
                    )
    else:
        for idx, item in enumerate(visible_items, start=1):
            lines.append(
                f"#{idx} {item.get('time') or 'n/a'} | "
                f"{item.get('side') or 'UNKNOWN'} | "
                f"value: {format_usd(item.get('usd_value'))} | "
                f"tx: {compact(item.get('tx'))}"
            )

    if len(items) > 20:
        lines.append("Showing first 20 rows only")

    lines.extend(
        [
            "",
            "Notes:",
            "- No PnL calculated.",
            "- No trading advice.",
            "- Manual diagnostic only.",
        ]
    )

    return "\n".join(lines)
