"""Phase detector — 4 trading signals from multi-source data.

Combines chart phase, maker flow, on-chain security, kabal behavior,
community sentiment, and meme score into actionable signals.

Signal types:
  🟢 BUY        — accumulation → early markup, strong confirmations
  🟡 ACCUMULATE — buy small lots near support, emerging accumulation
  🔴 SELL       — distribution, kabals dumping, exit
  💀 DEAD       — no volume, no activity, skip or cut losses

Usage: python3 phase_detector.py <chart_json> <maker_json> <onchain_json> <score_json> [sentiment_label]
Returns: JSON with signal, confidence, phase, and evidence breakdown.
"""

import json
import sys
import os


# ── Thresholds ──

# BUY signal: accumulation → early markup
BUY = {
    "chart_phase": ["accumulation", "markup"],  # must be one of these
    "vol_trend_zone": ["rising", "stable"],      # volume not falling
    "buy_ratio_min": 1.3,                         # makers buying
    "mc_min": 100_000,                            # not nano-cap
    "mc_max": 10_000_000,                         # not too large
    "kabals_top5_max": 2,                         # not dominated by kabals
    "kabals_sell_heavy_max": 0,                   # no kabals dumping
    "meme_score_min": 50,                         # at least SPECULATIVE
    "ath_drawdown_max": -70,                      # not deep in loss (> -70%)
    "creator_held_days_min": 3,                   # creator conviction
    "sentiment": ["pos", "neutral"],              # not negative
    "onchain_freeze": False,                      # freeze must be revoked
    "onchain_mutable": False,                     # metadata must be immutable
    "days_since_launch_min": 3,                   # not fresh pump
    "vol_mc_ratio_min": 0.05,                     # minimum volume relative to MC
}

# ACCUMULATE signal: watch & buy small lots near support
ACCUMULATE = {
    "chart_phase": ["accumulation"],              # must be accumulation
    "vol_trend_zone": ["rising", "stable"],       # volume not falling
    "flat_days_min": 3,                           # at least 3 days in zone
    "mc_min": 50_000,
    "mc_max": 5_000_000,
    "buy_ratio_min": 0.8,                         # neutral-to-buy
    "kabals_top5_max": 1,                         # max 1 kabal in top-5
    "kabals_sell_heavy_max": 0,                   # no kabal dumping
    "meme_score_min": 40,                         # borderline SPECULATIVE
    "onchain_freeze": False,
    "onchain_mutable": False,
    "creator_selling": False,                     # creator NOT dumping
    "days_since_launch_min": 7,                   # survived initial dump
    "sentiment": ["pos", "neutral"],
}

# SELL signal: distribution, kabals dumping, exit
SELL = {
    "chart_phase": ["distribution", "decay", "markup"],  # distribution or overbought
    "buy_ratio_max": 0.7,                                  # sell-heavy makers
    "vol_trend_zone": ["falling"],                         # volume drying
    "kabals_sell_heavy_min": 0,                            # any kabal selling (relaxed)
    "ath_drawdown_max": -80,                               # deep loss trigger
    "mc_lp_ratio_min": 15,                                 # thin liquidity
    "creator_selling": True,                               # creator dumping
    "sentiment": ["neg"],                                  # negative sentiment
}

# DEAD signal: skip, no recovery
DEAD = {
    "chart_phase": ["decay", "dead"],
    "vol_24h_max": 5_000,                          # < $5K volume
    "txn_24h_max": 100,                            # < 100 txns
    "mc_max": 100_000,                             # < $100K MC
    "flat_days_min": 14,                           # inactive >2 weeks (only if MC < $500K)
    "x_inactive_days_min": 7,                      # no posts >7 days
    "maker_count_max": 5,                          # < 5 makers
}


