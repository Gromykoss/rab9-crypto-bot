import logging

from config import RAB9_DB_ENABLED
from trade_db import persist_pair_scan, utc_now


logger = logging.getLogger(__name__)


def symbol_from_label(label):
    text = str(label or "").strip()
    if not text or text == "n/a":
        return None
    return text.split("/", 1)[0].strip() or None


def pair_metadata(candidate, resolved):
    return {
        "token_symbol": symbol_from_label(candidate.get("base")),
        "quote_symbol": symbol_from_label(candidate.get("quote")),
        "dex": candidate.get("dex") or candidate.get("source") or resolved.get("source"),
        "liquidity_usd": candidate.get("liquidity"),
        "volume24h_usd": candidate.get("volume24h"),
        "market_cap_usd": candidate.get("marketCap"),
        "fdv_usd": candidate.get("fdv"),
    }


def persist_final_msf_scan(pair, candidate, resolved, final_scan, trigger="msf"):
    if not RAB9_DB_ENABLED:
        return {"enabled": False, "inserted": 0, "skipped": 0, "total": 0}

    try:
        maker_result = final_scan.get("maker_result") or {}
        items = maker_result.get("items") or []
        now = utc_now()
        return persist_pair_scan(
            pair_address=pair,
            metadata=pair_metadata(candidate or {}, resolved or {}),
            trades=items,
            scan_run={
                "trigger": trigger,
                "mode": maker_result.get("mode") or final_scan.get("mode"),
                "pages_fetched": maker_result.get("pages_scanned") or 0,
                "trades_fetched": maker_result.get("raw_pair_trades_scanned") or len(items),
                "status": maker_result.get("status"),
                "started_at": now,
                "finished_at": now,
            },
        )
    except Exception:
        logger.exception("Failed to persist MSF final scan for pair %s", pair)
        return {"enabled": True, "inserted": 0, "skipped": len((final_scan.get("maker_result") or {}).get("items") or []), "error": True}
