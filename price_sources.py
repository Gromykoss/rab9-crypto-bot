from datetime import datetime, timezone

import requests

from config import BIRDEYE_API_KEY


BIRDEYE_BASE_URL = "https://public-api.birdeye.so"
BIRDEYE_CHAIN = "solana"


def _compact(value: str, left: int = 6, right: int = 4) -> str:
    if not value:
        return "n/a"

    text = str(value)
    if len(text) <= left + right + 3:
        return text

    return f"{text[:left]}...{text[-right:]}"


def _parse_iso_timestamp(timestamp: str):
    raw = (timestamp or "").strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _iso_from_unix(value):
    if value is None:
        return "n/a"

    try:
        ts = int(float(value))
    except (TypeError, ValueError):
        return str(value)

    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_birdeye(path: str, params: dict):
    url = f"{BIRDEYE_BASE_URL}{path}"
    headers = {
        "accept": "application/json",
        "X-API-KEY": BIRDEYE_API_KEY,
        "x-chain": BIRDEYE_CHAIN,
    }

    try:
        response = requests.get(url, headers=headers, params=params, timeout=20)
    except requests.RequestException as exc:
        return {
            "ok": False,
            "endpoint": path,
            "status_code": "request_error",
            "error": str(exc),
            "data": None,
        }

    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text[:500]}

    return {
        "ok": response.ok,
        "endpoint": path,
        "status_code": response.status_code,
        "error": None if response.ok else str(data)[:500],
        "data": data,
    }


def _extract_items(payload):
    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("items", "list", "points"):
            value = data.get(key)
            if isinstance(value, list):
                return value

        if any(key in data for key in ("o", "h", "l", "c", "unixTime", "time", "value", "price")):
            return [data]

    if isinstance(data, list):
        return data

    return []


def _item_time(item):
    for key in ("unixTime", "time", "timestamp", "t"):
        if key in item:
            try:
                return int(float(item[key]))
            except (TypeError, ValueError):
                return None

    return None


def _nearest_item(items, target_ts):
    best = None
    best_distance = None

    for item in items:
        if not isinstance(item, dict):
            continue

        item_ts = _item_time(item)
        if item_ts is None:
            continue

        distance = abs(item_ts - target_ts)
        if best_distance is None or distance < best_distance:
            best = item
            best_distance = distance

    return best, best_distance


def _field(item, *keys):
    if not isinstance(item, dict):
        return None

    for key in keys:
        if key in item and item[key] is not None:
            return item[key]

    return None


def _to_float(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _build_report(token: str, requested_iso: str, result: dict):
    available_keys = result.get("available_keys") or []

    lines = [
        "🧪 Price Source Diagnostic",
        f"Token: {_compact(token)}",
        f"Timestamp requested: {requested_iso}",
        f"Source: {result.get('source') or 'n/a'}",
        f"Endpoint: {result.get('endpoint') or 'n/a'}",
        f"Status: {result.get('status_code')}",
    ]

    if result.get("error") and not result.get("ok"):
        lines.append(f"Error: {result['error']}")

    lines.extend(
        [
            "",
            "Result:",
            f"Price near timestamp: {result.get('price') if result.get('price') is not None else 'n/a'}",
            f"Candle time: {result.get('time') or 'n/a'}",
            f"Distance from requested: {result.get('distance') if result.get('distance') is not None else 'n/a'} sec",
            f"Open: {result.get('open') if result.get('open') is not None else 'n/a'}",
            f"High: {result.get('high') if result.get('high') is not None else 'n/a'}",
            f"Low: {result.get('low') if result.get('low') is not None else 'n/a'}",
            f"Close: {result.get('close') if result.get('close') is not None else 'n/a'}",
            f"Raw fields count: {result.get('raw_fields_count', 0)}",
            f"Available keys: {', '.join(available_keys) if available_keys else 'n/a'}",
            "",
            "No PnL calculated.",
        ]
    )

    return "\n".join(lines)


def get_birdeye_price_near(token: str, timestamp: str) -> dict:
    token = (token or "").strip()
    timestamp = (timestamp or "").strip()

    if not BIRDEYE_API_KEY:
        return {
            "ok": False,
            "skipped": True,
            "error": "BIRDEYE_API_KEY missing.",
            "price": None,
            "time": "n/a",
            "source": "Birdeye",
            "endpoint": "n/a",
            "status_code": None,
        }

    requested = _parse_iso_timestamp(timestamp)
    if requested is None:
        return {
            "ok": False,
            "skipped": False,
            "error": "Invalid timestamp.",
            "price": None,
            "time": "n/a",
            "source": "Birdeye",
            "endpoint": "n/a",
            "status_code": None,
        }

    requested_ts = int(requested.timestamp())
    params = {
        "address": token,
        "address_type": "token",
        "type": "1m",
        "time_from": requested_ts - 3600,
        "time_to": requested_ts + 3600,
    }

    ohlcv = _request_birdeye("/defi/ohlcv", params)
    items = _extract_items(ohlcv.get("data"))
    nearest, distance = _nearest_item(items, requested_ts)
    source = "Birdeye /defi/ohlcv"
    result = ohlcv

    if nearest is None:
        history = _request_birdeye("/defi/history_price", params)
        items = _extract_items(history.get("data"))
        nearest, distance = _nearest_item(items, requested_ts)
        source = "Birdeye /defi/history_price"
        result = history

    price = _to_float(_field(nearest, "c", "close", "value", "price"))
    available_keys = sorted(nearest.keys()) if isinstance(nearest, dict) else []

    if nearest is None or price is None:
        return {
            "ok": False,
            "skipped": False,
            "error": result.get("error") or "price unavailable",
            "price": None,
            "time": "n/a",
            "source": source,
            "endpoint": result.get("endpoint"),
            "status_code": result.get("status_code"),
            "distance": distance,
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "raw_fields_count": len(available_keys),
            "available_keys": available_keys,
        }

    candle_time = _field(nearest, "unixTime", "time", "timestamp", "t")

    return {
        "ok": True,
        "skipped": False,
        "error": None,
        "price": price,
        "time": _iso_from_unix(candle_time),
        "distance": distance,
        "source": source,
        "endpoint": result.get("endpoint"),
        "status_code": result.get("status_code"),
        "open": _to_float(_field(nearest, "o", "open")),
        "high": _to_float(_field(nearest, "h", "high")),
        "low": _to_float(_field(nearest, "l", "low")),
        "close": _to_float(_field(nearest, "c", "close", "value", "price")),
        "raw_fields_count": len(available_keys),
        "available_keys": available_keys,
    }


def build_price_source_text(token: str, timestamp: str) -> str:
    token = (token or "").strip()
    timestamp = (timestamp or "").strip()

    if not BIRDEYE_API_KEY:
        return "BIRDEYE_API_KEY missing."

    requested = _parse_iso_timestamp(timestamp)
    if requested is None:
        return "Invalid timestamp. Use ISO format, example: 2026-05-07T18:45:29Z"

    requested_iso = requested.replace(microsecond=0).isoformat().replace("+00:00", "Z")

    result = get_birdeye_price_near(token, timestamp)

    return _build_report(token, requested_iso, result)
