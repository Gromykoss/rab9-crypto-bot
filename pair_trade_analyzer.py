import logging

from maker_sources import summarize_pair_makers
from trade_db import fetch_pair_meta, fetch_pair_trades


logger = logging.getLogger(__name__)


def cached_row_to_item(row):
    return {
        "maker": row["maker"],
        "side": row["side"],
        "time": row["trade_time"],
        "usd_value": row["usd_value"],
        "amount": row["amount"],
        "token_in": row["token_in"],
        "token_out": row["token_out"],
        "page": row["page"],
        "tx": row["tx_hash"],
    }


def behavior_counts(makers):
    return {
        "buy_heavy": len([row for row in makers if row["net_direction"] == "buy-heavy"]),
        "sell_heavy": len([row for row in makers if row["net_direction"] == "sell-heavy"]),
        "mixed": len([row for row in makers if row["net_direction"] == "mixed"]),
        "weak": len([row for row in makers if row["trades"] < 3]),
    }


def weak_ratio(buckets, unique_makers):
    return buckets["weak"] / unique_makers if unique_makers else 1.0


def analyze_window(name, rows):
    items = [cached_row_to_item(row) for row in rows if row["maker"]]
    makers = summarize_pair_makers(items)
    buckets = behavior_counts(makers)
    unique_makers = len(makers)
    return {
        "name": name,
        "stored_trades": len(rows),
        "items": items,
        "makers": makers,
        "unique_makers": unique_makers,
        "buckets": buckets,
        "weak_ratio": weak_ratio(buckets, unique_makers),
        "top5": makers[:5],
    }


def top5_overlap(left, right):
    left_wallets = {row["wallet"] for row in left.get("top5") or []}
    right_wallets = {row["wallet"] for row in right.get("top5") or []}
    return len(left_wallets & right_wallets)


def format_window(summary):
    buckets = summary["buckets"]
    return (
        f"- {summary['name']}: makers {summary['unique_makers']} | "
        f"B/S/M {buckets['buy_heavy']}/{buckets['sell_heavy']}/{buckets['mixed']} | "
        f"weak {summary['weak_ratio']:.0%}"
    )


def build_cache_windows_summary(pair_address):
    meta = fetch_pair_meta(pair_address)
    if meta is None:
        return None

    last_1k = analyze_window("1k", fetch_pair_trades(pair_address, limit=1000))
    last_10k = analyze_window("10k", fetch_pair_trades(pair_address, limit=10000))
    all_rows = fetch_pair_trades(pair_address)
    all_stored = analyze_window("all", all_rows)

    if not all_stored["stored_trades"]:
        return None

    return {
        "stored": meta["trade_count"] if meta["trade_count"] is not None else all_stored["stored_trades"],
        "last_1k": last_1k,
        "last_10k": last_10k,
        "all": all_stored,
        "top5_overlap_1k_10k": top5_overlap(last_1k, last_10k),
    }


def format_cache_windows_block(summary):
    if not summary:
        return []

    one = summary["last_1k"]
    ten = summary["last_10k"]
    all_stored = summary["all"]
    weak_delta = ten["weak_ratio"] - one["weak_ratio"]
    if weak_delta >= 0.05:
        weak_trend = "recent 1k is cleaner than wider history"
    elif weak_delta <= -0.05:
        weak_trend = "wider history is cleaner than recent 1k"
    else:
        weak_trend = "weak ratio stable across windows"

    return [
        "Cache windows:",
        f"- Stored: {summary['stored']} trades",
        format_window(one),
        format_window(ten),
        format_window(all_stored),
        (
            f"- Trend: {weak_trend}; weak {one['weak_ratio']:.0%} -> {ten['weak_ratio']:.0%}; "
            f"top5 overlap {summary['top5_overlap_1k_10k']}/5"
        ),
        "",
    ]


def build_cache_windows_block(pair_address):
    try:
        return format_cache_windows_block(build_cache_windows_summary(pair_address))
    except Exception:
        logger.exception("Failed to build cache windows block for pair %s", pair_address)
        return []
