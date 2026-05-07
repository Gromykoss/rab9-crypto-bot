import requests
from urllib.parse import quote

from config import ARKHAM_API_KEY


ARKHAM_BASE_URL = "https://api.arkm.com"


def arkham_headers():
    return {
        "API-Key": ARKHAM_API_KEY or "",
        "Accept": "application/json",
    }


def arkham_get(path: str, timeout=20):
    if not ARKHAM_API_KEY:
        return {
            "ok": False,
            "status_code": None,
            "data": None,
            "text": "ARKHAM_API_KEY missing",
            "usage": {},
        }

    url = f"{ARKHAM_BASE_URL}{path}"

    try:
        response = requests.get(url, headers=arkham_headers(), timeout=timeout)

        usage = {
            "limit": response.headers.get("x-intel-datapoints-limit"),
            "remaining": response.headers.get("x-intel-datapoints-remaining"),
            "used": response.headers.get("x-intel-datapoints-usage"),
        }

        try:
            data = response.json() if response.text else None
        except ValueError:
            data = None

        return {
            "ok": response.ok,
            "status_code": response.status_code,
            "data": data,
            "text": response.text[:800] if response.text else "",
            "usage": usage,
        }

    except Exception as error:
        return {
            "ok": False,
            "status_code": None,
            "data": None,
            "text": str(error),
            "usage": {},
        }


def get_chains():
    return arkham_get("/chains")


def get_token_intelligence(chain: str, address: str):
    return arkham_get(f"/intelligence/token/{chain}/{address}")


def get_address_intelligence_all(address: str):
    return arkham_get(f"/intelligence/address/{address}/all")


def get_address_flow(address: str, time_last="24h"):
    safe_address = quote(address, safe="")
    safe_time_last = quote(time_last, safe="")
    return arkham_get(f"/flow/address/{safe_address}?timeLast={safe_time_last}")


def get_token_top_flow(chain: str, address: str, time_last="24h"):
    safe_chain = quote(chain, safe="")
    safe_address = quote(address, safe="")
    safe_time_last = quote(time_last, safe="")
    return arkham_get(f"/token/top_flow/{safe_chain}/{safe_address}?timeLast={safe_time_last}")


def format_usage(usage: dict):
    if not usage:
        return "Usage: n/a"

    limit = usage.get("limit") or "n/a"
    remaining = usage.get("remaining") or "n/a"
    used = usage.get("used") or "n/a"

    return f"Usage: used {used}, remaining {remaining}, limit {limit}"


def format_arkham_error(title: str, result: dict, lines: list[str]):
    status = result.get("status_code")
    status_text = f"error {status}" if status is not None else "error"
    response = result.get("text") or "No response body."

    return "\n".join(
        [
            title,
            "",
            *lines,
            f"Status: {status_text}",
            f"Response: {response[:500]}",
            format_usage(result.get("usage") or {}),
        ]
    )


def format_compact_value(value):
    if value is None:
        return "n/a"

    if isinstance(value, float):
        return f"{value:,.2f}"

    if isinstance(value, int):
        return f"{value:,}"

    if isinstance(value, dict):
        for key in ["name", "label", "address", "id", "identifier", "symbol"]:
            if value.get(key):
                return str(value.get(key))

        return str(value)[:80]

    if isinstance(value, list):
        return f"{len(value)} item(s)"

    return str(value)[:80]


def pick_first(data: dict, keys: list[str]):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)

    return None


def format_flow_snapshot(snapshot: dict):
    fields = [
        ("Time", ["time", "timestamp", "date"]),
        ("Inflow USD", ["inflow", "inflowUsd", "inflowUSD", "inflow_usd"]),
        ("Outflow USD", ["outflow", "outflowUsd", "outflowUSD", "outflow_usd"]),
        ("Total Inflow", ["totalInflow", "cumulativeInflow", "total_inflow"]),
        ("Total Outflow", ["totalOutflow", "cumulativeOutflow", "total_outflow"]),
        ("Net Flow", ["netFlow", "netflow", "net", "flow"]),
    ]

    lines = []

    for label, keys in fields:
        value = pick_first(snapshot, keys)

        if value is not None:
            lines.append(f"{label}: {format_compact_value(value)}")

    if lines:
        return "\n".join(lines)

    preview = ", ".join(
        f"{key}: {format_compact_value(value)}"
        for key, value in list(snapshot.items())[:6]
    )

    return preview or "Snapshot: n/a"


