import requests

from config import BIRDEYE_API_KEY, DEXSCREENER_BASE_URL
from swap_sources import compact, extract_items, first_value, format_usd


BIRDEYE_BASE_URL = "https://public-api.birdeye.so"
CHAIN = "solana"


def safe_get(url, headers=None, params=None, timeout=20):
    try:
        response = requests.get(url, headers=headers or {}, params=params or {}, timeout=timeout)
    except requests.RequestException as exc:
        return {"ok": False, "status": "request_error", "data": None, "error": str(exc)}

    try:
        data = response.json() if response.text else None
    except ValueError:
        data = None

    return {
        "ok": response.ok,
        "status": response.status_code,
        "data": data,
        "error": None if response.ok else (response.text or "")[:300],
    }


def value_at(record, path):
    current = record
    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def as_list(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []

    for key in ("pairs", "items", "markets", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return value

    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("pairs", "items", "markets", "list"):
            value = data.get(key)
            if isinstance(value, list):
                return value

    return extract_items(payload)


def token_label(value):
    if isinstance(value, dict):
        symbol = value.get("symbol") or value.get("name") or value.get("token_symbol") or value.get("tokenSymbol")
        address = value.get("address") or value.get("mint") or value.get("token_address") or value.get("tokenAddress")
        if symbol and address:
            return f"{symbol}/{compact(address)}"
        return symbol or address or "n/a"
    return str(value) if value else "n/a"


def normalize_dex_pair(item):
    liquidity = item.get("liquidity") if isinstance(item.get("liquidity"), dict) else {}
    volume = item.get("volume") if isinstance(item.get("volume"), dict) else {}

    return {
        "pair": item.get("pairAddress") or item.get("pair_address") or item.get("address") or "n/a",
        "dex": item.get("dexId") or item.get("dex") or "n/a",
        "chain": item.get("chainId") or item.get("chain") or "n/a",
        "base": token_label(item.get("baseToken")),
        "quote": token_label(item.get("quoteToken")),
        "liquidity": liquidity.get("usd"),
        "volume24h": volume.get("h24") or volume.get("24h") or item.get("volume24h"),
    }


def normalize_birdeye_market(item, source):
    base = first_value(item, ["base", "baseToken", "base_token", "token0", "token0Info"])
    quote = first_value(item, ["quote", "quoteToken", "quote_token", "token1", "token1Info"])

    return {
        "market": (
            item.get("address")
            or item.get("marketAddress")
            or item.get("market_address")
            or item.get("pool_id")
            or item.get("poolId")
            or item.get("poolAddress")
            or item.get("lpAddress")
            or "n/a"
        ),
        "source": source,
        "base": token_label(base),
        "quote": token_label(quote),
        "liquidity": (
            item.get("liquidity")
            or item.get("liquidity_usd")
            or item.get("liquidityUsd")
            or value_at(item, ["liquidity", "usd"])
        ),
        "volume24h": (
            item.get("volume24h")
            or item.get("volume_24h")
            or item.get("volume24hUsd")
            or item.get("volume_24h_usd")
            or value_at(item, ["volume", "h24"])
        ),
    }


def unique_by_address(items, key):
    result = []
    seen = set()
    for item in items:
        address = item.get(key)
        marker = str(address).lower() if address else f"missing-{len(result)}"
        if marker in seen:
            continue
        seen.add(marker)
        result.append(item)
    return result


def get_dexscreener_candidates(address):
    candidates = []
    token_result = safe_get(f"{DEXSCREENER_BASE_URL}/token-pairs/v1/{CHAIN}/{address}")
    pair_result = safe_get(f"{DEXSCREENER_BASE_URL}/latest/dex/pairs/{CHAIN}/{address}")

    for item in as_list(token_result.get("data")):
        if isinstance(item, dict):
            candidates.append(normalize_dex_pair(item))

    for item in as_list(pair_result.get("data")):
        if isinstance(item, dict):
            candidates.append(normalize_dex_pair(item))

    return {
        "candidates": unique_by_address(candidates, "pair")[:10],
        "token_status": token_result.get("status"),
        "pair_status": pair_result.get("status"),
    }


def birdeye_headers():
    return {"accept": "application/json", "X-API-KEY": BIRDEYE_API_KEY or "", "x-chain": CHAIN}


def get_birdeye_candidates(address):
    if not BIRDEYE_API_KEY:
        return {"candidates": [], "statuses": ["BIRDEYE_API_KEY missing"], "error": "BIRDEYE_API_KEY missing"}

    candidates = []
    statuses = []

    market_result = safe_get(
        f"{BIRDEYE_BASE_URL}/defi/v2/markets",
        headers=birdeye_headers(),
        params={"address": address, "offset": 0, "limit": 10, "sort_by": "liquidity", "sort_type": "desc"},
    )
    statuses.append(f"markets:{market_result.get('status')}")
    for item in as_list(market_result.get("data")):
        if isinstance(item, dict):
            candidates.append(normalize_birdeye_market(item, "markets"))

    search_result = safe_get(
        f"{BIRDEYE_BASE_URL}/defi/v3/search",
        headers=birdeye_headers(),
        params={"keyword": address, "target": "all", "search_mode": "exact", "sort_by": "volume_24h_usd", "sort_type": "desc"},
    )
    statuses.append(f"search:{search_result.get('status')}")
    for item in as_list(search_result.get("data")):
        if isinstance(item, dict):
            candidates.append(normalize_birdeye_market(item, "search"))

    overview_result = safe_get(
        f"{BIRDEYE_BASE_URL}/defi/v3/pair/overview/single",
        headers=birdeye_headers(),
        params={"address": address},
    )
    statuses.append(f"pair_overview:{overview_result.get('status')}")
    overview_data = overview_result.get("data")
    if isinstance(overview_data, dict):
        data = overview_data.get("data") if isinstance(overview_data.get("data"), dict) else overview_data
        if isinstance(data, dict):
            candidates.append(normalize_birdeye_market(data, "pair_overview"))

    return {"candidates": unique_by_address(candidates, "market")[:10], "statuses": statuses, "error": None}


def format_candidate_line(idx, item, kind):
    if kind == "dex":
        return (
            f"#{idx} pair: {compact(item.get('pair'))} | "
            f"dex: {item.get('dex') or 'n/a'} | "
            f"chain: {item.get('chain') or 'n/a'} | "
            f"base/quote: {item.get('base') or 'n/a'}/{item.get('quote') or 'n/a'} | "
            f"liq: {format_usd(item.get('liquidity'))} | "
            f"vol24h: {format_usd(item.get('volume24h'))}"
        )

    return (
        f"#{idx} market/pool: {compact(item.get('market'))} | "
        f"source: {item.get('source') or 'n/a'} | "
        f"base/quote: {item.get('base') or 'n/a'}/{item.get('quote') or 'n/a'} | "
        f"liq: {format_usd(item.get('liquidity'))} | "
        f"vol24h: {format_usd(item.get('volume24h'))}"
    )


def build_pair_resolve_text(address):
    dex = get_dexscreener_candidates(address)
    birdeye = get_birdeye_candidates(address)
    dex_candidates = dex.get("candidates") or []
    birdeye_candidates = birdeye.get("candidates") or []
    recommendation = next((item.get("market") for item in birdeye_candidates if item.get("market") and item.get("market") != "n/a"), None)
    # Fallback: use DexScreener pair if Birdeye returned nothing
    if recommendation is None:
        recommendation = next((item.get("pair") for item in dex_candidates if item.get("pair") and item.get("pair") != "n/a"), None)

    lines = [
        "Pair Resolve Diagnostic",
        f"Input: {compact(address)}",
        "",
        "Dexscreener candidates:",
    ]

    if dex_candidates:
        for idx, item in enumerate(dex_candidates[:5], start=1):
            lines.append(format_candidate_line(idx, item, "dex"))
    else:
        lines.append("No Dexscreener candidates found.")

    lines.extend(["", "Birdeye candidates:"])
    if birdeye_candidates:
        for idx, item in enumerate(birdeye_candidates[:5], start=1):
            lines.append(format_candidate_line(idx, item, "birdeye"))
    else:
        if birdeye.get("error"):
            lines.append(f"No Birdeye candidates found. {birdeye['error']}")
        else:
            lines.append("No Birdeye candidates found.")

    lines.extend(
        [
            "",
            "Recommendation:",
        ]
    )

    if recommendation:
        lines.append(f"- Use this address for /makertrades: {recommendation}")
    else:
        lines.append("- Birdeye pair address unresolved; /makertrades may need Solscan/Bitquery source.")

    lines.extend(
        [
            "",
            "Sources checked:",
            f"- Dexscreener token-pairs status: {dex.get('token_status')}",
            f"- Dexscreener pair status: {dex.get('pair_status')}",
            f"- Birdeye statuses: {', '.join(birdeye.get('statuses') or ['n/a'])}",
            "",
            "Notes:",
            "- No PnL calculated.",
            "- No trading advice.",
            "- Manual diagnostic only.",
        ]
    )

    return "\n".join(lines)
