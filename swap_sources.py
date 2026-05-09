from collections import Counter
from datetime import datetime, timezone
import time

import requests

from config import BIRDEYE_API_KEY, SOLSCAN_API_KEY
from price_sources import get_birdeye_price_near


SOLSCAN_BASE_URL = "https://pro-api.solscan.io/v2.0"
BIRDEYE_BASE_URL = "https://public-api.birdeye.so"
DEEP_MAX_PAGES = 5
DEEP10_MAX_PAGES = 10
DEEP_PAGE_SIZE = 50
DEEP_MAX_RAW_EVENTS = 250
DEEP10_MAX_RAW_EVENTS = 500
DEEP_DELAY_SECONDS = 1.2


def compact(value, left=6, right=4):
    if value is None or value == "":
        return "n/a"

    text = str(value)
    if len(text) <= left + right + 3:
        return text

    return f"{text[:left]}...{text[-right:]}"


def format_time(value):
    if value is None:
        return "n/a"

    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    text = str(value).strip()
    if not text:
        return "n/a"

    try:
        return format_time(float(text))
    except ValueError:
        return text


def to_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def format_amount(value):
    number = to_float(value)
    if number is None:
        return "n/a"

    if abs(number) >= 1:
        return f"{number:,.6f}".rstrip("0").rstrip(".")

    return f"{number:.12f}".rstrip("0").rstrip(".")


def format_usd(value):
    number = to_float(value)
    if number is None:
        return "n/a"

    return f"${number:,.2f}"


def format_percent(value):
    if value is None:
        return "n/a"

    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def format_price(value):
    number = to_float(value)
    if number is None:
        return "price unavailable"

    if abs(number) >= 1:
        return f"{number:.6f}".rstrip("0").rstrip(".")

    return f"{number:.12f}".rstrip("0").rstrip(".")


