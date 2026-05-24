import hashlib
import os
import sqlite3
from datetime import datetime, timezone

from config import RAB9_DB_ENABLED, RAB9_DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS pairs (
    pair_address TEXT PRIMARY KEY,
    token_symbol TEXT,
    quote_symbol TEXT,
    dex TEXT,
    liquidity_usd REAL,
    volume24h_usd REAL,
    market_cap_usd REAL,
    fdv_usd REAL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    trade_count INTEGER NOT NULL DEFAULT 0,
    oldest_trade_unix INTEGER,
    last_trade_unix INTEGER
);

CREATE TABLE IF NOT EXISTS pair_trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_address TEXT NOT NULL,
    dedupe_key TEXT NOT NULL,
    tx_hash TEXT,
    maker TEXT,
    side TEXT,
    trade_time TEXT,
    trade_unix INTEGER,
    token_in TEXT,
    token_out TEXT,
    amount TEXT,
    usd_value REAL,
    page INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(dedupe_key),
    FOREIGN KEY(pair_address) REFERENCES pairs(pair_address)
);

CREATE INDEX IF NOT EXISTS idx_pair_trades_pair_time
ON pair_trades(pair_address, trade_unix);

CREATE TABLE IF NOT EXISTS pair_scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pair_address TEXT NOT NULL,
    trigger TEXT,
    mode TEXT,
    pages_fetched INTEGER NOT NULL DEFAULT 0,
    trades_fetched INTEGER NOT NULL DEFAULT 0,
    trades_inserted INTEGER NOT NULL DEFAULT 0,
    trades_skipped INTEGER NOT NULL DEFAULT 0,
    status TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    FOREIGN KEY(pair_address) REFERENCES pairs(pair_address)
);

CREATE INDEX IF NOT EXISTS idx_pair_scan_runs_pair_finished
ON pair_scan_runs(pair_address, finished_at);
"""


def utc_now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(path=None):
    db_path = path or RAB9_DB_PATH
    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def ensure_schema(conn):
    conn.executescript(SCHEMA)


def to_float(value):
    try:
        return float(value) if value is not None and value != "n/a" else None
    except (TypeError, ValueError):
        return None


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def trade_unix_from_text(value):
    text = str(value or "").strip()
    if not text or text == "n/a":
        return None

    try:
        number = float(text)
    except ValueError:
        normalized = f"{text[:-1]}+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp())

    return int(number / 1000) if number > 10_000_000_000 else int(number)


def normalized_text(value):
    text = str(value or "").strip()
    return text if text else "n/a"


def build_dedupe_key(pair_address, item):
    pair = normalized_text(pair_address).lower()
    tx_hash = normalized_text(item.get("tx")).lower()
    maker = normalized_text(item.get("maker")).lower()
    side = normalized_text(item.get("side")).upper()

    if tx_hash != "n/a" and maker != "n/a" and side != "N/A":
        raw_key = "|".join(["tx", pair, tx_hash, maker, side])
    else:
        raw_key = "|".join(
            [
                "fallback",
                pair,
                normalized_text(item.get("time")),
                maker,
                side,
                normalized_text(item.get("amount")),
                normalized_text(item.get("usd_value")),
            ]
        )

    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def upsert_pair(conn, pair_address, metadata, inserted_count, trade_unixes, now):
    oldest_trade_unix = min(trade_unixes) if trade_unixes else None
    last_trade_unix = max(trade_unixes) if trade_unixes else None
    conn.execute(
        """
        INSERT INTO pairs (
            pair_address, token_symbol, quote_symbol, dex, liquidity_usd, volume24h_usd,
            market_cap_usd, fdv_usd, first_seen_at, last_seen_at, trade_count,
            oldest_trade_unix, last_trade_unix
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(pair_address) DO UPDATE SET
            token_symbol = COALESCE(excluded.token_symbol, pairs.token_symbol),
            quote_symbol = COALESCE(excluded.quote_symbol, pairs.quote_symbol),
            dex = COALESCE(excluded.dex, pairs.dex),
            liquidity_usd = COALESCE(excluded.liquidity_usd, pairs.liquidity_usd),
            volume24h_usd = COALESCE(excluded.volume24h_usd, pairs.volume24h_usd),
            market_cap_usd = COALESCE(excluded.market_cap_usd, pairs.market_cap_usd),
            fdv_usd = COALESCE(excluded.fdv_usd, pairs.fdv_usd),
            last_seen_at = excluded.last_seen_at,
            trade_count = pairs.trade_count + excluded.trade_count,
            oldest_trade_unix = CASE
                WHEN pairs.oldest_trade_unix IS NULL THEN excluded.oldest_trade_unix
                WHEN excluded.oldest_trade_unix IS NULL THEN pairs.oldest_trade_unix
                WHEN excluded.oldest_trade_unix < pairs.oldest_trade_unix THEN excluded.oldest_trade_unix
                ELSE pairs.oldest_trade_unix
            END,
            last_trade_unix = CASE
                WHEN pairs.last_trade_unix IS NULL THEN excluded.last_trade_unix
                WHEN excluded.last_trade_unix IS NULL THEN pairs.last_trade_unix
                WHEN excluded.last_trade_unix > pairs.last_trade_unix THEN excluded.last_trade_unix
                ELSE pairs.last_trade_unix
            END
        """,
        (
            pair_address,
            metadata.get("token_symbol"),
            metadata.get("quote_symbol"),
            metadata.get("dex"),
            to_float(metadata.get("liquidity_usd")),
            to_float(metadata.get("volume24h_usd")),
            to_float(metadata.get("market_cap_usd")),
            to_float(metadata.get("fdv_usd")),
            now,
            now,
            inserted_count,
            oldest_trade_unix,
            last_trade_unix,
        ),
    )


def insert_scan_run(conn, pair_address, scan_run, inserted_count, skipped_count):
    conn.execute(
        """
        INSERT INTO pair_scan_runs (
            pair_address, trigger, mode, pages_fetched, trades_fetched,
            trades_inserted, trades_skipped, status, started_at, finished_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            pair_address,
            scan_run.get("trigger"),
            scan_run.get("mode"),
            int(scan_run.get("pages_fetched") or 0),
            int(scan_run.get("trades_fetched") or 0),
            inserted_count,
            skipped_count,
            str(scan_run.get("status") or "n/a"),
            scan_run.get("started_at"),
            scan_run.get("finished_at"),
        ),
    )


