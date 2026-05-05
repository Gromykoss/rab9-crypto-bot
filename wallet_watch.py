import os
import json

from utils import utc_now_text
from arkham import get_address_intelligence_all, format_usage


WALLET_WATCHLIST_PATH = "/root/rab9/wallet_watchlist.json"


def wallet_key(address: str):
    return address.lower().strip()


def load_wallet_watchlist():
    if not os.path.exists(WALLET_WATCHLIST_PATH):
        return []

    try:
        with open(WALLET_WATCHLIST_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, list):
            return data

        return []
    except Exception:
        return []


def save_wallet_watchlist(items):
    with open(WALLET_WATCHLIST_PATH, "w", encoding="utf-8") as file:
        json.dump(items, file, ensure_ascii=False, indent=2)


def get_wallet_snapshot(address: str):
    result = get_address_intelligence_all(address)

    if not result["ok"]:
        return None

    data = result["data"] or {}

    if not isinstance(data, dict) or not data:
        return None

    chains = []

    for chain, chain_data in data.items():
        if not isinstance(chain_data, dict):
            continue

        label = chain_data.get("arkhamLabel") or {}
        entity = chain_data.get("arkhamEntity") or {}

        chains.append(
            {
                "chain": chain,
                "label": label.get("name"),
                "entity": entity.get("name"),
                "isUserAddress": chain_data.get("isUserAddress"),
                "program": chain_data.get("program"),
            }
        )

    return {
        "address": address,
        "chains": chains,
        "checked_at": utc_now_text(),
        "usage": result.get("usage") or {},
    }


def add_wallet_to_watchlist(address: str, note: str = ""):
    items = load_wallet_watchlist()
    key = wallet_key(address)
    snapshot = get_wallet_snapshot(address)

    for item in items:
        if wallet_key(item.get("address", "")) == key:
            item["note"] = note or item.get("note", "")
            item["updated_at"] = utc_now_text()

            if snapshot:
                if not item.get("first_snapshot"):
                    item["first_snapshot"] = snapshot
                item["last_snapshot"] = snapshot

            save_wallet_watchlist(items)
            return "updated", item

    new_item = {
        "address": address.strip(),
        "note": note.strip(),
        "added_at": utc_now_text(),
        "updated_at": utc_now_text(),
        "first_snapshot": snapshot,
        "last_snapshot": snapshot,
    }

    items.append(new_item)
    save_wallet_watchlist(items)

    return "added", new_item


def remove_wallet_from_watchlist(address_or_index: str):
    items = load_wallet_watchlist()
    target = str(address_or_index).strip()

    removed = []

    # Delete by number from /walletlist: /unwatchwallet 1
    if target.isdigit():
        index = int(target) - 1

        if 0 <= index < len(items):
            removed_item = items[index]
            kept = items[:index] + items[index + 1:]
            save_wallet_watchlist(kept)
            return [removed_item]

        return []

    # Delete by full address: /unwatchwallet ADDRESS
    target_key = wallet_key(target)
    kept = []

    for item in items:
        if wallet_key(item.get("address", "")) == target_key:
            removed.append(item)
        else:
            kept.append(item)

    save_wallet_watchlist(kept)
    return removed


def format_wallet_snapshot(snapshot: dict):
    if not snapshot:
        return "No Arkham snapshot."

    chains = snapshot.get("chains") or []

    if not chains:
        return "No Arkham chains found."

    lines = []

    for item in chains:
        lines.extend(
            [
                f"Chain: {item.get('chain')}",
                f"Label: {item.get('label') or 'n/a'}",
                f"Entity: {item.get('entity') or 'n/a'}",
                f"Is User Address: {item.get('isUserAddress', 'n/a')}",
                f"Program: {item.get('program', 'n/a')}",
                "",
            ]
        )

    lines.append(f"Checked: {snapshot.get('checked_at', 'n/a')}")
    lines.append(format_usage(snapshot.get("usage") or {}))

    return "\n".join(lines)


def format_walletlist_text():
    items = load_wallet_watchlist()

    if not items:
        return "👛 Wallet watchlist пуст.\n\nДобавить:\n/watchwallet ADDRESS заметка"

    lines = [f"👛 Wallet Watchlist: {len(items)} адрес(ов)\n"]

    for idx, item in enumerate(items, start=1):
        address = item.get("address")
        note = item.get("note") or "без заметки"
        first = item.get("first_snapshot") or {}

        chains = first.get("chains") or []
        first_label = "n/a"
        first_entity = "n/a"
        first_chain = "n/a"

        if chains:
            first_chain = chains[0].get("chain") or "n/a"
            first_label = chains[0].get("label") or "n/a"
            first_entity = chains[0].get("entity") or "n/a"

        lines.append(
            f"#{idx}\n"
            f"Address: {address}\n"
            f"Note: {note}\n"
            f"First Chain: {first_chain}\n"
            f"First Label: {first_label}\n"
            f"First Entity: {first_entity}\n"
            f"Added: {item.get('added_at')}\n\n"
            f"Check: /wallet {address}\n"
            f"Remove: /unwatchwallet {idx}\n"
            f"Remove by address: /unwatchwallet {address}"
        )

    return "\n\n".join(lines)


def build_checkwallets_text():
    items = load_wallet_watchlist()

    if not items:
        return "👛 Wallet watchlist пуст.\n\nДобавить:\n/watchwallet ADDRESS заметка"

    lines = [f"🔁 Wallet Watch Check\nItems: {len(items)}\n"]

    updated = 0
    failed = 0

    for idx, item in enumerate(items, start=1):
        address = item.get("address")
        note = item.get("note") or "без заметки"

        snapshot = get_wallet_snapshot(address)

        if not snapshot:
            failed += 1
            lines.append(
                f"#{idx}\n"
                f"Address: {address}\n"
                f"Note: {note}\n"
                f"Status: no Arkham data or request failed"
            )
            continue

        if not item.get("first_snapshot"):
            item["first_snapshot"] = snapshot

        item["last_snapshot"] = snapshot
        item["updated_at"] = utc_now_text()
        updated += 1

        lines.append(
            f"#{idx}\n"
            f"Address: {address}\n"
            f"Note: {note}\n\n"
            f"{format_wallet_snapshot(snapshot)}"
        )

    save_wallet_watchlist(items)

    lines.append("")
    lines.append(f"Updated: {updated}")
    lines.append(f"Failed: {failed}")

    return "\n\n".join(lines)
