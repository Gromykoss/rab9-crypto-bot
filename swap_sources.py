from collections import Counter
from datetime import datetime, timezone

import requests

from config import BIRDEYE_API_KEY, SOLSCAN_API_KEY


SOLSCAN_BASE_URL = "https://pro-api.solscan.io/v2.0"
BIRDEYE_BASE_URL = "https://public-api.birdeye.so"


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


def normalize_solscan_item(item):
    routers = item.get("routers") if isinstance(item, dict) else None
    router = routers[0] if isinstance(routers, list) and routers else {}

    token_in = token_text(first_value(router, ["token1", "from_token", "input_token"]))
    token_out = token_text(first_value(router, ["token2", "to_token", "output_token"]))
    amount_in = first_value(router, ["amount1", "from_amount", "input_amount"])
    amount_out = first_value(router, ["amount2", "to_amount", "output_amount"])

    return {
        "time": format_time(first_value(item, ["block_time", "time", "timestamp"])),
        "token_in": token_in,
        "amount_in": amount_in,
        "token_out": token_out,
        "amount_out": amount_out,
        "usd_value": first_value(item, ["value", "usd_value", "usdValue", "amount_usd", "volume_usd"]),
        "tx": first_value(item, ["trans_id", "tx_hash", "txHash", "signature", "hash"]),
        "platform": first_value(item, ["platform", "source", "program", "activity_type"]) or "n/a",
    }


def normalize_birdeye_item(item):
    token_in = token_text(first_value(item, ["from", "from_token", "token_in", "base", "sell_token", "source_token"]))
    token_out = token_text(first_value(item, ["to", "to_token", "token_out", "quote", "buy_token", "destination_token"]))

    return {
        "time": format_time(first_value(item, ["block_unix_time", "blockUnixTime", "block_time", "time", "timestamp"])),
        "token_in": token_in,
        "amount_in": first_value(item, ["from_amount", "amount_in", "sell_amount", "base_amount", "fromAmount"]),
        "token_out": token_out,
        "amount_out": first_value(item, ["to_amount", "amount_out", "buy_amount", "quote_amount", "toAmount"]),
        "usd_value": first_value(item, ["volume_usd", "value", "value_usd", "usd_value", "amount_usd"]),
        "tx": first_value(item, ["tx_hash", "txHash", "signature", "tx_id", "hash"]),
        "platform": first_value(item, ["source", "platform", "dex", "amm"]) or "n/a",
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


def request_birdeye_swaps(wallet, token, limit):
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


def pick_swap_source(wallet, token, limit):
    solscan = request_solscan_swaps(wallet, token, limit)
    if solscan["ok"] and solscan["items"]:
        return solscan, [solscan]

    birdeye = request_birdeye_swaps(wallet, token, limit)
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

    return {
        "total": len(items),
        "unique_tokens": len(unique_tokens),
        "total_usd": total_usd if has_usd else None,
        "main_input": input_tokens.most_common(1)[0][0] if input_tokens else "n/a",
        "main_output": output_tokens.most_common(1)[0][0] if output_tokens else "n/a",
    }


def build_wallet_swaps_text(wallet, token=None, limit=20):
    safe_limit = min(max(int(limit), 1), 50)
    token = (token or "").strip() or None
    result, attempts = pick_swap_source(wallet, token, safe_limit)
    items = result.get("items") or []
    summary = build_summary(items)

    lines = [
        "Wallet Swaps Diagnostic",
        f"Wallet: {compact(wallet)}",
        f"Token filter: {compact(token) if token else 'none'}",
        f"Source used: {result.get('source')}",
        f"Status: {result.get('status')}",
        f"Items returned: {len(items)}",
    ]

    if attempts and attempts[0].get("error") == "SOLSCAN_API_KEY missing":
        lines.append("Solscan: SOLSCAN_API_KEY missing")

    if result.get("error") and not items:
        lines.append(f"Error: {result['error']}")

    lines.extend(
        [
            "",
            "Summary:",
            f"- Total swaps: {summary['total']}",
            f"- Unique tokens involved: {summary['unique_tokens']}",
            f"- Total USD value: {format_usd(summary['total_usd'])}",
            f"- Most common input token: {summary['main_input']}",
            f"- Most common output token: {summary['main_output']}",
            "",
            "Events:",
        ]
    )

    visible_items = items[:20]
    if not visible_items:
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