def detect(
    chart: dict,
    makers: dict | None = None,
    onchain: dict | None = None,
    score: dict | None = None,
    sentiment_label: str = "neutral",
    x_account_info: dict | None = None,
) -> dict:
    """Detect phase and generate trading signal.

    Args:
        chart: chart_analysis.py output
        makers: maker summary {buy_heavy, sell_heavy, kabals_top5, kabals_sell_heavy, count, buy_ratio}
        onchain: onchain_check.py output {freezeAuthority, mutableMetadata, creatorPercentage, ...}
        score: meme_score.py output {tier, score, pillars}
        sentiment_label: 'pos' | 'neg' | 'neutral'
        x_account_info: {'followers': N, 'tweets': N, 'last_active_days': N} or None

    Returns:
        {signal, signal_emoji, phase, phase_label, confidence, evidence, action}
    """
    evidence = []
    phase = chart.get("phase", "unknown")
    vol_zone = chart.get("vol_trend_zone", "?")
    flat_days = chart.get("flat_days", 0)
    ath_dd = chart.get("ath_drawdown", 0)
    trend = chart.get("trend", "?")

    # Maker data
    buy_heavy = makers.get("buy_heavy", 0) if makers else 0
    sell_heavy = makers.get("sell_heavy", 0) if makers else 0
    maker_count = makers.get("count", 0) if makers else 0
    buy_ratio = makers.get("buy_ratio", 1.0) if makers else 1.0
    kabals_top5 = makers.get("kabals_top5", 0) if makers else 0
    kabals_sell_heavy = makers.get("kabals_sell_heavy", 0) if makers else 0

    # On-chain
    freeze = onchain.get("freezeAuthority", False) if onchain else False
    mutable = onchain.get("mutableMetadata", False) if onchain else False
    creator_pct = float(onchain.get("creatorPercentage", 0) or 0) if onchain else 0
    top10_pct = float(onchain.get("top10HolderPercent", 0) or 0) if onchain else 0
    if top10_pct < 1:
        top10_pct *= 100

    # Score
    score_val = score.get("score", 0) if score else 0
    score_tier = score.get("tier", "?") if score else "?"

    # Market data embedded in score pillars
    mc = 0
    liq = 0
    vol_24h = 0
    txn_24h = 0
    if score and score.get("pillars"):
        market_pillar = score["pillars"].get("market", {})
        for note in market_pillar.get("notes", []):
            if "MC=" in note and "MC/LP" not in note and "MC/LP" not in note:
                # Extract MC: "MC=$3.3M — mid cap" or "MC=$200K — micro cap"
                import re
                m = re.search(r'MC=\$([\d.]+)([MKB])', note)
                if m:
                    val = float(m.group(1))
                    unit = m.group(2)
                    if unit == 'M':
                        mc = val * 1_000_000
                    elif unit == 'K':
                        mc = val * 1_000
                    else:
                        mc = val
            if "Liq/MC=" in note:
                try:
                    ratio_str = note.split("Liq/MC=")[1].split("%")[0]
                    liq_ratio = float(ratio_str) / 100
                    if mc > 0:
                        liq = mc * liq_ratio
                except (ValueError, IndexError):
                    pass
            if "Vol/MC=" in note:
                try:
                    ratio_str = note.split("Vol/MC=")[1].split("x")[0]
                    vol_ratio = float(ratio_str)
                    if mc > 0:
                        vol_24h = mc * vol_ratio
                except (ValueError, IndexError):
                    pass
            if "txns/24h" in note:
                try:
                    txn_24h = int(note.split(" ")[0])
                except (ValueError, IndexError):
                    pass

    mc_lp_ratio = mc / max(liq, 1) if liq > 0 else 999
    vol_mc_ratio = vol_24h / max(mc, 1) if mc > 0 else 0

    # Creator behavior
    creator_held_days = 0
    creator_selling = False
    if onchain:
        age = onchain.get("token_age_days", 0) or 0
        if age > 7 and creator_pct > 0.02:
            creator_held_days = age  # still holds after 7+ days
        elif creator_pct < 0.005 and age > 7:
            creator_selling = True  # dumped almost everything

    # Days since launch
    days_since_launch = chart.get("days", 0) or 0

    # X account
    x_followers = x_account_info.get("followers", 0) if x_account_info else 0
    x_inactive_days = x_account_info.get("last_active_days", 999) if x_account_info else 999
    if x_account_info and x_followers > 0:
        evidence.append(f"X: {x_followers:,} followers, sentiment={sentiment_label}")

    # ═══════════════════════════════════════════
    # DEAD check (highest priority — if dead, nothing else matters)
    # ═══════════════════════════════════════════
    dead_checks = 0
    dead_total = 0

    if phase in DEAD["chart_phase"]:
        dead_checks += 1
        evidence.append(f"💀 chart phase={phase}")
    dead_total += 1

    if vol_24h > 0 and vol_24h < DEAD["vol_24h_max"]:
        dead_checks += 1
        evidence.append(f"💀 volume=${vol_24h:,.0f} < $5K")
    # Missing volume — don't penalize, could be data issue
    dead_total += 1

    if txn_24h > 0 and txn_24h < DEAD["txn_24h_max"]:
        dead_checks += 1
        evidence.append(f"💀 {txn_24h} txns/24h")
    dead_total += 1

    if mc > 0 and mc < DEAD["mc_max"]:
        dead_checks += 1
        evidence.append(f"💀 MC=${mc:,.0f}")
    dead_total += 1

    if flat_days >= DEAD["flat_days_min"]:
        dead_checks += 1
        evidence.append(f"💀 inactive {flat_days}d")
    dead_total += 1

    if maker_count > 0 and maker_count <= DEAD["maker_count_max"]:
        dead_checks += 1
        evidence.append(f"💀 {maker_count} makers")
    dead_total += 1

    if 0 < x_inactive_days >= DEAD["x_inactive_days_min"]:
        dead_checks += 1
        evidence.append(f"💀 X inactive {x_inactive_days}d")
    dead_total += 1

    dead_score = dead_checks / max(dead_total, 1)
    # HARD OVERRIDE: if MC > $500K or volume > $50K/day, token is NOT dead
    if mc > 500_000 or vol_24h > 50_000:
        dead_score = 0
    if dead_score >= 0.5:
        return {
            "signal": "DEAD",
            "signal_emoji": "💀",
            "phase": phase,
            "phase_label": _phase_label(phase),
            "confidence": round(dead_score * 100),
            "evidence": evidence,
            "action": "SKIP — token is dead. If holding, cut losses immediately.",
        }

    # ═══════════════════════════════════════════
    # SELL check
    # ═══════════════════════════════════════════
    sell_checks = 0
    sell_total = 0

    # Critical: kabal coordinated dump
    if buy_ratio < 0.5 and kabals_top5 >= 1:
        sell_checks += 3  # triple weight — this is the strongest signal
        evidence.append(f"🔴 COORDINATED DUMP: buy_ratio={buy_ratio:.1f}, kabals_top5={kabals_top5}")
    sell_total += 3

    if phase in SELL["chart_phase"]:
        sell_checks += 1
        evidence.append(f"🔴 chart phase={phase}")
    sell_total += 1

    if buy_ratio > 0 and buy_ratio < SELL["buy_ratio_max"]:
        sell_checks += 1
        evidence.append(f"🔴 buy_ratio={buy_ratio:.1f} (sell-heavy makers)")
    sell_total += 1

    if vol_zone in SELL["vol_trend_zone"]:
        sell_checks += 1
        evidence.append(f"🔴 volume {vol_zone}")
    sell_total += 1

    if ath_dd < SELL["ath_drawdown_max"]:
        sell_checks += 1
        evidence.append(f"🔴 ATH drawdown={ath_dd:+.0f}%")
    sell_total += 1

    if mc_lp_ratio > SELL["mc_lp_ratio_min"]:
        sell_checks += 1
        evidence.append(f"🔴 MC/LP={mc_lp_ratio:.0f}x (thin)")
    sell_total += 1

    if creator_selling:
        sell_checks += 1
        evidence.append("🔴 creator selling/dumped")
    sell_total += 1

    if sentiment_label in SELL["sentiment"]:
        sell_checks += 1
        evidence.append(f"🔴 sentiment={sentiment_label}")
    sell_total += 1

    # Kabal sell-heavy (separate from coordinated dump)
    if kabals_sell_heavy >= 1 and buy_ratio < 0.7:
        sell_checks += 1
        evidence.append(f"🔴 {kabals_sell_heavy} kabal(s) sell-heavy")
    sell_total += 1

    sell_score = sell_checks / max(sell_total, 1)
    if sell_score >= 0.4:
        action = "SELL"
        if "COORDINATED DUMP" in " ".join(evidence):
            action = "EXIT NOW — coordinated dump detected, exit immediately"
        elif phase == "distribution":
            action = "SELL — distribution phase, take profits or exit"
        else:
            action = "SELL — sell pressure building, reduce position"
        return {
            "signal": "SELL",
            "signal_emoji": "🔴",
            "phase": phase,
            "phase_label": _phase_label(phase),
            "confidence": round(sell_score * 100),
            "evidence": evidence,
            "action": action,
        }

    # ═══════════════════════════════════════════
    # BUY / ACCUMULATE / WAIT
    # ═══════════════════════════════════════════
    buy_checks = 0
    buy_total = 0

    if phase not in BUY["chart_phase"]:
        evidence.append(f"🚫 BUY blocked: chart phase={phase}, need accumulation/markup")
        buy_total = 1  # single check, failed
    else:
        if phase in BUY["chart_phase"]:
            buy_checks += 1
            evidence.append(f"🟢 chart phase={phase}")
        else:
            evidence.append(f"✗ chart phase={phase} (need accumulation/markup)")
        buy_total += 1

        if vol_zone in BUY["vol_trend_zone"]:
            buy_checks += 1
            evidence.append(f"🟢 volume {vol_zone}")
        else:
            evidence.append(f"✗ volume {vol_zone}")
        buy_total += 1

        if buy_ratio >= BUY["buy_ratio_min"]:
            buy_checks += 1
            evidence.append(f"🟢 buy_ratio={buy_ratio:.1f}")
        else:
            evidence.append(f"✗ buy_ratio={buy_ratio:.1f} < {BUY['buy_ratio_min']}")
        buy_total += 1

        if mc == 0 or (mc >= BUY["mc_min"] and mc <= BUY["mc_max"]):
            buy_checks += 1
            evidence.append(f"🟢 MC in range" if mc > 0 else "✗ MC unknown")
        else:
            evidence.append(f"✗ MC=${mc:,.0f} out of range")
        buy_total += 1

        if kabals_top5 <= BUY["kabals_top5_max"]:
            buy_checks += 1
            evidence.append(f"🟢 kabals_top5={kabals_top5}")
        else:
            evidence.append(f"✗ kabals_top5={kabals_top5} > {BUY['kabals_top5_max']}")
        buy_total += 1

        if kabals_sell_heavy <= BUY["kabals_sell_heavy_max"]:
            buy_checks += 1
        else:
            evidence.append(f"✗ kabal(s) sell-heavy")
        buy_total += 1

        if score_val >= BUY["meme_score_min"]:
            buy_checks += 1
            evidence.append(f"🟢 meme_score={score_val} ({score_tier})")
        else:
            evidence.append(f"✗ meme_score={score_val} < {BUY['meme_score_min']}")
        buy_total += 1

        if ath_dd >= BUY["ath_drawdown_max"] or ath_dd == 0:
            buy_checks += 1
        else:
            evidence.append(f"✗ ATH drawdown={ath_dd:+.0f}% too deep")
        buy_total += 1

        if not freeze:
            buy_checks += 1
        else:
            evidence.append("✗ freeze authority active")
        buy_total += 1

        if not mutable:
            buy_checks += 1
        else:
            evidence.append("✗ mutable metadata")
        buy_total += 1

        if sentiment_label in BUY["sentiment"]:
            buy_checks += 1
            evidence.append(f"🟢 sentiment={sentiment_label}")
        else:
            evidence.append(f"✗ sentiment={sentiment_label}")
        buy_total += 1

        if days_since_launch == 0 or days_since_launch >= BUY["days_since_launch_min"]:
            buy_checks += 1
        else:
            evidence.append(f"✗ {days_since_launch:.0f}d since launch < {BUY['days_since_launch_min']}")
        buy_total += 1

        if vol_mc_ratio >= BUY["vol_mc_ratio_min"] or vol_mc_ratio == 0:
            buy_checks += 1
        else:
            evidence.append(f"✗ Vol/MC={vol_mc_ratio:.2f}x too low")
        buy_total += 1

    buy_score = buy_checks / max(buy_total, 1)

    # ═══════════════════════════════════════════
    # ACCUMULATE check (fallback from BUY) — HARD GATE: accumulation phase
    # ═══════════════════════════════════════════
    acc_checks = 0
    acc_total = 0

    if phase not in ACCUMULATE["chart_phase"]:
        evidence.append(f"🚫 ACCUMULATE blocked: chart phase={phase}, need accumulation")
        acc_total = 1
    else:
        if phase in ACCUMULATE["chart_phase"]:
            acc_checks += 1
        acc_total += 1

        if vol_zone in ACCUMULATE["vol_trend_zone"]:
            acc_checks += 1
        acc_total += 1

        if flat_days >= ACCUMULATE["flat_days_min"]:
            acc_checks += 1
        acc_total += 1

        if buy_ratio >= ACCUMULATE["buy_ratio_min"]:
            acc_checks += 1
        acc_total += 1

        if kabals_top5 <= ACCUMULATE["kabals_top5_max"]:
            acc_checks += 1
        acc_total += 1

        if score_val >= ACCUMULATE["meme_score_min"]:
            acc_checks += 1
        acc_total += 1

        if not freeze and not mutable:
            acc_checks += 1
        acc_total += 1

        if sentiment_label in ACCUMULATE["sentiment"]:
            acc_checks += 1
        acc_total += 1

    acc_score = acc_checks / max(acc_total, 1)

    # ── Decision ──
    if buy_score >= 0.7:
        action = "BUY"
        if phase == "markup":
            action = "BUY (early markup) — confirm with small position, add on pullback"
        elif buy_ratio >= 2.0 and kabals_top5 >= 1:
            action = "BUY — strong maker flow + kabal accumulation"
        else:
            action = "BUY — accumulation confirmed, enter near zone average"
        return {
            "signal": "BUY",
            "signal_emoji": "🟢",
            "phase": phase,
            "phase_label": _phase_label(phase),
            "confidence": round(buy_score * 100),
            "evidence": evidence,
            "action": action,
        }
    elif acc_score >= 0.6:
        action = "ACCUMULATE — buy small lots near support, wait for volume confirmation"
        if vol_zone == "rising":
            action = "ACCUMULATE (volume rising) — buy small lots, volume confirming"
        return {
            "signal": "ACCUMULATE",
            "signal_emoji": "🟡",
            "phase": phase,
            "phase_label": _phase_label(phase),
            "confidence": round(acc_score * 100),
            "evidence": evidence,
            "action": action,
        }
    else:
        # Default: SPECULATIVE or WAIT
        if phase == "accumulation" and acc_score >= 0.4:
            return {
                "signal": "WATCH",
                "signal_emoji": "🟡",
                "phase": phase,
                "phase_label": _phase_label(phase),
                "confidence": round(acc_score * 100),
                "evidence": evidence,
                "action": "WATCH — accumulation forming, missing confirmations. Wait for volume + sentiment.",
            }
        elif phase == "markup":
            return {
                "signal": "WATCH",
                "signal_emoji": "🟡",
                "phase": phase,
                "phase_label": _phase_label(phase),
                "confidence": 40,
                "evidence": evidence,
                "action": "WATCH — markup phase, too late to enter. Wait for pullback to accumulation.",
            }
        else:
            return {
                "signal": "WAIT",
                "signal_emoji": "⏳",
                "phase": phase,
                "phase_label": _phase_label(phase),
                "confidence": 30,
                "evidence": evidence,
                "action": "WAIT — insufficient signals. Monitor for accumulation or exit signals.",
            }