def format_generic_flow_record(record: dict):
    preferred_keys = [
        "name",
        "entity",
        "entityName",
        "address",
        "chain",
        "symbol",
        "flow",
        "flowUsd",
        "flowUSD",
        "netFlow",
        "usd",
        "value",
        "volume",
    ]

    lines = []

    for key in preferred_keys:
        if key in record and record.get(key) is not None:
            lines.append(f"{key}: {format_compact_value(record.get(key))}")

    if not lines:
        lines = [
            f"{key}: {format_compact_value(value)}"
            for key, value in list(record.items())[:8]
        ]

    return "\n".join(lines) if lines else "Record: n/a"


TOKEN_FLOW_ADDRESS_KEYS = [
    "address",
    "fromAddress",
    "toAddress",
    "walletAddress",
    "ownerAddress",
    "counterpartyAddress",
]

TOKEN_FLOW_USEFUL_FIELDS = [
    "amount",
    "usdValue",
    "value",
    "inflow",
    "outflow",
    "balanceChange",
    "direction",
    "chain",
    "tokenSymbol",
]

TOKEN_FLOW_INFRASTRUCTURE_TERMS = [
    "jupiter",
    "raydium",
    "meteora",
    "pump",
    "pumpswap",
    "orca",
    "phoenix",
    "openbook",
    "exchange",
    "dex",
    "router",
    "aggregator",
    "bridge",
    "binance",
    "coinbase",
    "okx",
    "bybit",
    "kraken",
]


