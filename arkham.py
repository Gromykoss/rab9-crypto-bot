import requests
from datetime import datetime, timezone
from urllib.parse import quote, urlencode

from config import ARKHAM_API_KEY
from price_sources import get_birdeye_price_near


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


def get_wallet_token_transfers(wallet: str, token: str, chain="solana", limit=25):
    safe_limit = min(max(int(limit), 1), 50)
    params = {
        "base": wallet,
        "chains": chain,
        "flow": "all",
        "tokens": token,
        "sortKey": "time",
        "sortDir": "desc",
        "limit": str(safe_limit),
        "offset": "0",
    }
    endpoint = f"/transfers?{urlencode(params)}"
    result = arkham_get(endpoint)
    result["endpoint"] = endpoint
    return result


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


def pick_nested(data: dict, keys: list[str]):
    for key in keys:
        value = data.get(key)

        if isinstance(value, dict):
            for nested_key in ["address", "id", "hash", "symbol", "name"]:
                if value.get(nested_key):
                    return value.get(nested_key)

        if value is not None:
            return value

    return None


def pick_first(data: dict, keys: list[str]):
    for key in keys:
        if key in data and data.get(key) is not None:
            return data.get(key)

    return None


def extract_transfer_items(data):
    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in ["transfers", "items", "data", "results"]:
            value = data.get(key)
            if isinstance(value, list):
                return value

    return []


def transfer_direction(item: dict, wallet: str):
    from_address = str(pick_nested(item, ["from", "fromAddress", "from_address"]) or "").lower()
    to_address = str(pick_nested(item, ["to", "toAddress", "to_address"]) or "").lower()
    wallet_lower = wallet.lower()

    if to_address == wallet_lower:
        return "Token IN / possible buy"

    if from_address == wallet_lower:
        return "Token OUT / possible sell"

    return "Other transfer"


def transfer_counterparty(item: dict, wallet: str):
    direction = transfer_direction(item, wallet)

    if direction == "Token IN / possible buy":
        return pick_nested(item, ["from", "fromAddress", "from_address", "fromLabel"])

    if direction == "Token OUT / possible sell":
        return pick_nested(item, ["to", "toAddress", "to_address", "toLabel"])

    return None


def transfer_timestamp(item: dict):
    return pick_first(item, ["timestamp", "time", "blockTimestamp", "block_time", "datetime"])


def compact_identifier(value, head=6, tail=4):
    if value is None:
        return "n/a"

    text = str(value)

    if len(text) <= head + tail + 3:
        return text

    return f"{text[:head]}...{text[-tail:]}"


def transfer_direction_short(item: dict, wallet: str):
    direction = transfer_direction(item, wallet)

    if direction == "Token IN / possible buy":
        return "IN"

    if direction == "Token OUT / possible sell":
        return "OUT"

    return "OTHER"


def format_wallet_transfer_item(item, wallet: str):
    if not isinstance(item, dict):
        return f"Raw: {compact_identifier(item)}"

    parts = [
        str(transfer_timestamp(item) or "n/a"),
        transfer_direction_short(item, wallet),
        f"CP: {compact_identifier(transfer_counterparty(item, wallet))}",
        f"tx: {compact_identifier(pick_first(item, ['txHash', 'transactionHash', 'hash', 'txid', 'txId']))}",
    ]

    return " | ".join(parts)