def _phase_label(phase: str) -> str:
    return {
        "accumulation": "📦 НАКОПЛЕНИЕ",
        "markup": "🚀 РАЗГОН",
        "distribution": "📤 РАЗДАЧА",
        "decay": "💤 ЗАТУХАНИЕ",
        "dead": "💀 МЁРТВ",
        "unknown": "❓ НЕИЗВЕСТНО",
    }.get(phase, phase)


def format_for_grok(result: dict) -> str:
    """Format phase detector output for Grok prompt injection."""
    if not result:
        return "Phase: unknown"
    lines = [
        f"Phase Signal: {result['signal_emoji']} {result['signal']} (confidence {result['confidence']}%)",
        f"Chart Phase: {result.get('phase_label', result.get('phase', '?'))}",
        f"Action: {result['action']}",
        "",
        "Evidence:",
    ]
    for e in result.get("evidence", []):
        lines.append(f"  {e}")
    return "\n".join(lines)


def format_for_terminal(result: dict) -> str:
    """Compact terminal output."""
    return (
        f"{result['signal_emoji']} {result['signal']} | "
        f"phase={result.get('phase_label', '?')} | "
        f"confidence={result['confidence']}% | "
        f"{result['action']}"
    )


# ── CLI ──
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: phase_detector.py <chart.json> [makers.json] [onchain.json] [score.json] [sentiment]"}))
        sys.exit(1)

    with open(sys.argv[1]) as f:
        chart = json.load(f)

    makers = None
    if len(sys.argv) > 2 and os.path.exists(sys.argv[2]):
        with open(sys.argv[2]) as f:
            makers = json.load(f)

    onchain = None
    if len(sys.argv) > 3 and os.path.exists(sys.argv[3]):
        with open(sys.argv[3]) as f:
            onchain = json.load(f)

    score = None
    if len(sys.argv) > 4 and os.path.exists(sys.argv[4]):
        with open(sys.argv[4]) as f:
            score = json.load(f)

    sentiment = sys.argv[5] if len(sys.argv) > 5 else "neutral"

    result = detect(chart, makers, onchain, score, sentiment)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0)
