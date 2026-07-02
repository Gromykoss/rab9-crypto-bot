"""
RAB9 Wallet Intelligence — cross-reference engine.
Answers: "Which wallets on this token have we seen before on winners?"
"""

import sqlite3
from config import RAB9_DB_ENABLED, RAB9_DB_PATH

# Pre-computed from 22-token historical analysis (June 2026).
# Wallets that appeared on 3+ successful tokens (GACHA, CUM, SOLANGELES — all MC > $1M).
# These represent automated market-making infrastructure, not insider "cabals".
CABAL_WALLETS = {
    "JD6rVaerbyz6wj": 2374,  # most active on winners
    "AgmLJBMDCqWynY": 1793,
    "2QfBNK2WDwSLoU": 823,
    "GxDC9e7SP9mzhD": 619,
    "8L2y55D11k63CA": 489,
    "SHARKRdGLNYRZr": 434,
    "MRiYA4oN3158fC": 278,
    "DsCJ5siuJTPQtQ": 546,
    "8TPWakvWw4xQbk": 456,
    "ARu4n5mFdZogZA": 414,
}

# Thresholds: a wallet must appear on >= this many tokens to be "infrastructure"
INFRA_TOKEN_THRESHOLD = 8  # appeared on 8+ tokens = likely bot/MEV
CABAL_TOKEN_MIN = 2        # appeared on 2+ winners = potential signal
CABAL_TRADE_MIN = 20        # minimum trades to be considered


def load_cabal_library():
    """Load wallet intelligence from the trade database."""
    if not RAB9_DB_ENABLED:
        return {}

    conn = sqlite3.connect(RAB9_DB_PATH)
    conn.row_factory = sqlite3.Row

    # Winner tokens: MC > $500K
    winner_addrs = [
        row["pair_address"]
        for row in conn.execute(
            "SELECT pair_address FROM pairs WHERE market_cap_usd > 500000"
        ).fetchall()
    ]

    if not winner_addrs:
        conn.close()
        return {}

    placeholders = ",".join(["?"] * len(winner_addrs))

    # Get all wallets with their total token count
    all_token_counts = {}
    for row in conn.execute(
        "SELECT maker, COUNT(DISTINCT pair_address) as cnt FROM pair_trades "
        "WHERE maker != '' GROUP BY maker"
    ).fetchall():
        all_token_counts[row["maker"]] = row["cnt"]

    # Get wallets on winner tokens
    rows = conn.execute(
        f"""
        SELECT t.maker, COUNT(DISTINCT t.pair_address) as winner_count,
               COUNT(*) as total_trades
        FROM pair_trades t
        WHERE t.maker != '' AND t.maker IS NOT NULL
          AND t.pair_address IN ({placeholders})
        GROUP BY t.maker
        HAVING winner_count >= ?
        ORDER BY winner_count DESC, total_trades DESC
        """,
        winner_addrs + [CABAL_TOKEN_MIN],
    ).fetchall()

    conn.close()

    cabals = {}
    for row in rows:
        maker = row["maker"]
        all_tokens = all_token_counts.get(maker, 0)
        is_infra = all_tokens >= INFRA_TOKEN_THRESHOLD
        cabals[maker] = {
            "winner_count": row["winner_count"],
            "total_trades": row["total_trades"],
            "all_tokens": all_tokens,
            "is_infrastructure": is_infra,
            "signal_strength": "infrastructure" if is_infra else
                              "strong" if row["winner_count"] >= 3 and row["total_trades"] >= CABAL_TRADE_MIN
                              else "moderate" if row["total_trades"] >= CABAL_TRADE_MIN
                              else "weak",
        }
    return cabals


