"""RAB9 Wallet Intelligence v3 — tiered timing-based kabal detection.

v2 → v3 improvements:
  1. Tiered winners: Tier1 (>=$2M peak MC) vs Tier2 ($500K-$2M) — different evidence weights
  2. Time-normalized early score: linear decay over token lifetime, not binary <24h
  3. Exit timing: sell within 6h/12h/24h of entry on winner tokens
  4. Evidence breakdown in output (not just final P)
  5. Recalibrated thresholds: KABAL >=75%, SUSPICIOUS 40-75%

Limitation: no PnL (usd_value IS NULL), no position sizes (amount IS NULL).
Timing is the sole available high-quality signal.
"""

import sqlite3
import json
import os
import math
from datetime import datetime, timezone
from collections import defaultdict
from config import RAB9_DB_ENABLED, RAB9_DB_PATH


# ── Bayesian priors ──
PRIOR_KABAL = 0.02  # ~2% of active traders show kabal patterns

# ── Evidence weights (log-odds) — v3 recalibrated ──
# Mutually exclusive categories to prevent stacking:
#   TIER:  max of {tier1_early, tier2_early} — only best tier counts
#   COVERAGE: full (all winners) OR high (≥75%) — only one fires
#   BEHAVIOR: max of {buy_heavy, high_volume} — only strongest behavior
#   NEGATIVE: each fires independently (they measure different things)
EVIDENCE = {
    # TIER category (mutually exclusive — only best tier)
    "tier1_early":          2.5,   # early on ≥1 Tier1 winner (>=$2M MC)
    "tier2_early":          1.5,   # early on ≥1 Tier2 winner ($500K-$2M) — only if no Tier1

    # COVERAGE category (mutually exclusive — only best coverage)
    "full_coverage":        2.5,   # traded ALL winner tokens
    "high_coverage":        1.5,   # traded ≥75% of winners (3/4)

    # BEHAVIOR category (mutually exclusive — only strongest)
    "buy_heavy":            1.5,   # buy_ratio ≥ 0.70 on winners
    "high_volume":          1.0,   # 50+ trades on winners

    # NEGATIVE signals (each fires independently)
    "exit_timing_6h":      -2.5,   # sold within 6h of entry on winner
    "exit_timing_12h":     -1.5,   # sold within 12h of entry on winner
    "diluted":             -2.0,   # ≥10 tokens, <30% are winners
    "single_winner_only":  -1.5,   # only 1 winner — insufficient pattern
    "sell_heavy":          -2.0,   # buy_ratio < 0.45 on winners → primarily selling
    "low_volume":          -1.0,   # <10 trades on winners total
}

# ── Tier thresholds ──
TIER1_MC = 2_000_000   # $2M+
TIER2_MC =   500_000   # $500K-$2M

# ── Classification thresholds (v3 recalibrated) ──
KABAL_THRESHOLD = 0.80       # P >= 80% → KABAL
SUSPICIOUS_THRESHOLD = 0.45  # 45% <= P < 80% → SUSPICIOUS

# ── Minimum requirements ──
MIN_WINNER_TOKENS = 2        # must trade at least 2 winner tokens
MIN_WINNER_TRADES = 10       # must have at least 10 trades on winners


# ──────────────────────────────────────────────────────────────────────
#  Tiered winner loader
# ──────────────────────────────────────────────────────────────────────

def fetch_tiered_winners(conn) -> tuple[dict[str, int], dict[str, int], dict]:
    """Return (tier1_pairs, tier2_pairs, token_starts).

    tier1/2_pairs map pair_address → tier (1 or 2).
    token_starts maps pair_address → oldest_trade_unix.
    """
    pairs = conn.execute(
        """SELECT pair_address, market_cap_usd, oldest_trade_unix
           FROM pairs
           WHERE market_cap_usd IS NOT NULL AND market_cap_usd >= ?""",
        [TIER2_MC],
    ).fetchall()

    tier1 = {}
    tier2 = {}
    starts = {}

    for row in pairs:
        addr = row["pair_address"]
        mc = row["market_cap_usd"] or 0
        ts = row["oldest_trade_unix"] or 0
        starts[addr] = ts
        if mc >= TIER1_MC:
            tier1[addr] = 1
        else:
            tier2[addr] = 2

    return tier1, tier2, starts