def summarize_wallet_transfer_items(items: list, wallet: str):
    token_in_count = 0
    token_out_count = 0
    timestamps = []
    counterparty_counts = {}

    for item in items:
        if not isinstance(item, dict):
            continue

        direction = transfer_direction(item, wallet)

        if direction == "Token IN / possible buy":
            token_in_count += 1
        elif direction == "Token OUT / possible sell":
            token_out_count += 1

        timestamp = transfer_timestamp(item)
        if timestamp is not None:
            timestamps.append(str(timestamp))

        counterparty = transfer_counterparty(item, wallet)
        if counterparty:
            counterparty_text = str(counterparty)
            counterparty_counts[counterparty_text] = counterparty_counts.get(counterparty_text, 0) + 1

    sorted_times = sorted(timestamps)
    unique_counterparties = len(counterparty_counts)
    main_counterparty = None

    if counterparty_counts:
        candidate, count = max(counterparty_counts.items(), key=lambda entry: entry[1])

        if count >= 2 and count > len(items) / 2:
            main_counterparty = f"{compact_identifier(candidate)} ({count}/{len(items)})"

    return {
        "total": len(items),
        "token_in": token_in_count,
        "token_out": token_out_count,
        "first_time": sorted_times[0] if sorted_times else "n/a",
        "last_time": sorted_times[-1] if sorted_times else "n/a",
        "unique_counterparties": unique_counterparties,
        "main_counterparty": main_counterparty,
        "main_counterparty_count": max(counterparty_counts.values()) if counterparty_counts else 0,
    }


def get_events_chrono(items: list):
    if all(isinstance(item, dict) and transfer_timestamp(item) is not None for item in items):
        return sorted(items, key=lambda item: str(transfer_timestamp(item)))

    return list(reversed(items))


def build_potential_trade_cycles(events_chrono: list, wallet: str):
    cycles = []
    current = None
    seen = set()

    for item in events_chrono:
        if not isinstance(item, dict):
            continue

        direction = transfer_direction_short(item, wallet)
        timestamp = transfer_timestamp(item) or "n/a"

        if direction == "IN":
            if current and current["out_count"] > 0:
                key = (
                    current["in_first"],
                    current["out_first"],
                    current["in_count"],
                    current["out_count"],
                )

                if key not in seen:
                    cycles.append(current)
                    seen.add(key)

                current = None

            if not current:
                current = {
                    "in_first": timestamp,
                    "out_first": "n/a",
                    "in_count": 0,
                    "out_count": 0,
                }

            current["in_count"] += 1
        elif direction == "OUT" and current:
            if current["out_count"] == 0:
                current["out_first"] = timestamp

            current["out_count"] += 1

    if current:
        key = (
            current["in_first"],
            current["out_first"],
            current["in_count"],
            current["out_count"],
        )

        if key not in seen:
            cycles.append(current)

    return cycles


def parse_transfer_time(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        timestamp = value / 1000 if value > 10_000_000_000 else value
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    text = str(value)

    if text.isdigit():
        timestamp = int(text)
        timestamp = timestamp / 1000 if timestamp > 10_000_000_000 else timestamp
        return datetime.fromtimestamp(timestamp, tz=timezone.utc)

    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def format_duration(start, end):
    start_dt = parse_transfer_time(start)
    end_dt = parse_transfer_time(end)

    if not start_dt or not end_dt or end_dt < start_dt:
        return "n/a"

    seconds = int((end_dt - start_dt).total_seconds())
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)

    if days:
        return f"{days}d {hours}h"

    if hours:
        return f"{hours}h {minutes}m"

    return f"{minutes}m"


def summarize_cycles(cycles: list):
    completed = [
        cycle
        for cycle in cycles
        if cycle.get("in_count", 0) > 0 and cycle.get("out_count", 0) > 0
    ]
    durations = []

    for cycle in completed:
        start_dt = parse_transfer_time(cycle.get("in_first"))
        end_dt = parse_transfer_time(cycle.get("out_first"))

        if start_dt and end_dt and end_dt >= start_dt:
            durations.append((end_dt - start_dt).total_seconds())

    if durations:
        avg_seconds = sum(durations) / len(durations)
        shortest_seconds = min(durations)
        longest_seconds = max(durations)
        base = datetime.fromtimestamp(0, tz=timezone.utc)

        avg_duration = format_duration(base, datetime.fromtimestamp(avg_seconds, tz=timezone.utc))
        shortest_duration = format_duration(base, datetime.fromtimestamp(shortest_seconds, tz=timezone.utc))
        longest_duration = format_duration(base, datetime.fromtimestamp(longest_seconds, tz=timezone.utc))
    else:
        avg_duration = "n/a"
        shortest_duration = "n/a"
        longest_duration = "n/a"

    return {
        "total": len(cycles),
        "completed": len(completed),
        "avg_duration": avg_duration,
        "shortest": shortest_duration,
        "longest": longest_duration,
    }