def get_top_flow_list(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        preferred_list_keys = [
            "data",
            "items",
            "flows",
            "topFlow",
            "topFlows",
            "addresses",
            "results",
        ]

        for key in preferred_list_keys:
            value = data.get(key)
            if isinstance(value, list):
                return value

        for value in data.values():
            if isinstance(value, list):
                return value

    return None


def extract_top_flow_items(data, max_items=10):
    items = get_top_flow_list(data)
    return items[:max_items] if items is not None else []


def get_top_flow_total(data):
    items = get_top_flow_list(data)
    return len(items) if items is not None else None


def get_flow_record_address(record):
    if isinstance(record, str):
        return record

    if not isinstance(record, dict):
        return None

    address = pick_first(record, TOKEN_FLOW_ADDRESS_KEYS)

    if isinstance(address, dict):
        return pick_first(address, TOKEN_FLOW_ADDRESS_KEYS + ["id"])

    return address


def get_chain_intelligence(data, chain: str):
    if not isinstance(data, dict):
        return {}

    chain_data = data.get(chain)
    if isinstance(chain_data, dict):
        return chain_data

    for value in data.values():
        if isinstance(value, dict) and any(
            key in value for key in ["arkhamLabel", "arkhamEntity", "isUserAddress", "program"]
        ):
            return value

    return {}


def entity_name(value):
    if isinstance(value, dict):
        return value.get("name") or ""

    return str(value) if value else ""


def classify_token_flow_address(label_name: str, entity_name_value: str, program):
    if program is True:
        return (
            "Program / Ignore",
            "Do not add to smart-wallet watchlist",
            "programs_ignored",
        )

    text = f"{label_name} {entity_name_value}".lower()

    if any(term in text for term in TOKEN_FLOW_INFRASTRUCTURE_TERMS):
        return (
            "Infrastructure / Ignore",
            "Do not add to smart-wallet watchlist",
            "infrastructure_ignored",
        )

    if label_name or entity_name_value:
        return (
            "Known Entity / Review",
            "Review /wallet first, then optionally /watchwallet",
            "known_entities",
        )

    return (
        "Unknown Candidate / Manual Check",
        "Check /wallet first, then optionally /watchwallet",
        "unknown_candidates",
    )


def format_token_flow_record(record, chain: str, token_address: str):
    flow_address = get_flow_record_address(record)
    flow_address_text = format_compact_value(flow_address) if flow_address else "n/a"

    lines = [f"Address: {flow_address_text}"]
    label_text = ""
    entity_text = ""
    program = "n/a"

    if isinstance(record, dict):
        for key in TOKEN_FLOW_USEFUL_FIELDS:
            if key in record and record.get(key) is not None:
                lines.append(f"{key}: {format_compact_value(record.get(key))}")

    if flow_address:
        lookup = get_address_intelligence_all(str(flow_address))

        if lookup["ok"]:
            chain_data = get_chain_intelligence(lookup.get("data") or {}, chain)
            label = chain_data.get("arkhamLabel") or {}
            entity = chain_data.get("arkhamEntity") or {}
            label_text = entity_name(label)
            entity_text = entity_name(entity)
            program = chain_data.get("program", "n/a")

            lines.extend(
                [
                    f"Arkham Label: {label_text or 'n/a'}",
                    f"Entity: {entity_text or 'n/a'}",
                    f"Is User Address: {chain_data.get('isUserAddress', 'n/a')}",
                    f"Program: {program}",
                ]
            )
        else:
            lines.extend(
                [
                    "Label: lookup failed",
                    "Entity: lookup failed",
                    "Is User Address: n/a",
                    "Program: n/a",
                ]
            )
    else:
        lines.extend(
            [
                "Label: lookup failed",
                "Entity: lookup failed",
                "Is User Address: n/a",
                "Program: n/a",
            ]
        )

    flow_type, action, summary_key = classify_token_flow_address(
        label_text,
        entity_text,
        program,
    )

    lines.extend([f"Type: {flow_type}", f"Action: {action}", f"/wallet {flow_address_text}"])

    if flow_type in ["Known Entity / Review", "Unknown Candidate / Manual Check"]:
        lines.append(f"/watchwallet {flow_address_text} tokenflow:{token_address}")

    return "\n".join(lines), summary_key


def format_enriched_token_flow(data, chain: str, token_address: str, max_items=10):
    items = extract_top_flow_items(data, max_items)
    total_items = get_top_flow_total(data)
    total_text = str(total_items) if total_items is not None else "n/a"
    summary = {
        "infrastructure_ignored": 0,
        "known_entities": 0,
        "unknown_candidates": 0,
        "programs_ignored": 0,
    }

    if not items:
        return "\n".join(
            [
                f"Total items from Arkham: {total_text}",
                "Enriched: first 10 addresses only",
                "",
                "No flow data returned.",
                "",
                "Summary:",
                "- Infrastructure ignored: 0",
                "- Known entities: 0",
                "- Unknown candidates: 0",
                "- Programs ignored: 0",
            ]
        )

    sections = [
        f"Total items from Arkham: {total_text}",
        "Enriched: first 10 addresses only",
    ]

    for idx, item in enumerate(items, start=1):
        record_text, summary_key = format_token_flow_record(item, chain, token_address)
        summary[summary_key] += 1
        sections.append(f"#{idx}\n{record_text}")

    sections.extend(
        [
            "Summary:",
            f"- Infrastructure ignored: {summary['infrastructure_ignored']}",
            f"- Known entities: {summary['known_entities']}",
            f"- Unknown candidates: {summary['unknown_candidates']}",
            f"- Programs ignored: {summary['programs_ignored']}",
        ]
    )

    return "\n\n".join(sections)


def format_flow_collection(data, item_formatter, max_sections=6, max_items=5):
    if isinstance(data, dict):
        sections = []

        for key, value in list(data.items())[:max_sections]:
            if isinstance(value, list):
                sections.append(f"{key}: {len(value)} item(s)")

                for idx, item in enumerate(value[:max_items], start=1):
                    if isinstance(item, dict):
                        sections.append(f"#{idx}\n{item_formatter(item)}")
                    else:
                        sections.append(f"#{idx} {format_compact_value(item)}")

                sections.append("")
            else:
                sections.append(f"{key}: {format_compact_value(value)}")

        return "\n".join(sections).strip() or "No flow data returned."

    if isinstance(data, list):
        if not data:
            return "No flow data returned."

        sections = [f"Items: {len(data)}"]

        for idx, item in enumerate(data[:max_items], start=1):
            if isinstance(item, dict):
                sections.append(f"#{idx}\n{item_formatter(item)}")
            else:
                sections.append(f"#{idx} {format_compact_value(item)}")

        return "\n\n".join(sections)

    return f"Raw response: {format_compact_value(data)}"


def build_arkham_status_text():
    chains = get_chains()

    if not chains["ok"]:
        return (
            "🕵️ Arkham Status\n\n"
            f"ARKHAM_API_KEY: {'loaded' if ARKHAM_API_KEY else 'missing'}\n"
            f"Status: error {chains['status_code']}\n"
            f"Response: {chains['text'][:500]}"
        )

    data = chains["data"]
    chains_text = ", ".join(data[:12]) if isinstance(data, list) else str(data)[:300]

    return (
        "🕵️ Arkham Status\n\n"
        f"ARKHAM_API_KEY: {'loaded' if ARKHAM_API_KEY else 'missing'}\n"
        f"Status: online ({chains['status_code']})\n"
        f"Chains: {chains_text}\n"
        f"{format_usage(chains.get('usage') or {})}"
    )


def build_ark_token_text(chain: str, address: str):
    token = get_token_intelligence(chain, address)
    address_intel = get_address_intelligence_all(address)

    lines = [
        "🕵️ Arkham Token Intel",
        "",
        f"Chain: {chain}",
        f"Address: {address}",
        "",
    ]

    if token["ok"]:
        data = token["data"] or {}
        identifier = data.get("identifier") or {}

        lines.extend(
            [
                "Token Intelligence:",
                f"Name: {data.get('name', 'n/a')}",
                f"Symbol: {data.get('symbol', 'n/a')}",
                f"Pricing ID: {identifier.get('pricingID', 'n/a')}",
                f"Identifier Chain: {identifier.get('chain', 'n/a')}",
                "",
                format_usage(token.get("usage") or {}),
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Token Intelligence:",
                f"Status: error {token['status_code']}",
                f"Response: {token['text'][:400]}",
                "",
            ]
        )

    if address_intel["ok"]:
        data = address_intel["data"] or {}
        chain_data = data.get(chain) or {}

        label = chain_data.get("arkhamLabel") or {}
        entity = chain_data.get("arkhamEntity") or {}

        lines.extend(
            [
                "Address Intelligence:",
                f"Arkham Label: {label.get('name', 'n/a')}",
                f"Entity: {entity.get('name', 'n/a')}",
                f"Is User Address: {chain_data.get('isUserAddress', 'n/a')}",
                f"Program: {chain_data.get('program', 'n/a')}",
                "",
                format_usage(address_intel.get("usage") or {}),
            ]
        )
    else:
        lines.extend(
            [
                "Address Intelligence:",
                f"Status: error {address_intel['status_code']}",
                f"Response: {address_intel['text'][:400]}",
            ]
        )

    return "\n".join(lines)


def build_wallet_flow_text(address: str, time_last="24h"):
    result = get_address_flow(address, time_last)

    title = "🌊 Arkham Wallet Flow"
    context = [
        f"Address: {address}",
        f"TimeLast: {time_last}",
        "Endpoint: /flow/address/{address}",
        "",
    ]

    if not result["ok"]:
        return format_arkham_error(title, result, context)

    data = result["data"]

    lines = [
        title,
        "",
        f"Address: {address}",
        f"TimeLast: {time_last}",
        "Endpoint: /flow/address/{address}",
        "",
        format_flow_collection(data, format_flow_snapshot),
        "",
        format_usage(result.get("usage") or {}),
    ]

    return "\n".join(lines)


def build_token_flow_text(chain: str, address: str, time_last="24h"):
    result = get_token_top_flow(chain, address, time_last)

    title = "🌊 Arkham Token Top Flow"
    context = [
        f"Chain: {chain}",
        f"Address: {address}",
        f"TimeLast: {time_last}",
        "Endpoint: /token/top_flow/{chain}/{address}",
        "",
    ]

    if not result["ok"]:
        return format_arkham_error(title, result, context)

    data = result["data"]

    lines = [
        title,
        "",
        f"Chain: {chain}",
        f"Address: {address}",
        f"TimeLast: {time_last}",
        "Endpoint: /token/top_flow/{chain}/{address}",
        format_usage(result.get("usage") or {}),
        "",
        format_enriched_token_flow(data, chain, address),
    ]

    return "\n".join(lines)


def build_wallet_text(address: str):
    result = get_address_intelligence_all(address)

    if not result["ok"]:
        return (
            "👛 Arkham Wallet / Address Intel\n\n"
            f"Address: {address}\n"
            f"Status: error {result['status_code']}\n"
            f"Response: {result['text'][:500]}"
        )

    data = result["data"] or {}

    if not isinstance(data, dict) or not data:
        return (
            "👛 Arkham Wallet / Address Intel\n\n"
            f"Address: {address}\n"
            "No Arkham intelligence found."
        )

    lines = [
        "👛 Arkham Wallet / Address Intel",
        "",
        f"Address: {address}",
        "",
    ]

    for chain, chain_data in data.items():
        if not isinstance(chain_data, dict):
            continue

        label = chain_data.get("arkhamLabel") or {}
        entity = chain_data.get("arkhamEntity") or {}

        lines.extend(
            [
                f"Chain: {chain}",
                f"Arkham Label: {label.get('name', 'n/a')}",
                f"Entity: {entity.get('name', 'n/a')}",
                f"Is User Address: {chain_data.get('isUserAddress', 'n/a')}",
                f"Program: {chain_data.get('program', 'n/a')}",
                "",
            ]
        )

    lines.append(format_usage(result.get("usage") or {}))

    lines.extend(
        [
            "",
            "Notes:",
            "- Это базовая Arkham-разметка адреса.",
            "- Если Entity/Label пустые, Arkham не знает владельца адреса или не отдаёт его по текущему доступу.",
            "- Для smart-money логики позже добавим watchwallet и checkwallets.",
        ]
    )

    return "\n".join(lines)