def persist_pair_scan(pair_address, metadata, trades, scan_run, path=None):
    if not RAB9_DB_ENABLED:
        return {"enabled": False, "inserted": 0, "skipped": 0, "total": len(trades or [])}

    now = utc_now()
    items = list(trades or [])
    started_at = scan_run.get("started_at") or now
    finished_at = scan_run.get("finished_at") or now
    scan_run = {**scan_run, "started_at": started_at, "finished_at": finished_at}

    with connect(path) as conn:
        ensure_schema(conn)

        rows = []
        trade_unixes = []
        for item in items:
            trade_unix = trade_unix_from_text(item.get("time"))
            if trade_unix is not None:
                trade_unixes.append(trade_unix)
            rows.append(
                (
                    pair_address,
                    build_dedupe_key(pair_address, item),
                    None if normalized_text(item.get("tx")) == "n/a" else normalized_text(item.get("tx")),
                    None if normalized_text(item.get("maker")) == "n/a" else normalized_text(item.get("maker")),
                    None if normalized_text(item.get("side")) == "n/a" else normalized_text(item.get("side")),
                    None if normalized_text(item.get("time")) == "n/a" else normalized_text(item.get("time")),
                    trade_unix,
                    None if normalized_text(item.get("token_in")) == "n/a" else normalized_text(item.get("token_in")),
                    None if normalized_text(item.get("token_out")) == "n/a" else normalized_text(item.get("token_out")),
                    None if normalized_text(item.get("amount")) == "n/a" else normalized_text(item.get("amount")),
                    to_float(item.get("usd_value")),
                    to_int(item.get("page")),
                    now,
                )
            )

        upsert_pair(conn, pair_address, metadata or {}, 0, [], now)
        before_changes = conn.total_changes
        conn.executemany(
            """
            INSERT OR IGNORE INTO pair_trades (
                pair_address, dedupe_key, tx_hash, maker, side, trade_time, trade_unix,
                token_in, token_out, amount, usd_value, page, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        inserted_count = conn.total_changes - before_changes
        skipped_count = len(rows) - inserted_count
        upsert_pair(conn, pair_address, metadata or {}, inserted_count, trade_unixes, now)
        insert_scan_run(conn, pair_address, scan_run, inserted_count, skipped_count)

    return {"enabled": True, "inserted": inserted_count, "skipped": skipped_count, "total": len(rows)}