def classify_wallet_trade_behavior(summary: dict, cycle_summary: dict):
    total = summary["total"]
    token_in = summary["token_in"]
    token_out = summary["token_out"]
    main_count = summary.get("main_counterparty_count", 0)

    if total and main_count / total > 0.7:
        return "Pool-centric trading pattern"

    if total < 3:
        return "Insufficient Data"

    if token_in >= 3 and token_out >= 3 and cycle_summary["total"] >= 3:
        return "Active Trading Wallet"

    if token_in > 0 and token_out == 0:
        return "Accumulation / Holder"

    if token_out > 0 and token_in == 0:
        return "Distribution Only"

    return "Mixed / Needs Review"


def interpret_wallet_trade_behavior(classification: str, summary: dict, cycle_summary: dict, price_summary=None):
    cycle_text = (
        "Repeated IN/OUT cycles are visible."
        if cycle_summary["completed"] > 1
        else "Repeated IN/OUT cycles are not clearly visible."
    )

    if classification == "Active Trading Wallet":
        activity = "The wallet shows active token movement with multiple IN and OUT events."
    elif classification == "Accumulation / Holder":
        activity = "The wallet mostly accumulated or received tokens without observed OUT events."
    elif classification == "Distribution Only":
        activity = "The wallet only shows outgoing token movement in the returned data."
    elif classification == "Pool-centric trading pattern":
        activity = "Most events involve one dominant counterparty, suggesting a pool-centric transfer pattern."
    elif classification == "Insufficient Data":
        activity = "There are too few returned events to describe behavior confidently."
    else:
        activity = "The wallet has mixed token movement that needs deeper price-action context."

    cycles_priced = (price_summary or {}).get("cycles_priced")
    price_skipped = (price_summary or {}).get("skipped")

    if cycles_priced and cycles_priced > 0:
        next_step = "Historical price was available for selected cycles, so approximate cycle price movement is included above."
    elif price_skipped:
        next_step = "Historical price analysis was skipped because Birdeye key is missing."
    elif cycles_priced == 0:
        next_step = "Historical price was attempted but unavailable for selected cycles."
    elif summary["token_in"] and summary["token_out"]:
        next_step = "It is suitable for future price-action analysis when matching historical candles are available."
    else:
        next_step = "It has limited value for price-action analysis until more matching transfers are found."

    return "\n".join([activity, cycle_text, next_step])


def format_percent(value):
    if value is None:
        return "n/a"

    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f}%"


def format_price(value):
    if value is None:
        return "n/a"

    if value >= 1:
        return f"{value:.6f}".rstrip("0").rstrip(".")

    return f"{value:.12f}".rstrip("0").rstrip(".")


def has_price(result: dict):
    return bool(result.get("ok")) and result.get("price") is not None


def format_cycle_price(result: dict):
    if has_price(result):
        return format_price(result["price"])

    return "price unavailable"