def cross_reference_makers(makers, cabal_library=None):
    """
    Given a list of maker dicts (from maker_sources.summarize_pair_makers),
    check which ones are known from winner tokens.

    Args:
        makers: list of dicts with 'maker' key
        cabal_library: pre-loaded dict from load_cabal_library()

    Returns:
        dict with 'known', 'cabal', 'infrastructure' lists
    """
    if cabal_library is None:
        cabal_library = load_cabal_library() if RAB9_DB_ENABLED else {}

    if not cabal_library:
        return {"known": [], "cabal": [], "infrastructure": [], "summary": ""}

    known = []
    cabal = []
    infra = []

    for m in makers:
        # summarize_pair_makers returns "wallet" key, not "maker"
        addr = m.get("wallet", "") or m.get("maker", "")
        if addr in cabal_library:
            info = cabal_library[addr]
            entry = {**m, "intel": info}
            if info["is_infrastructure"]:
                infra.append(entry)
            else:
                cabal.append(entry)
            known.append(entry)

    # Build summary
    lines = []
    if cabal:
        lines.append(f"🎯 Кабалы ({len(cabal)}):")
        for c in cabal[:5]:
            lines.append(f"  • {c['wallet'][:8]}... — {c['intel']['winner_count']} winner tokens, {c['intel']['total_trades']} trades ({c['intel']['signal_strength']})")

    if infra:
        lines.append(f"🤖 Инфраструктура ({len(infra)}):")
        if len(infra) <= 3:
            for i in infra[:3]:
                lines.append(f"  • {i['wallet'][:8]}... — {i['intel']['all_tokens']} tokens (MEV/bot)")
        else:
            lines.append(f"  {len(infra)} кошельков (MEV/bot) — типично для ликвидных пар")

    summary = "\n".join(lines) if lines else ""

    return {
        "known": known,
        "cabal": cabal,
        "infrastructure": infra,
        "summary": summary,
        "has_signal": len(cabal) > 0,
        "cabal_count": len(cabal),
    }


def delta_compare(new_makers, pair_address):
    """
    Compare current scan makers against historical data for the same pair.

    Returns delta report: new wallets, gone wallets, behavior changes.
    """
    if not RAB9_DB_ENABLED:
        return {"has_history": False}

    conn = sqlite3.connect(RAB9_DB_PATH)
    conn.row_factory = sqlite3.Row

    # Get historical makers for this pair
    hist = conn.execute(
        """
        SELECT maker, COUNT(*) as trades,
               SUM(CASE WHEN side='buy' THEN 1 ELSE 0 END) as buys,
               SUM(CASE WHEN side='sell' THEN 1 ELSE 0 END) as sells,
               MIN(trade_time) as first_seen, MAX(trade_time) as last_seen
        FROM pair_trades
        WHERE pair_address = ?
        GROUP BY maker
        ORDER BY trades DESC
        """,
        [pair_address],
    ).fetchall()

    conn.close()

    if not hist:
        return {"has_history": False, "summary": "📝 Первый скан для этого токена."}

    old_makers = {row["maker"]: dict(row) for row in hist}
    new_maker_addrs = {m.get("wallet", "") or m.get("maker", "") for m in new_makers}

    # Find wallets present in both, only in old, only in new
    stayed = [a for a in old_makers if a in new_maker_addrs]
    gone = [a for a in old_makers if a not in new_maker_addrs]
    arrived = [a for a in new_maker_addrs if a not in old_makers]

    # Top changed wallets
    changes = []
    for addr in stayed[:5]:
        old = old_makers[addr]
        new = next((m for m in new_makers if (m.get("wallet", "") or m.get("maker", "")) == addr), {})
        old_net = old["buys"] - old["sells"]
        changes.append(
            f"  • {addr[:8]}... — {old['trades']} trades historically, now active"
        )

    lines = []
    lines.append(f"📊 Исторический скан: {len(old_makers)} кошельков")
    if arrived:
        lines.append(f"🆕 Новые: {len(arrived)}")
    if gone:
        lines.append(f"👋 Ушли: {len(gone)}")
    if stayed:
        lines.append(f"🔄 Остались: {len(stayed)}")
    if changes:
        lines.append("Активные из истории:")
        lines.extend(changes)

    return {
        "has_history": True,
        "old_count": len(old_makers),
        "new_count": len(new_makers),
        "stayed": len(stayed),
        "gone": len(gone),
        "arrived": len(arrived),
        "summary": "\n".join(lines),
        "fresh_scan": len(arrived) > len(stayed),
    }


def auto_escalation_check(maker_count, cabal_count, buy_ratio, concentration):
    """
    Determine if scan should auto-escalate to deep/deep50.

    Returns: (should_escalate: bool, reason: str, level: str)
    """
    triggers = []

    if cabal_count >= 3:
        triggers.append(("deep", f"{cabal_count} кабалов в топе"))
    if maker_count >= 50 and concentration > 0.5:
        triggers.append(("deep", f"концентрация топ-5 > 50%"))
    if buy_ratio > 2.0 and maker_count >= 20:
        triggers.append(("deep", f"buy/sell > {buy_ratio:.1f}x"))
    if cabal_count >= 5:
        triggers.append(("deep50", f"{cabal_count} кабалов — deep50"))

    if not triggers:
        return False, "", "normal"

    best = max(triggers, key=lambda t: 0 if t[0] == "normal" else 1 if t[0] == "deep" else 2)
    return True, best[1], best[0]