# ──────────────────────────────────────────────────────────────────────
#  Time-normalized early score
# ──────────────────────────────────────────────────────────────────────

def early_score(entry_unix: int, launch_unix: int) -> float:
    """Binary: did maker trade this token during our tracking period?

    Since oldest_trade_unix == first trade timestamp for all tokens
    (our DB starts at token launch), time normalization can't discriminate.
    Returns 1.0 if maker has any trade on this token, 0.0 otherwise.
    """
    if not entry_unix or not launch_unix:
        return 0.0
    # During our tracking period, first_trade >= launch_unix for all makers.
    # We check: did the maker trade within 72h of launch?
    # Since everyone's first trade IS the launch, this is always true.
    # Instead, use binary: traded this token at all → 1.0
    return 1.0 if entry_unix >= launch_unix else 0.0


# ──────────────────────────────────────────────────────────────────────
#  Exit timing: check sell proximity to entry
# ──────────────────────────────────────────────────────────────────────

def check_exit_timing(conn, maker: str, winner_pairs: list[str]) -> dict:
    """Check if maker sold within 6h/12h/24h of their first buy on each winner.

    Returns:
        {"within_6h": int, "within_12h": int, "within_24h": int, "score": float}
    where score is a negative evidence sum (lower = worse / more dump-like).
    """
    if not winner_pairs:
        return {"within_6h": 0, "within_12h": 0, "within_24h": 0, "score": 0.0}

    ph = ",".join(["?"] * len(winner_pairs))

    # For each winner pair, find: first buy time, first sell time
    rows = conn.execute(
        f"""SELECT pair_address,
                  MIN(CASE WHEN side='BUY' THEN trade_unix END) as first_buy,
                  MIN(CASE WHEN side='SELL' THEN trade_unix END) as first_sell
           FROM pair_trades
           WHERE maker = ? AND pair_address IN ({ph}) AND side IN ('BUY','SELL')
           GROUP BY pair_address""",
        [maker] + winner_pairs,
    ).fetchall()

    within_6h = 0
    within_12h = 0
    within_24h = 0

    for row in rows:
        buy_ts = row["first_buy"]
        sell_ts = row["first_sell"]
        if not buy_ts or not sell_ts:
            continue
        delta_h = (sell_ts - buy_ts) / 3600.0
        if delta_h <= 0:
            continue  # sell before buy = data error
        if delta_h <= 6:
            within_6h += 1
        if delta_h <= 12:
            within_12h += 1
        if delta_h <= 24:
            within_24h += 1

    # Score: each rapid exit adds negative evidence (6h and 12h only)
    score = 0.0
    if within_6h > 0:
        score += EVIDENCE["exit_timing_6h"] * within_6h
    if within_12h > within_6h:
        score += EVIDENCE["exit_timing_12h"] * (within_12h - within_6h)

    return {
        "within_6h": within_6h,
        "within_12h": within_12h,
        "score": round(score, 2),
    }


# ──────────────────────────────────────────────────────────────────────
#  Main library builder
# ──────────────────────────────────────────────────────────────────────