def build_cycle_price_movement_section(cycles: list, token: str, max_cycles=5):
    completed = [
        cycle
        for cycle in cycles
        if cycle.get("in_count", 0) > 0
        and cycle.get("out_count", 0) > 0
        and cycle.get("in_first") != "n/a"
        and cycle.get("out_first") != "n/a"
    ]

    lines = ["Price Movement by Cycle:"]

    if not completed:
        lines.append("No completed cycles available for price movement.")
        return {"lines": lines, "cycles_priced": 0, "skipped": False}

    priced_moves = []
    analysis_cycles = completed[-max_cycles:]
    first_price = get_birdeye_price_near(token, analysis_cycles[0]["in_first"])

    if first_price.get("skipped"):
        lines.append("Price analysis skipped: BIRDEYE_API_KEY missing.")
        return {"lines": lines, "cycles_priced": 0, "skipped": True}

    in_price_cache = {analysis_cycles[0]["in_first"]: first_price}
    price_cache = {}

    for idx, cycle in enumerate(analysis_cycles, start=1):
        in_time = cycle["in_first"]
        out_time = cycle["out_first"]

        if in_time in in_price_cache:
            in_price = in_price_cache[in_time]
        else:
            in_price = price_cache.get(in_time)
            if in_price is None:
                in_price = get_birdeye_price_near(token, in_time)
                price_cache[in_time] = in_price

        out_price = price_cache.get(out_time)
        if out_price is None:
            out_price = get_birdeye_price_near(token, out_time)
            price_cache[out_time] = out_price

        if not has_price(in_price) or not has_price(out_price):
            lines.append(
                f"#{idx} IN: {in_time} / {format_cycle_price(in_price)} | "
                f"OUT: {out_time} / {format_cycle_price(out_price)} | Move: n/a"
            )
            continue

        move = ((out_price["price"] - in_price["price"]) / in_price["price"]) * 100
        priced_moves.append(move)
        lines.append(
            f"#{idx} IN: {in_time} / {format_price(in_price['price'])} | "
            f"OUT: {out_time} / {format_price(out_price['price'])} | "
            f"Move: {format_percent(move)}"
        )

    if len(completed) > max_cycles:
        lines.append("Analyzed latest 5 completed cycles only")

    lines.extend(["", "Cycle Price Movement Summary:"])
    lines.append(f"- Cycles priced: {len(priced_moves)}")
    lines.append(f"- Positive moves: {sum(1 for move in priced_moves if move > 0)}")
    lines.append(f"- Negative moves: {sum(1 for move in priced_moves if move < 0)}")

    if priced_moves:
        avg_move = sum(priced_moves) / len(priced_moves)
        lines.append(f"- Avg move: {format_percent(avg_move)}")
        lines.append(f"- Best move: {format_percent(max(priced_moves))}")
        lines.append(f"- Worst move: {format_percent(min(priced_moves))}")
    else:
        lines.append("- Avg move: n/a")
        lines.append("- Best move: n/a")
        lines.append("- Worst move: n/a")

    return {"lines": lines, "cycles_priced": len(priced_moves), "skipped": False}


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