def extract_items(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ("items", "list", "txs", "transactions"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    for key in ("items", "list", "txs", "transactions"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    return []


def first_value(record, keys):
    if not isinstance(record, dict):
        return None

    for key in keys:
        if key in record and record[key] is not None:
            return record[key]

    return None


def token_text(value):
    if isinstance(value, dict):
        return (
            value.get("symbol")
            or value.get("token_symbol")
            or value.get("address")
            or value.get("mint")
            or value.get("token_address")
            or "n/a"
        )

    return value or "n/a"


def token_address(value):
    if isinstance(value, dict):
        return (
            value.get("address")
            or value.get("mint")
            or value.get("token_address")
            or value.get("tokenAddress")
            or value.get("token")
        )

    return value


def token_symbol(value):
    if isinstance(value, dict):
        return value.get("symbol") or value.get("token_symbol") or value.get("tokenSymbol")

    return value


def collect_raw_token_values(value):
    values = []

    if isinstance(value, dict):
        for key in (
            "address",
            "mint",
            "token",
            "token_address",
            "tokenAddress",
            "symbol",
            "token_symbol",
            "tokenSymbol",
        ):
            if value.get(key):
                values.append(str(value[key]))
    elif value:
        values.append(str(value))

    return values


def collect_item_token_values(item):
    values = []

    if not isinstance(item, dict):
        return values

    token_keys = (
        "token",
        "token_address",
        "tokenAddress",
        "mint",
        "address",
        "base",
        "quote",
        "from",
        "to",
        "from_token",
        "to_token",
        "token_in",
        "token_out",
        "sell_token",
        "buy_token",
        "source_token",
        "destination_token",
    )

    for key in token_keys:
        if key in item:
            values.extend(collect_raw_token_values(item.get(key)))

    routers = item.get("routers")
    if isinstance(routers, list):
        for router in routers:
            if isinstance(router, dict):
                for key in ("token1", "token2", "from_token", "to_token", "input_token", "output_token"):
                    if key in router:
                        values.extend(collect_raw_token_values(router.get(key)))

    return values


def normalize_solscan_item(item):
    routers = item.get("routers") if isinstance(item, dict) else None
    router = routers[0] if isinstance(routers, list) and routers else {}

    raw_token_in = first_value(router, ["token1", "from_token", "input_token"])
    raw_token_out = first_value(router, ["token2", "to_token", "output_token"])
    token_in = token_symbol(raw_token_in) or token_text(raw_token_in)
    token_out = token_symbol(raw_token_out) or token_text(raw_token_out)
    amount_in = first_value(router, ["amount1", "from_amount", "input_amount"])
    amount_out = first_value(router, ["amount2", "to_amount", "output_amount"])
    raw_values = collect_item_token_values(item)
    raw_values.extend(collect_raw_token_values(raw_token_in))
    raw_values.extend(collect_raw_token_values(raw_token_out))

    return {
        "time": format_time(first_value(item, ["block_time", "time", "timestamp"])),
        "token_in": token_in,
        "token_in_address": token_address(raw_token_in),
        "amount_in": amount_in,
        "token_out": token_out,
        "token_out_address": token_address(raw_token_out),
        "amount_out": amount_out,
        "usd_value": first_value(item, ["value", "usd_value", "usdValue", "amount_usd", "volume_usd"]),
        "tx": first_value(item, ["trans_id", "tx_hash", "txHash", "signature", "hash"]),
        "platform": first_value(item, ["platform", "source", "program", "activity_type"]) or "n/a",
        "raw_token_values": sorted(set(str(value) for value in raw_values if value)),
    }


def normalize_birdeye_item(item):
    raw_token_in = first_value(item, ["from", "from_token", "token_in", "base", "sell_token", "source_token"])
    raw_token_out = first_value(item, ["to", "to_token", "token_out", "quote", "buy_token", "destination_token"])
    token_in = token_symbol(raw_token_in) or token_text(raw_token_in)
    token_out = token_symbol(raw_token_out) or token_text(raw_token_out)
    raw_values = collect_item_token_values(item)
    raw_values.extend(collect_raw_token_values(raw_token_in))
    raw_values.extend(collect_raw_token_values(raw_token_out))

    return {
        "time": format_time(first_value(item, ["block_unix_time", "blockUnixTime", "block_time", "time", "timestamp"])),
        "token_in": token_in,
        "token_in_address": token_address(raw_token_in),
        "amount_in": first_value(
            item,
            [
                "from_amount",
                "amount_in",
                "sell_amount",
                "base_amount",
                "fromAmount",
                "from_ui_amount",
                "fromUiAmount",
                "sellAmount",
                "baseAmount",
            ],
        ),
        "token_out": token_out,
        "token_out_address": token_address(raw_token_out),
        "amount_out": first_value(
            item,
            [
                "to_amount",
                "amount_out",
                "buy_amount",
                "quote_amount",
                "toAmount",
                "to_ui_amount",
                "toUiAmount",
                "buyAmount",
                "quoteAmount",
            ],
        ),
        "usd_value": first_value(item, ["volume_usd", "value", "value_usd", "usd_value", "amount_usd"]),
        "tx": first_value(item, ["tx_hash", "txHash", "signature", "tx_id", "hash"]),
        "platform": first_value(item, ["source", "platform", "dex", "amm"]) or "n/a",
        "raw_token_values": sorted(set(str(value) for value in raw_values if value)),
    }


def request_solscan_swaps(wallet, token, limit):
    if not SOLSCAN_API_KEY:
        return {
            "ok": False,
            "source": "Solscan Pro / account defi activities",
            "status": "SOLSCAN_API_KEY missing",
            "items": [],
            "error": "SOLSCAN_API_KEY missing",
        }

    params = {
        "address": wallet,
        "activity_type[]": ["ACTIVITY_TOKEN_SWAP", "ACTIVITY_AGG_TOKEN_SWAP"],
        "page": 1,
        "page_size": limit,
        "sort_by": "block_time",
        "sort_order": "desc",
    }
    if token:
        params["token"] = token

    try:
        response = requests.get(
            f"{SOLSCAN_BASE_URL}/account/defi/activities",
            headers={"accept": "application/json", "token": SOLSCAN_API_KEY},
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        return {
            "ok": False,
            "source": "Solscan Pro / account defi activities",
            "status": "request_error",
            "items": [],
            "error": str(exc),
        }

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text[:500]}

    items = [normalize_solscan_item(item) for item in extract_items(payload) if isinstance(item, dict)]

    return {
        "ok": response.ok,
        "source": "Solscan Pro / account defi activities",
        "status": response.status_code,
        "items": items,
        "error": None if response.ok else str(payload)[:500],
    }


def request_birdeye_swaps_page(wallet, token, limit, offset=0):
    if not BIRDEYE_API_KEY:
        return {
            "ok": False,
            "source": "Birdeye /defi/v3/txs",
            "status": "BIRDEYE_API_KEY missing",
            "items": [],
            "error": "BIRDEYE_API_KEY missing",
        }

    params = {
        "owner": wallet,
        "limit": limit,
        "offset": offset,
        "sort_by": "block_unix_time",
        "sort_type": "desc",
        "tx_type": "swap",
    }
    if token:
        params["token_address"] = token

    try:
        response = requests.get(
            f"{BIRDEYE_BASE_URL}/defi/v3/txs",
            headers={"accept": "application/json", "X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"},
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        return {
            "ok": False,
            "source": "Birdeye /defi/v3/txs",
            "status": "request_error",
            "items": [],
            "error": str(exc),
        }

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text[:500]}

    items = [normalize_birdeye_item(item) for item in extract_items(payload) if isinstance(item, dict)]

    return {
        "ok": response.ok,
        "source": "Birdeye /defi/v3/txs",
        "status": response.status_code,
        "items": items,
        "error": None if response.ok else str(payload)[:500],
    }


def request_birdeye_swaps(wallet, token, limit):
    return request_birdeye_swaps_page(wallet, token, limit, 0)


def row_matches_token(item, token):
    if not token:
        return True

    wanted = str(token).strip().lower()
    candidates = [
        item.get("token_in"),
        item.get("token_out"),
        item.get("token_in_address"),
        item.get("token_out_address"),
    ]
    candidates.extend(item.get("raw_token_values") or [])

    return any(str(candidate).strip().lower() == wanted for candidate in candidates if candidate)


def apply_token_filter(result, token):
    if not token:
        result["token_filter_applied"] = False
        result["items_before_filter"] = len(result.get("items") or [])
        return result

    original = result.get("items") or []
    filtered = [item for item in original if row_matches_token(item, token)]
    result = dict(result)
    result["items"] = filtered
    result["items_before_filter"] = len(original)
    result["token_filter_applied"] = True
    return result


def has_token_sol_pair(summary):
    return summary.get("token_to_sol", 0) > 0 and summary.get("sol_to_token", 0) > 0


def request_birdeye_swaps_deep(wallet, token, mode="deep"):
    max_pages = DEEP10_MAX_PAGES if mode == "deep10" else DEEP_MAX_PAGES
    max_raw_events = DEEP10_MAX_RAW_EVENTS if mode == "deep10" else DEEP_MAX_RAW_EVENTS

    if not BIRDEYE_API_KEY:
        return {
            "ok": False,
            "source": f"Birdeye /defi/v3/txs {mode}",
            "status": "BIRDEYE_API_KEY missing",
            "items": [],
            "error": "BIRDEYE_API_KEY missing",
            "pages_scanned": 0,
            "raw_swaps_scanned": 0,
        }

    raw_items = []
    last_status = None
    last_error = None
    pages_scanned = 0
    rate_limited = False
    rate_limit_page = None

    for page in range(max_pages):
        if page:
            time.sleep(DEEP_DELAY_SECONDS)

        offset = page * DEEP_PAGE_SIZE
        result = request_birdeye_swaps_page(wallet, token, DEEP_PAGE_SIZE, offset)
        last_status = result.get("status")
        last_error = result.get("error")

        if not result.get("ok"):
            if result.get("status") == 429:
                rate_limited = True
                rate_limit_page = page + 1
            break

        page_items = result.get("items") or []
        pages_scanned += 1
        raw_items.extend(page_items)
        raw_items = raw_items[:max_raw_events]

        filtered = [item for item in raw_items if row_matches_token(item, token)]
        summary = build_summary(filtered)
        if token and has_token_sol_pair(summary):
            break

        if len(raw_items) >= max_raw_events or len(page_items) < DEEP_PAGE_SIZE:
            break

    status = last_status
    if rate_limited:
        status = "partial (rate limited 429)" if raw_items else "rate limited 429"

    return apply_token_filter(
        {
            "ok": bool(raw_items) or last_error is None,
            "source": f"Birdeye /defi/v3/txs {mode}",
            "status": status,
            "items": raw_items,
            "error": None if raw_items else last_error,
            "pages_scanned": pages_scanned,
            "raw_swaps_scanned": len(raw_items),
            "rate_limited": rate_limited,
            "rate_limit_page": rate_limit_page,
            "mode": mode,
            "max_pages": max_pages,
            "max_raw_events": max_raw_events,
        },
        token,
    )


def pick_swap_source(wallet, token, limit, mode="normal"):
    if mode in {"deep", "deep10"}:
        birdeye = request_birdeye_swaps_deep(wallet, token, mode)
        return birdeye, [birdeye]

    solscan = apply_token_filter(request_solscan_swaps(wallet, token, limit), token)
    if solscan["ok"] and solscan["items"]:
        return solscan, [solscan]

    birdeye = apply_token_filter(request_birdeye_swaps(wallet, token, limit), token)
    if birdeye["ok"] and birdeye["items"]:
        return birdeye, [solscan, birdeye]

    if solscan["ok"]:
        return solscan, [solscan, birdeye]

    return birdeye if birdeye["ok"] else solscan, [solscan, birdeye]


def build_summary(items):
    unique_tokens = set()
    input_tokens = Counter()
    output_tokens = Counter()
    total_usd = 0.0
    has_usd = False
    times = []
    token_to_sol = 0
    sol_to_token = 0

    for item in items:
        token_in = item.get("token_in") or "n/a"
        token_out = item.get("token_out") or "n/a"

        if token_in != "n/a":
            unique_tokens.add(token_in)
            input_tokens[token_in] += 1

        if token_out != "n/a":
            unique_tokens.add(token_out)
            output_tokens[token_out] += 1

        usd = to_float(item.get("usd_value"))
        if usd is not None:
            total_usd += usd
            has_usd = True

        time_value = item.get("time")
        if time_value and time_value != "n/a":
            times.append(time_value)

        token_in_lower = str(token_in).lower()
        token_out_lower = str(token_out).lower()
        if token_in_lower == "sol" and token_out_lower != "sol":
            sol_to_token += 1
        elif token_out_lower == "sol" and token_in_lower != "sol":
            token_to_sol += 1

    return {
        "total": len(items),
        "unique_tokens": len(unique_tokens),
        "total_usd": total_usd if has_usd else None,
        "main_input": input_tokens.most_common(1)[0][0] if input_tokens else "n/a",
        "main_output": output_tokens.most_common(1)[0][0] if output_tokens else "n/a",
        "first_time": min(times) if times else "n/a",
        "last_time": max(times) if times else "n/a",
        "token_to_sol": token_to_sol,
        "sol_to_token": sol_to_token,
    }


def build_sell_window_price_check(items, token):
    if not token:
        return []

    sell_events = [
        item
        for item in items
        if str(item.get("token_out") or "").lower() == "sol"
        and str(item.get("token_in") or "").lower() != "sol"
        and item.get("time")
        and item.get("time") != "n/a"
    ]

    if not sell_events:
        return []

    if not BIRDEYE_API_KEY:
        return ["", "Sell window price check skipped: BIRDEYE_API_KEY missing."]

    sell_events = sorted(sell_events, key=lambda item: item.get("time") or "")
    first_sell = sell_events[0]
    last_sell = sell_events[-1]
    first_time = first_sell.get("time")
    last_time = last_sell.get("time")

    first_price = get_birdeye_price_near(token, first_time)
    time.sleep(0.2)
    last_price = get_birdeye_price_near(token, last_time)

    first_value = first_price.get("price") if first_price.get("ok") else None
    last_value = last_price.get("price") if last_price.get("ok") else None
    price_change = None

    if first_value is not None and last_value is not None and first_value != 0:
        price_change = ((last_value - first_value) / first_value) * 100

    total_sell_usd = 0.0
    has_sell_usd = False
    for item in sell_events:
        usd = to_float(item.get("usd_value"))
        if usd is not None:
            total_sell_usd += usd
            has_sell_usd = True

    return [
        "",
        "Sell Window Price Check:",
        f"- Sell events: {len(sell_events)}",
        f"- First sell: {first_time} / {format_price(first_value)}",
        f"- Last sell: {last_time} / {format_price(last_value)}",
        f"- Price change during sell window: {format_percent(price_change)}",
        f"- Total sell USD value: {format_usd(total_sell_usd if has_sell_usd else None)}",
    ]


def build_wallet_swaps_text(wallet, token=None, limit=20, mode="normal"):
    mode = str(mode).lower()
    mode = mode if mode in {"deep", "deep10"} else "normal"
    safe_limit = min(max(int(limit), 1), 50)
    token = (token or "").strip() or None
    result, attempts = pick_swap_source(wallet, token, safe_limit, mode)
    items = result.get("items") or []
    summary = build_summary(items)

    lines = [
        "Wallet Swaps Diagnostic",
        f"Wallet: {compact(wallet)}",
        f"Token filter: {compact(token) if token else 'none'}",
        f"Mode: {mode}",
        f"Pages scanned: {result.get('pages_scanned', 1 if result.get('ok') else 0)}",
        f"Raw swaps scanned: {result.get('raw_swaps_scanned', result.get('items_before_filter', len(items)))}",
        f"Rate limited: {'yes' if result.get('rate_limited') else 'no'}",
        f"Token filter applied: {'yes' if token else 'no'}",
        f"Source used: {result.get('source')}",
        f"Status: {result.get('status')}",
        f"Items after filter: {len(items)}",
    ]

    if result.get("rate_limited"):
        lines.append(f"Rate limit hit after page: {result.get('rate_limit_page') or 'n/a'}")

    if attempts and attempts[0].get("error") == "SOLSCAN_API_KEY missing":
        lines.append("Solscan: SOLSCAN_API_KEY missing")

    if result.get("error") and not items:
        lines.append(f"Error: {result['error']}")

    lines.extend(
        [
            "",
            "Summary:",
            f"- Total swaps{' after filter' if token else ''}: {summary['total']}",
            f"- Unique tokens involved: {summary['unique_tokens']}",
            f"- Total USD value: {format_usd(summary['total_usd'])}",
            f"- Most common input token: {summary['main_input']}",
            f"- Most common output token: {summary['main_output']}",
            f"- First swap time: {summary['first_time']}",
            f"- Last swap time: {summary['last_time']}",
        ]
    )

    if token:
        lines.extend(
            [
                f"- Direction token -> SOL count: {summary['token_to_sol']}",
                f"- Direction SOL -> token count: {summary['sol_to_token']}",
                f"- Has possible buy: {'yes' if summary['sol_to_token'] > 0 else 'no'}",
                f"- Has possible sell: {'yes' if summary['token_to_sol'] > 0 else 'no'}",
            ]
        )

    lines.extend(build_sell_window_price_check(items, token))

    lines.extend(["", "Events:"])

    visible_items = items[:20]
    if not visible_items:
        if token:
            lines.append("No swaps found for this wallet/token in returned window.")
        else:
            lines.append("No parsed swap events returned.")
    else:
        for idx, item in enumerate(visible_items, start=1):
            lines.append(
                f"#{idx} {item.get('time') or 'n/a'} | "
                f"{item.get('token_in') or 'n/a'} {format_amount(item.get('amount_in'))} -> "
                f"{item.get('token_out') or 'n/a'} {format_amount(item.get('amount_out'))} | "
                f"value: {format_usd(item.get('usd_value'))} | "
                f"tx: {compact(item.get('tx'))}"
            )

    if len(items) > 20:
        lines.append("Showing first 20 rows only")

    if token:
        if summary["token_to_sol"] > 0 and summary["sol_to_token"] > 0:
            lines.append("Both possible buy and sell events found. Suitable for future wallettrade swap-cycle analysis.")
        elif summary["token_to_sol"] > 0:
            lines.append("Only possible sell events found in scanned window.")
        elif summary["sol_to_token"] > 0:
            lines.append("Only possible buy events found in scanned window.")
        elif mode == "deep10":
            lines.append("No possible buy found in scanned window. Buy may be older, routed differently, or received via transfer.")

    lines.extend(
        [
            "",
            "Notes:",
            "- No amount-based return calculated.",
            "- No entry/exit quality calculated.",
            "- Manual diagnostic only.",
        ]
    )

    return "\n".join(lines)