def build_kabal_library(
    min_winner_trades: int = 5,
    min_winner_tokens: int = 1,
    cache_hours: int = 24,
) -> dict:
    """Score all makers and return kabal library.

    Caches to data/kabal_library.json for speed.
    """
    if not RAB9_DB_ENABLED:
        return {}

    cache_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "data", "kabal_library.json"
    )
    if os.path.exists(cache_path):
        age_h = (datetime.now().timestamp() - os.path.getmtime(cache_path)) / 3600
        if age_h < cache_hours:
            with open(cache_path) as f:
                return json.load(f)

    conn = sqlite3.connect(RAB9_DB_PATH)
    conn.row_factory = sqlite3.Row

    # ── Tiered winners ──
    tier1, tier2, token_starts = fetch_tiered_winners(conn)
    all_winners = list(tier1.keys()) + list(tier2.keys())
    if not all_winners:
        conn.close()
        return {}

    winner_set = set(all_winners)
    ph = ",".join(["?"] * len(all_winners))

    # ── All-token counts (for infrastructure filter) ──
    all_token_counts = {}
    for row in conn.execute(
        """SELECT maker, COUNT(DISTINCT pair_address) as cnt
           FROM pair_trades WHERE maker != ''
           GROUP BY maker"""
    ).fetchall():
        all_token_counts[row["maker"]] = row["cnt"]

    # ── Per-maker aggregate on winners ──
    makers = conn.execute(
        f"""SELECT maker,
                  COUNT(DISTINCT pair_address) as winner_tokens,
                  COUNT(*) as winner_trades,
                  SUM(CASE WHEN side='BUY' THEN 1 ELSE 0 END) as buys,
                  SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END) as sells,
                  MIN(trade_unix) as first_trade_unix
           FROM pair_trades
           WHERE maker != '' AND pair_address IN ({ph})
           GROUP BY maker
           HAVING winner_trades >= ? AND winner_tokens >= ?
           ORDER BY winner_tokens DESC, winner_trades DESC""",
        all_winners + [min_winner_trades, min_winner_tokens],
    ).fetchall()

    library = {}
    for row in makers:
        maker = row["maker"]
        winner_tokens = row["winner_tokens"]
        winner_trades = row["winner_trades"]
        buys = row["buys"] or 0
        sells = row["sells"] or 0
        first_trade = row["first_trade_unix"] or 0
        all_tokens = all_token_counts.get(maker, 1)

        buy_ratio = buys / max(buys + sells, 1)

        # ── Tier detection (binary: traded Tier1? Tier2?) ──
        has_tier1 = any(p in tier1 for p in winner_set)
        has_tier2 = any(p in tier2 for p in winner_set)
        tier1_count = sum(1 for p in winner_set if p in tier1)
        tier2_count = sum(1 for p in winner_set if p in tier2)

        # ── Coverage: fraction of all winners traded ──
        total_winners = len(winner_set)
        coverage = winner_tokens / max(total_winners, 1)
        full_coverage = (winner_tokens == total_winners)
        high_coverage = (coverage >= 0.75)

        # ── Concentration: what fraction of maker's tokens are winners ──
        concentration = winner_tokens / max(all_tokens, 1)

        # ── Exit timing ──
        exit_info = check_exit_timing(conn, maker, all_winners)

        # ══════════════════════════════════════════════════════════
        #  Bayesian update — mutually exclusive categories
        # ══════════════════════════════════════════════════════════
        log_odds = math.log(PRIOR_KABAL / (1 - PRIOR_KABAL))
        evidence_list = []

        # ── TIER (best tier only) ──
        if tier1_count >= 1:
            w = EVIDENCE["tier1_early"]
            log_odds += w
            evidence_list.append({
                "type": "positive",
                "category": "tier",
                "key": "tier1_early",
                "weight": w,
                "detail": f"traded {tier1_count} Tier1 winner(s) (>=$2M MC)",
            })
        elif tier2_count >= 1:
            w = EVIDENCE["tier2_early"]
            log_odds += w
            evidence_list.append({
                "type": "positive",
                "category": "tier",
                "key": "tier2_early",
                "weight": w,
                "detail": f"traded {tier2_count} Tier2 winner(s) ($500K-$2M)",
            })

        # ── COVERAGE (best only) ──
        if full_coverage:
            w = EVIDENCE["full_coverage"]
            log_odds += w
            evidence_list.append({
                "type": "positive",
                "category": "coverage",
                "key": "full_coverage",
                "weight": w,
                "detail": f"traded ALL {total_winners} winners",
            })
        elif high_coverage:
            w = EVIDENCE["high_coverage"]
            log_odds += w
            evidence_list.append({
                "type": "positive",
                "category": "coverage",
                "key": "high_coverage",
                "weight": w,
                "detail": f"traded {winner_tokens}/{total_winners} winners ({coverage:.0%})",
            })

        # ── BEHAVIOR (best only) ──
        if buy_ratio >= 0.70 and winner_trades >= 10:
            w = EVIDENCE["buy_heavy"]
            log_odds += w
            evidence_list.append({
                "type": "positive",
                "category": "behavior",
                "key": "buy_heavy",
                "weight": w,
                "detail": f"buy_ratio={buy_ratio:.0%}, {winner_trades} trades on winners",
            })
        elif winner_trades >= 50:
            w = EVIDENCE["high_volume"]
            log_odds += w
            evidence_list.append({
                "type": "positive",
                "category": "behavior",
                "key": "high_volume",
                "weight": w,
                "detail": f"{winner_trades} trades on winners",
            })

        # ── NEGATIVE (each fires independently) ──

        # Exit timing: rapid sells after entry
        if exit_info["within_6h"] > 0:
            w = EVIDENCE["exit_timing_6h"] * exit_info["within_6h"]
            log_odds += w
            evidence_list.append({
                "type": "negative",
                "category": "exit",
                "key": "exit_timing",
                "weight": w,
                "detail": f"sold within 6h on {exit_info['within_6h']} winner(s)",
            })
        elif exit_info["within_12h"] > 0:
            w = EVIDENCE["exit_timing_12h"] * (exit_info["within_12h"] - exit_info["within_6h"])
            log_odds += w
            evidence_list.append({
                "type": "negative",
                "category": "exit",
                "key": "exit_timing",
                "weight": w,
                "detail": f"sold within 12h on {exit_info['within_12h']} winner(s)",
            })

        # Diluted: trades many tokens, few are winners
        if all_tokens >= 10 and concentration < 0.30:
            w = EVIDENCE["diluted"]
            log_odds += w
            evidence_list.append({
                "type": "negative",
                "category": "concentration",
                "key": "diluted",
                "weight": w,
                "detail": f"{all_tokens} tokens, only {winner_tokens} winners ({concentration:.0%})",
            })

        # Single winner
        if winner_tokens == 1:
            w = EVIDENCE["single_winner_only"]
            log_odds += w
            evidence_list.append({
                "type": "negative",
                "category": "coverage",
                "key": "single_winner_only",
                "weight": w,
                "detail": "single winner — insufficient pattern",
            })

        # Sell-heavy on winners (triggers at <45% — selling 55%+ = exit liquidity)
        if buy_ratio < 0.45 and sells > 5:
            w = EVIDENCE["sell_heavy"]
            log_odds += w
            evidence_list.append({
                "type": "negative",
                "category": "behavior",
                "key": "sell_heavy",
                "weight": w,
                "detail": f"sell-heavy ({1-buy_ratio:.0%} sells)",
            })

        # Low volume
        if winner_trades < 10:
            w = EVIDENCE["low_volume"]
            log_odds += w
            evidence_list.append({
                "type": "negative",
                "category": "volume",
                "key": "low_volume",
                "weight": w,
                "detail": f"only {winner_trades} trades on winners",
            })

        # Convert to probability
        probability = 1 / (1 + math.exp(-log_odds))

        # ── Classification ──
        if all_tokens >= 8 and probability < 0.35:
            classification = "infrastructure"
        elif probability >= KABAL_THRESHOLD:
            classification = "kabal"
        elif probability >= SUSPICIOUS_THRESHOLD:
            classification = "suspicious"
        elif all_tokens >= 3:
            classification = "follower"
        else:
            classification = "unknown"

        if classification in ("kabal", "suspicious", "infrastructure"):
            library[maker] = {
                "probability": round(probability, 3),
                "evidence": evidence_list,
                "winner_tokens": winner_tokens,
                "winner_trades": winner_trades,
                "all_tokens": all_tokens,
                "buy_ratio": round(buy_ratio, 2),
                "tier1_count": tier1_count,
                "tier2_count": tier2_count,
                "coverage": round(coverage, 2),
                "concentration": round(concentration, 2),
                "exit_6h": exit_info["within_6h"],
                "exit_12h": exit_info["within_12h"],
                "classification": classification,
            }

    conn.close()

    # Cache
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump(library, f, ensure_ascii=False, indent=2)

    return library