def build_wallet_tx_text(wallet: str, token: str, limit=25):
    safe_limit = min(max(int(limit), 1), 50)
    result = get_wallet_token_transfers(wallet, token, limit=safe_limit)
    endpoint = result.get("endpoint") or "/transfers"
    title = "🧪 Arkham Wallet Token Transfers Diagnostic"

    context = [
        f"Wallet: {wallet}",
        f"Token: {token}",
        "Endpoint: Arkham /transfers",
    ]

    if not result["ok"]:
        return format_arkham_error(title, result, context)

    data = result.get("data")
    items = extract_transfer_items(data)

    lines = [
        title,
        "",
        f"Wallet: {wallet}",
        f"Token: {token}",
        "Endpoint: Arkham /transfers",
        f"Status: ok ({result.get('status_code')})",
        format_usage(result.get("usage") or {}),
        f"Limit: {safe_limit}",
        "",
    ]

    summary = summarize_wallet_transfer_items(items, wallet)
    summary_lines = [
        "Summary:",
        f"- Total events returned: {summary['total']}",
        f"- Token IN count: {summary['token_in']}",
        f"- Token OUT count: {summary['token_out']}",
        f"- First event time: {summary['first_time']}",
        f"- Last event time: {summary['last_time']}",
        f"- Unique counterparties count: {summary['unique_counterparties']}",
        f"- Main counterparty: {summary['main_counterparty'] or 'n/a'}",
    ]

    lines.extend(summary_lines)

    if not items:
        lines.extend(
            [
                "",
                "No transfer items returned.",
                "This may mean Arkham has no matching wallet/token transfers, or /transfers needs different filters for this asset.",
            ]
        )
        return "\n".join(lines)

    visible_items = items[:20]
    events_chrono = get_events_chrono(items)
    cycles = build_potential_trade_cycles(events_chrono, wallet)
    visible_cycles = cycles[:10]

    lines.extend(
        [
            "",
            "Potential cycles:",
        ]
    )

    if cycles:
        for idx, cycle in enumerate(visible_cycles, start=1):
            lines.append(
                f"#{idx} IN first: {cycle['in_first']} | OUT first: {cycle['out_first']} | "
                f"IN: {cycle['in_count']} | OUT: {cycle['out_count']}"
            )

        if len(cycles) > 10:
            lines.append("Showing first 10 cycles only")
    else:
        lines.append("No IN-led cycles detected in returned events.")

    lines.extend(["", "Showing first 20 events only", "Events:"])

    for idx, item in enumerate(visible_items, start=1):
        lines.append(f"#{idx} {format_wallet_transfer_item(item, wallet)}")

    return "\n".join(lines)


def build_wallet_trade_text(wallet: str, token: str):
    result = get_wallet_token_transfers(wallet, token, limit=50)
    title = "🧠 Wallet Trade Pattern"

    context = [
        f"Wallet: {wallet}",
        f"Token: {token}",
        "Endpoint: Arkham /transfers",
    ]

    if not result["ok"]:
        return format_arkham_error(title, result, context)

    items = extract_transfer_items(result.get("data"))
    events_chrono = get_events_chrono(items)
    summary = summarize_wallet_transfer_items(items, wallet)
    cycles = build_potential_trade_cycles(events_chrono, wallet)
    cycle_summary = summarize_cycles(cycles)
    classification = classify_wallet_trade_behavior(summary, cycle_summary)
    price_section = build_cycle_price_movement_section(cycles, token)

    active_period = (
        f"{summary['first_time']} -> {summary['last_time']}"
        if summary["first_time"] != "n/a" or summary["last_time"] != "n/a"
        else "n/a"
    )
    main_counterparty = summary["main_counterparty"] or "n/a"

    lines = [
        title,
        f"Wallet: {compact_identifier(wallet)}",
        f"Token: {compact_identifier(token)}",
        f"Status: ok ({result.get('status_code')})",
        format_usage(result.get("usage") or {}),
        "",
        "Activity Summary:",
        f"- Events analyzed: {summary['total']}",
        f"- Token IN count: {summary['token_in']}",
        f"- Token OUT count: {summary['token_out']}",
        f"- Active period: {active_period}",
        f"- Unique counterparties: {summary['unique_counterparties']}",
        f"- Main counterparty: {main_counterparty}",
        "",
        "Cycle Summary:",
        f"- Potential cycles count: {cycle_summary['total']}",
        f"- Completed cycles count: {cycle_summary['completed']}",
        f"- Avg cycle duration: {cycle_summary['avg_duration']}",
        f"- Shortest cycle: {cycle_summary['shortest']}",
        f"- Longest cycle: {cycle_summary['longest']}",
        "",
        *price_section["lines"],
        "",
        "Behavior Classification:",
        classification,
        "",
        "Interpretation:",
        interpret_wallet_trade_behavior(classification, summary, cycle_summary, price_section),
        "",
        "Limitations:",
        "- No amount/usdValue in Arkham transfer response.",
        "- Cycle price movement is approximate and uses Birdeye close near first IN/OUT timestamps.",
        "- Amount-based returns and exit quality are not calculated.",
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
