import os
import json

from config import WATCHLIST_PATH
from utils import (
    utc_now_text,
    format_usd,
    format_percent,
    format_ratio,
    safe_float,
)
from dex import get_dex_token_pairs, pick_best_pair
from scoring import analyze_pair_metrics


def watch_key(chain: str, address: str):
    return f"{chain.lower().strip()}:{address.lower().strip()}"


def load_watchlist():
    if not os.path.exists(WATCHLIST_PATH):
        return []

    try:
        with open(WATCHLIST_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        return []
    except Exception:
        return []


def save_watchlist(items):
    with open(WATCHLIST_PATH, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)


def get_initial_watch_snapshot(chain: str, address: str):
    result = get_dex_token_pairs(chain, address)

    if not result["ok"]:
        return None

    pairs = result["data"]

    if not isinstance(pairs, list) or not pairs:
        return None

    best_pair = pick_best_pair(pairs)

    if not best_pair:
        return None

    metrics = analyze_pair_metrics(best_pair)
    base = best_pair.get("baseToken") or {}

    return {
        "symbol": base.get("symbol", "N/A"),
        "name": base.get("name", "Unknown"),
        "priceUsd": best_pair.get("priceUsd"),
        "marketCap": metrics.get("marketCap"),
        "liquidityUsd": metrics.get("liquidityUsd"),
        "volume24h": metrics.get("volume24h"),
        "score": metrics.get("score"),
        "risk": metrics.get("risk"),
        "rating": metrics.get("rating"),
        "url": best_pair.get("url"),
        "first_seen_at": utc_now_text(),
    }


def format_delta_percent(current, initial):
    current = safe_float(current, None)
    initial = safe_float(initial, None)

    if current is None or initial is None or initial == 0:
        return "n/a"

    delta = ((current - initial) / initial) * 100
    sign = "+" if delta >= 0 else ""

    return f"{sign}{delta:.1f}%"


def format_delta_points(current, initial):
    current = safe_float(current, None)
    initial = safe_float(initial, None)

    if current is None or initial is None:
        return "n/a"

    delta = current - initial
    sign = "+" if delta >= 0 else ""

    return f"{sign}{delta:.0f}"


def add_to_watchlist(chain: str, address: str, note: str = ""):
    items = load_watchlist()
    key = watch_key(chain, address)
    snapshot = get_initial_watch_snapshot(chain, address)

    for item in items:
        if watch_key(item.get("chain", ""), item.get("address", "")) == key:
            item["note"] = note or item.get("note", "")
            item["updated_at"] = utc_now_text()

            if snapshot:
                if not item.get("first_snapshot"):
                    item["first_snapshot"] = snapshot
                item["last_snapshot"] = snapshot

            save_watchlist(items)
            return "updated", item

    new_item = {
        "chain": chain.lower().strip(),
        "address": address.strip(),
        "note": note.strip(),
        "added_at": utc_now_text(),
        "updated_at": utc_now_text(),
        "first_snapshot": snapshot,
        "last_snapshot": snapshot,
    }

    items.append(new_item)
    save_watchlist(items)

    return "added", new_item


def remove_from_watchlist(address: str):
    items = load_watchlist()
    target = address.lower().strip()

    kept = []
    removed = []

    for item in items:
        if item.get("address", "").lower().strip() == target:
            removed.append(item)
        else:
            kept.append(item)

    save_watchlist(kept)

    return removed


def refresh_watchlist_snapshots():
    items = load_watchlist()

    if not items:
        return "📋 Watchlist пуст."

    updated = 0
    failed = 0

    for item in items:
        chain = item.get("chain")
        address = item.get("address")

        if not chain or not address:
            failed += 1
            continue

        snapshot = get_initial_watch_snapshot(chain, address)

        if not snapshot:
            failed += 1
            continue

        if not item.get("first_snapshot"):
            item["first_snapshot"] = snapshot

        item["last_snapshot"] = snapshot
        item["updated_at"] = utc_now_text()

        updated += 1

    save_watchlist(items)

    return (
        "♻️ Watchlist snapshots refreshed\n\n"
        f"Updated: {updated}\n"
        f"Failed: {failed}\n\n"
        "Теперь проверь:\n"
        "/watchlist\n"
        "/checkwatch"
    )


def format_watchlist_text():
    items = load_watchlist()

    if not items:
        return "📋 Watchlist пуст.\n\nДобавить:\n/watch solana ADDRESS заметка"

    lines = [f"📋 Watchlist: {len(items)} токен(ов)\n"]

    for idx, item in enumerate(items, start=1):
        note = item.get("note") or "без заметки"
        first = item.get("first_snapshot") or {}

        symbol = first.get("symbol", "N/A")
        first_mc = first.get("marketCap")
        first_liq = first.get("liquidityUsd")
        first_score = first.get("score")
        first_risk = first.get("risk")
        first_seen = first.get("first_seen_at") or item.get("added_at")

        lines.append(
            f"#{idx} {symbol}\n"
            f"Chain: {item.get('chain')}\n"
            f"Address: {item.get('address')}\n"
            f"Note: {note}\n\n"
            f"First Seen:\n"
            f"MC: {format_usd(first_mc)}\n"
            f"Liquidity: {format_usd(first_liq)}\n"
            f"Score: {first_score if first_score is not None else 'n/a'}\n"
            f"Risk: {first_risk or 'n/a'}\n"
            f"At: {first_seen}\n\n"
            f"Analyze: /token {item.get('chain')} {item.get('address')}\n"
            f"Remove: /unwatch {item.get('address')}"
        )

    return "\n\n".join(lines)


def build_watch_check_text() -> str:
    items = load_watchlist()

    if not items:
        return "📋 Watchlist пуст. Добавить:\n/watch solana ADDRESS заметка"

    lines = [f"🔁 Watchlist Check\nItems: {len(items)}\n"]

    for idx, item in enumerate(items, start=1):
        chain = item.get("chain")
        address = item.get("address")
        note = item.get("note") or "без заметки"

        result = get_dex_token_pairs(chain, address)

        if not result["ok"]:
            lines.append(
                f"#{idx} {chain} {address[:6]}...{address[-6:]}\n"
                f"Status: Dexscreener error {result['status_code']}\n"
                f"Note: {note}"
            )
            continue

        pairs = result["data"]

        if not isinstance(pairs, list) or not pairs:
            lines.append(
                f"#{idx} {chain} {address[:6]}...{address[-6:]}\n"
                f"Status: no pairs found\n"
                f"Note: {note}"
            )
            continue

        best_pair = pick_best_pair(pairs)

        if not best_pair:
            lines.append(
                f"#{idx} {chain} {address[:6]}...{address[-6:]}\n"
                f"Status: no best pair\n"
                f"Note: {note}"
            )
            continue

        metrics = analyze_pair_metrics(best_pair)
        base = best_pair.get("baseToken") or {}
        volume = best_pair.get("volume") or {}
        price_change = best_pair.get("priceChange") or {}

        first = item.get("first_snapshot") or {}

        first_mc = first.get("marketCap")
        first_liq = first.get("liquidityUsd")
        first_score = first.get("score")

        current_mc = metrics.get("marketCap")
        current_liq = metrics.get("liquidityUsd")
        current_score = metrics.get("score")

        lines.append(
            f"#{idx} {base.get('symbol', 'N/A')} | {chain}\n"
            f"Note: {note}\n\n"
            f"Since Added:\n"
            f"MC: {format_usd(first_mc)} → {format_usd(current_mc)} ({format_delta_percent(current_mc, first_mc)})\n"
            f"Liquidity: {format_usd(first_liq)} → {format_usd(current_liq)} ({format_delta_percent(current_liq, first_liq)})\n"
            f"Score: {first_score if first_score is not None else 'n/a'} → {current_score} ({format_delta_points(current_score, first_score)})\n\n"
            f"Current:\n"
            f"Risk: {metrics.get('risk')}\n"
            f"Signal: {metrics.get('rating')}\n"
            f"Vol24h: {format_usd(metrics.get('volume24h'))}\n"
            f"Price 1h: {format_percent(price_change.get('h1'))}\n"
            f"Price 24h: {format_percent(price_change.get('h24'))}\n"
            f"Sell/Buy24h: {format_ratio(metrics.get('sellBuyRatio24h'))}\n"
            f"Vol1h: {format_usd(volume.get('h1'))}\n\n"
            f"Analyze: /token {chain} {address}\n"
            f"{best_pair.get('url')}"
        )

    return "\n\n".join(lines)
