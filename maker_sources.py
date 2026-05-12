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


def get_birdeye_maker_trades(pair, maker, limit=50):
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
        }

    safe_limit = min(max(int(limit), 1), 50)
    params = {
        "address": pair,
        "limit": safe_limit,
        "offset": 0,
        "tx_type": "swap",
        "sort_type": "desc",
    }

    try:
        response = requests.get(
            f"{BIRDEYE_BASE_URL}/defi/txs/pair",
            headers={"accept": "application/json", "X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"},
            params=params,
            timeout=20,
        )
    except requests.RequestException as exc:
        return {
            "ok": False,
            "source": "Birdeye /defi/txs/pair",
            "status": "request_error",
            "items": [],
            "pair_items": [],
            "error": str(exc),
            "maker_filter_applied": True,
            "maker_like_keys_seen": [],
            "params": params,
        }

    try:
        payload = response.json()
    except ValueError:
        payload = {"raw_text": response.text[:500]}

    pair_items_raw = [item for item in extract_items(payload) if isinstance(item, dict)]
    maker_items_raw = [item for item in pair_items_raw if item_matches_maker(item, maker)]
    items = [normalize_maker_trade(item) for item in maker_items_raw]
    pair_items = [normalize_maker_trade(item) for item in pair_items_raw]

    return {
        "ok": response.ok,
        "source": "Birdeye /defi/txs/pair",
        "status": response.status_code,
        "items": items,
        "pair_items": pair_items,
        "items_from_pair_endpoint": len(pair_items_raw),
        "maker_filter_applied": True,
        "maker_like_keys_seen": maker_like_keys_seen(pair_items_raw),
        "debug_pair_rows": [
            {**normalize_maker_trade(item), "maker_like": maker_like_text(item)}
            for item in pair_items_raw[:3]
        ],
        "error": None if response.ok else str(payload)[:500],
        "params": params,
    }


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


def build_maker_trades_text(pair, maker, limit=50):
    safe_limit = min(max(int(limit), 1), 50)
    result = get_birdeye_maker_trades(pair, maker, safe_limit)
    items = result.get("items") or []
    summary = summarize_maker_trades(items)
    classification = classify_maker_behavior(summary)

    lines = [
        "Maker Trades Diagnostic",
        f"Pair: {compact(pair)}",
        f"Maker: {compact(maker)}",
        f"Source used: {result.get('source')}",
        f"Status: {result.get('status')}",
        f"Items returned: {len(items)}",
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
                f"{format_amount(item.get('amount'))} token | "
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