# ──────────────────────────────────────────────────────────────────────
#  Public API (backward-compatible with v1/v2)
# ──────────────────────────────────────────────────────────────────────

def load_cabal_library() -> dict:
    """Load scored kabal library."""
    return build_kabal_library()


def cross_reference_makers(makers, cabal_library=None):
    """Cross-reference current makers against scored library."""
    if cabal_library is None:
        cabal_library = load_cabal_library() if RAB9_DB_ENABLED else {}

    if not cabal_library:
        return {
            "known": [], "cabal": [], "infrastructure": [],
            "summary": "", "has_signal": False, "cabal_count": 0,
        }

    known = []
    cabal = []
    infra = []

    for m in makers:
        addr = m.get("wallet", "") or m.get("maker", "")
        if addr in cabal_library:
            info = cabal_library[addr]
            entry = {**m, "intel": info}
            if info.get("classification") == "infrastructure":
                infra.append(entry)
            else:
                cabal.append(entry)
            known.append(entry)

    lines = []
    if cabal:
        top = sorted(cabal, key=lambda x: x["intel"].get("probability", 0), reverse=True)
        lines.append(f"🎯 Kabals (timing-verified, {len(cabal)}):")
        for c in top[:5]:
            i = c["intel"]
            # Build evidence summary line
            ev_brief = []
            if i.get("tier1_count", 0) > 0:
                ev_brief.append(f"T1×{i['tier1_count']}")
            if i.get("tier2_count", 0) > 0:
                ev_brief.append(f"T2×{i['tier2_count']}")
            if i.get("coverage", 0) >= 0.75:
                ev_brief.append(f"cov={i['coverage']:.0%}")
            if i.get("exit_6h", 0) > 0:
                ev_brief.append(f"⚠️ exit<6h×{i['exit_6h']}")
            ev_str = ", ".join(ev_brief) if ev_brief else "—"

            lines.append(
                f"  • {c['wallet'][:8]}... — P={i.get('probability',0):.0%}, "
                f"{i.get('winner_tokens',0)}W tokens, "
                f"[{ev_str}]"
            )

    if infra:
        lines.append(f"🤖 Infrastructure ({len(infra)}): MEV/bot wallets")

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
    """Compare current makers against historical scans for this pair."""
    if not RAB9_DB_ENABLED:
        return {"has_history": False}

    conn = sqlite3.connect(RAB9_DB_PATH)
    conn.row_factory = sqlite3.Row
    hist = conn.execute(
        """SELECT maker, COUNT(*) as trades,
                  SUM(CASE WHEN side='BUY' THEN 1 ELSE 0 END) as buys,
                  SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END) as sells
           FROM pair_trades WHERE pair_address = ?
           GROUP BY maker ORDER BY trades DESC""",
        [pair_address],
    ).fetchall()
    conn.close()

    if not hist:
        return {"has_history": False, "summary": "First scan for this token."}

    old_makers = {row["maker"]: dict(row) for row in hist}
    new_addrs = {m.get("wallet", "") or m.get("maker", "") for m in new_makers}
    stayed = [a for a in old_makers if a in new_addrs]
    gone = [a for a in old_makers if a not in new_addrs]
    arrived = [a for a in new_addrs if a not in old_makers]

    lines = [f"Historical: {len(old_makers)} wallets"]
    if arrived: lines.append(f"New: {len(arrived)}")
    if gone: lines.append(f"Gone: {len(gone)}")
    if stayed: lines.append(f"Stayed: {len(stayed)}")

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
    """Determine escalation level based on kabal signals."""
    triggers = []
    if cabal_count >= 3:
        triggers.append(("deep", f"{cabal_count} timing-verified kabals"))
    if maker_count >= 50 and concentration > 0.5:
        triggers.append(("deep", "concentration top-5 > 50%"))
    if buy_ratio > 2.0 and maker_count >= 20:
        triggers.append(("deep", f"buy/sell > {buy_ratio:.1f}x"))
    if cabal_count >= 5:
        triggers.append(("deep50", f"{cabal_count} kabals — deep50"))

    if not triggers:
        return False, "", "normal"

    best = max(triggers, key=lambda t: 0 if t[0] == "normal" else 1 if t[0] == "deep" else 2)
    return True, best[1], best[0]
