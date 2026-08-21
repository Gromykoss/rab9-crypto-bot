"""Meme coin scoring framework for RAB9.

7-pillar scoring (0–115 pts) + hard-gates/caps/confidence (rugradar-паттерн, ADOPT).
Uses available data: Birdeye on-chain, DexScreener market, Jupiter live honeypot.

Hard-gates (после суммы пилларов):
  honeypot fail → score=0
  freeze open   → cap 35
  mint open     → cap 45
  LP not locked → cap 50
  confidence    → score таванится долей разрешённых критичных сигналов

Anti-rug (T-153, penalty-блок): 9 порогов как soft −N в score_security.
Недоступные сигналы (нет dev_holdings / trade_speed и т.п.) — SKIP, не штрафуют.
Отделён от time-логики: чистый penalty, без re-score в рантайме.

RAB9 = аналитика, НЕ торговля. Execution-слоя нет.
ROADMAP trading safety (только док, не внедрять в бота):
  confirm-code, kill switch, position/daily limits, paper-mode default.

Usage: python3 meme_score.py <token_address>
"""
import json
import sys
import os
import requests

TIMEOUT = 10

# Hard-caps (rugradar-паттерн) — верхние потолки при открытых рисках
CAP_FREEZE_OPEN = 35
CAP_MINT_OPEN = 45
CAP_LP_UNLOCKED = 50

# ── Anti-rug thresholds (T-153, своя реализация; SOL→USD через RAB9_SOL_USD) ──
_SOL_USD = float(os.getenv("RAB9_SOL_USD", "150"))
ANTI_RUG_BUY_RATIO_MIN = 0.55          # доля покупок в txns
ANTI_RUG_BUY_VOL_PCT_MIN = 0.55        # доля buy-volume (если есть)
ANTI_RUG_DEV_HOLD_MAX = 0.10           # dev/creator ≤ 10%
ANTI_RUG_TOP_HOLDER_MAX = 0.15         # top holder ≤ 15%
ANTI_RUG_MIN_LIQ_SOL = 5.0             # min liquidity 5 SOL
ANTI_RUG_MAX_MCAP_SOL = 800.0          # sniper-окно; penalty только для свежих
ANTI_RUG_SNIPER_AGE_H = 6.0            # max mcap gate только age < 6h
ANTI_RUG_PRICE_IMPACT_MAX = 0.15       # ≤ 15%
ANTI_RUG_TRADE_SPEED_MAX = 5.0         # ≤ 5 t/s (wash)
ANTI_RUG_RECENT_SELLS_MAX = 0.60       # sells ≤ 60%
# Штрафы (умеренные: SOLID mid-cap вроде BURNIE не должен падать < 80)
_PEN = {
    "buy_ratio": 3,
    "buy_volume_pct": 3,
    "dev_holdings": 4,
    "top_holder": 4,
    "min_liquidity": 5,
    "max_mcap_sniper": 2,
    "price_impact": 3,
    "trade_speed": 3,
    "recent_sells": 3,
}


def _read_birdeye_key():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith("#"):
                    continue
                if "BIRDEYE_API_KEY" in line:
                    parts = line.split("=", 1)
                    if len(parts) < 2:
                        return ""
                    return parts[1].strip().strip("\"'")
    return ""


def fetch_onchain(address: str) -> dict:
    """Birdeye token_security."""
    key = _read_birdeye_key()
    if not key:
        return {}
    try:
        r = requests.get(
            "https://public-api.birdeye.so/defi/token_security",
            params={"address": address},
            headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
            timeout=TIMEOUT,
        )
        return r.json().get("data", {}) if r.ok else {}
    except Exception:
        return {}


def fetch_market(address: str) -> dict:
    """DexScreener pair or token data (accepts pair OR mint)."""
    try:
        # Try as pair first
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/pairs/solana/{address}",
            timeout=TIMEOUT,
        )
        if r.ok:
            data = r.json()
            pairs = data.get("pairs") or []
            if pairs:
                return pairs[0]
        # Fallback: token mint endpoint
        r2 = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{address}",
            timeout=TIMEOUT,
        )
        if r2.ok:
            pairs = r2.json().get("pairs") or []
            if pairs:
                # best by liquidity
                pairs = sorted(
                    pairs,
                    key=lambda p: ((p.get("liquidity") or {}).get("usd") or 0),
                    reverse=True,
                )
                return pairs[0]
    except Exception:
        pass
    return {}


def _get_token_age_days(onchain: dict, market: dict) -> float:
    """Get token age in days. Uses Birdeye creationTime (unix sec) or DexScreener pairCreatedAt (unix ms)."""
    import time
    # Birdeye creationTime is unix seconds
    bt = onchain.get("creationTime", 0) or 0
    if bt > 1e9:
        return (time.time() - bt) / 86400
    # DexScreener pairCreatedAt is unix ms
    pc = market.get("pairCreatedAt", 0) or 0
    if pc > 1e9:
        return (time.time() * 1000 - pc) / (86400 * 1000)
    return 0


def _as_fraction(val) -> float | None:
    """Нормализовать процент/долю к [0, 1]. None если нет данных."""
    if val is None:
        return None
    try:
        v = float(val)
    except (TypeError, ValueError):
        return None
    if v < 0:
        return None
    # 0–1 уже fraction; 1–100 → percent
    if v > 1.0:
        v = v / 100.0
    return v


def anti_rug_penalty(
    onchain: dict,
    market: dict | None = None,
    extras: dict | None = None,
) -> tuple[int, list[str]]:
    """T-153 anti-rug: 9 порогов как soft penalty (своя реализация, без копипасты).

    Каждый ДОСТУПНЫЙ сигнал, нарушающий порог → −N очков.
    Недоступные сигналы ПРОПУСКАЮТСЯ (не штрафуют) — RAB9 часто без
    dev_holdings / trade_speed / price_impact (GMGN/DexScreener).

    Гейт отделён от time-логики: чистый penalty-блок, вызывается из score_security.

    Пороги:
      1. buy_ratio (txns) ≥ 55%
      2. buy_volume_pct ≥ 55%
      3. dev_holdings ≤ 10%
      4. top_holder ≤ 15%
      5. min liquidity 5 SOL
      6. max mcap 800 SOL — только для свежих (<6h), sniper-окно
      7. price impact ≤ 15%
      8. trade_speed ≤ 5 t/s (wash)
      9. recent_sells ≤ 60%

    extras (optional): buy_ratio, buy_volume_pct, dev_holdings, top_holder,
      price_impact, trade_speed, recent_sells_pct, age_hours.
    """
    market = market or {}
    extras = extras or {}
    penalty = 0
    notes: list[str] = []

    # ── 1. buy_ratio ≥ 55% (доля buys в txns) ──
    buy_ratio = extras.get("buy_ratio")
    if buy_ratio is None:
        txns = market.get("txns") or {}
        # h24 стабильнее h1/m5 (mid-cap не штрафуем за минутный шум)
        for win in ("h24", "h1", "m5"):
            w = txns.get(win) or {}
            buys = w.get("buys")
            sells = w.get("sells")
            if buys is not None and sells is not None:
                total = (buys or 0) + (sells or 0)
                if total > 0:
                    buy_ratio = (buys or 0) / total
                    break
    if buy_ratio is not None:
        try:
            br = float(buy_ratio)
            # если передали sell/buy ratio > 1 (msf makers style) — не fraction
            # extras.buy_ratio_is_bs: True → B/S count ratio, not fraction
            if extras.get("buy_ratio_is_bs"):
                # B/S = buys/sells → fraction ≈ bs/(1+bs) приблизительно не нужно;
                # если B/S < 1 → sells dominate
                if br < 1.0:  # more sells than buys
                    penalty += _PEN["buy_ratio"]
                    notes.append(
                        f"⚠️ anti-rug buy_pressure B/S={br:.2f} < 1 → −{_PEN['buy_ratio']}"
                    )
                else:
                    notes.append(f"✓ anti-rug buy_pressure B/S={br:.2f}")
            else:
                if br < ANTI_RUG_BUY_RATIO_MIN:
                    penalty += _PEN["buy_ratio"]
                    notes.append(
                        f"⚠️ anti-rug buy_ratio={br:.0%} < 55% → −{_PEN['buy_ratio']}"
                    )
                else:
                    notes.append(f"✓ anti-rug buy_ratio={br:.0%}")
        except (TypeError, ValueError):
            pass  # skip invalid

    # ── 2. buy_volume_pct ≥ 55% ──
    bvp = extras.get("buy_volume_pct")
    if bvp is None:
        vol = market.get("volume") or {}
        # DexScreener обычно не даёт buy/sell volume раздельно — skip
        buy_v = vol.get("buy") or vol.get("buy24h") or vol.get("h24Buy")
        sell_v = vol.get("sell") or vol.get("sell24h") or vol.get("h24Sell")
        if buy_v is not None and sell_v is not None:
            try:
                bv, sv = float(buy_v or 0), float(sell_v or 0)
                if bv + sv > 0:
                    bvp = bv / (bv + sv)
            except (TypeError, ValueError):
                bvp = None
    bvp_f = _as_fraction(bvp) if bvp is not None else None
    if bvp_f is not None:
        if bvp_f < ANTI_RUG_BUY_VOL_PCT_MIN:
            penalty += _PEN["buy_volume_pct"]
            notes.append(
                f"⚠️ anti-rug buy_vol={bvp_f:.0%} < 55% → −{_PEN['buy_volume_pct']}"
            )
        else:
            notes.append(f"✓ anti-rug buy_vol={bvp_f:.0%}")

    # ── 3. dev_holdings ≤ 10% ──
    dev = extras.get("dev_holdings")
    if dev is None:
        dev = onchain.get("creatorPercentage")
        if dev is None:
            dev = onchain.get("creator_percentage")
        if dev is None:
            dev = onchain.get("ownerPercentage")
    dev_f = _as_fraction(dev) if dev is not None else None
    # creatorPercentage от Birdeye часто 0.0x (fraction) или 0 — 0 = available & ok
    if dev is not None and dev_f is not None:
        if dev_f > ANTI_RUG_DEV_HOLD_MAX:
            penalty += _PEN["dev_holdings"]
            notes.append(
                f"⚠️ anti-rug dev_hold={dev_f:.0%} > 10% → −{_PEN['dev_holdings']}"
            )
        else:
            notes.append(f"✓ anti-rug dev_hold={dev_f:.1%}")

    # ── 4. top_holder ≤ 15% ──
    top_h = extras.get("top_holder")
    if top_h is None:
        top_h = onchain.get("topHolderPercent") or onchain.get("top_holder_pct")
        # top10 ≠ top1: не подставляем top10 (завысило бы penalty)
    top_f = _as_fraction(top_h) if top_h is not None else None
    if top_f is not None:
        if top_f > ANTI_RUG_TOP_HOLDER_MAX:
            penalty += _PEN["top_holder"]
            notes.append(
                f"⚠️ anti-rug top_holder={top_f:.0%} > 15% → −{_PEN['top_holder']}"
            )
        else:
            notes.append(f"✓ anti-rug top_holder={top_f:.0%}")

    # ── 5. min liquidity 5 SOL ──
    liq_usd = None
    liq = market.get("liquidity")
    if isinstance(liq, dict):
        liq_usd = liq.get("usd")
    elif isinstance(liq, (int, float)):
        liq_usd = liq
    if liq_usd is None and extras.get("liquidity_usd") is not None:
        liq_usd = extras.get("liquidity_usd")
    if liq_usd is not None:
        try:
            liq_usd = float(liq_usd)
            min_liq_usd = ANTI_RUG_MIN_LIQ_SOL * _SOL_USD
            if liq_usd < min_liq_usd:
                penalty += _PEN["min_liquidity"]
                notes.append(
                    f"⚠️ anti-rug liq=${liq_usd:.0f} < {ANTI_RUG_MIN_LIQ_SOL} SOL "
                    f"(~${min_liq_usd:.0f}) → −{_PEN['min_liquidity']}"
                )
            else:
                notes.append(f"✓ anti-rug liq=${liq_usd:,.0f}")
        except (TypeError, ValueError):
            pass

    # ── 6. max mcap 800 SOL — только свежие (sniper-окно), mid-cap не штрафуем ──
    mc = market.get("marketCap") or market.get("fdv")
    if mc is None:
        mc = extras.get("market_cap")
    age_h = extras.get("age_hours")
    if age_h is None:
        age_days = _get_token_age_days(onchain, market)
        age_h = age_days * 24.0 if age_days > 0 else None
    if mc is not None and age_h is not None:
        try:
            mc = float(mc)
            age_h = float(age_h)
            max_mc_usd = ANTI_RUG_MAX_MCAP_SOL * _SOL_USD
            if age_h < ANTI_RUG_SNIPER_AGE_H and mc > max_mc_usd:
                penalty += _PEN["max_mcap_sniper"]
                notes.append(
                    f"⚠️ anti-rug sniper mcap=${mc:,.0f} > {ANTI_RUG_MAX_MCAP_SOL} SOL "
                    f"@ {age_h:.1f}h → −{_PEN['max_mcap_sniper']}"
                )
            # established / mid-cap: skip (не rug-сигнал)
        except (TypeError, ValueError):
            pass

    # ── 7. price impact ≤ 15% ──
    pi = extras.get("price_impact")
    if pi is None:
        pi = market.get("priceImpact") or market.get("price_impact")
    pi_f = _as_fraction(pi) if pi is not None else None
    if pi_f is not None:
        if pi_f > ANTI_RUG_PRICE_IMPACT_MAX:
            penalty += _PEN["price_impact"]
            notes.append(
                f"⚠️ anti-rug price_impact={pi_f:.0%} > 15% → −{_PEN['price_impact']}"
            )
        else:
            notes.append(f"✓ anti-rug price_impact={pi_f:.0%}")

    # ── 8. trade_speed ≤ 5 t/s (wash-подозрение) ──
    tps = extras.get("trade_speed")
    if tps is None:
        # аппроксимация: h1 txns / 3600
        txns = market.get("txns") or {}
        h1 = txns.get("h1") or {}
        buys = h1.get("buys")
        sells = h1.get("sells")
        if buys is not None and sells is not None:
            try:
                tps = ((buys or 0) + (sells or 0)) / 3600.0
            except (TypeError, ValueError):
                tps = None
    if tps is not None:
        try:
            tps = float(tps)
            if tps > ANTI_RUG_TRADE_SPEED_MAX:
                penalty += _PEN["trade_speed"]
                notes.append(
                    f"⚠️ anti-rug trade_speed={tps:.1f} t/s > 5 (wash?) → −{_PEN['trade_speed']}"
                )
            else:
                notes.append(f"✓ anti-rug trade_speed={tps:.2f} t/s")
        except (TypeError, ValueError):
            pass

    # ── 9. recent_sells ≤ 60% ──
    rs = extras.get("recent_sells_pct")
    if rs is None:
        txns = market.get("txns") or {}
        # dump-детект: h1 достаточно «recent», h24 — fallback
        for win in ("h1", "h24", "m5"):
            w = txns.get(win) or {}
            buys = w.get("buys")
            sells = w.get("sells")
            if buys is not None and sells is not None:
                total = (buys or 0) + (sells or 0)
                if total > 0:
                    rs = (sells or 0) / total
                    break
    rs_f = _as_fraction(rs) if rs is not None else None
    if rs_f is not None:
        if rs_f > ANTI_RUG_RECENT_SELLS_MAX:
            penalty += _PEN["recent_sells"]
            notes.append(
                f"⚠️ anti-rug recent_sells={rs_f:.0%} > 60% → −{_PEN['recent_sells']}"
            )
        else:
            notes.append(f"✓ anti-rug recent_sells={rs_f:.0%}")

    return penalty, notes


def score_security(
    onchain: dict,
    market: dict | None = None,
    extras: dict | None = None,
) -> tuple[int, list[str]]:
    """Pillar 1: Security & On-chain hygiene (20 pts) + anti-rug penalty (T-153).

    Survival tokens (>7d) get conviction credit.
    market/extras optional — anti_rug_penalty skips missing signals.
    """
    score = 20
    notes = []

    if onchain.get("freezeAuthority"):
        score -= 10
        notes.append("⚠️ freeze authority active")
    else:
        notes.append("✓ freeze revoked")

    if onchain.get("mutableMetadata"):
        score -= 8
        notes.append("⚠️ mutable metadata")
    else:
        notes.append("✓ metadata immutable")

    creator_pct = float(onchain.get("creatorPercentage", 0) or 0)
    age_days = _get_token_age_days(onchain, market or {})
    survival = age_days > 7

    if creator_pct > 5:
        if survival:
            notes.append(f"· creator holds {creator_pct*100:.0f}% — conviction ({age_days:.0f}d)")
        else:
            score -= 8
            notes.append(f"⚠️ creator holds {creator_pct*100:.0f}% — fresh risk")
    elif creator_pct > 0:
        notes.append(f"✓ creator {creator_pct*100:.1f}%")

    top10_pct = float(onchain.get("top10HolderPercent", 0) or 0)
    if top10_pct < 1:  # Value is decimal (0.1927 = 19.27%)
        top10_pct *= 100
    if top10_pct > 50:
        if survival:
            score -= 2
            notes.append(f"· top10={top10_pct:.0f}% — conviction ({age_days:.0f}d survival)")
        else:
            score -= 8
            notes.append(f"⚠️ top10={top10_pct:.0f}% concentrated")
    elif top10_pct > 30:
        if survival:
            notes.append(f"· top10={top10_pct:.0f}% — held through accumulation")
        else:
            score -= 4
            notes.append(f"⚠️ top10={top10_pct:.0f}% moderate")
    else:
        notes.append(f"✓ top10={top10_pct:.0f}% distributed")

    # Survival bonus: immutable + no freeze + >7 days
    if survival and not onchain.get("freezeAuthority") and not onchain.get("mutableMetadata"):
        score += 3
        notes.append(f"✓ survival bonus ({age_days:.0f}d + clean security) +3")

    lock = onchain.get("lockInfo")
    if not lock:
        # PumpSwap: LP часто не залочен — soft-note; hard-cap применяется в apply_gates
        notes.append("· LP not locked (standard for PumpSwap)")
    else:
        notes.append("✓ LP locked")

    # jupStrictList (Birdeye) — мёртвый флаг (API suspended). Живой honeypot
    # идёт отдельно через honeypot_check (hard-gate). Soft: −1 если строго False.
    jup = onchain.get("jupStrictList")
    if jup is False:
        score -= 1
        notes.append("· jupStrictList=false (legacy, soft)")
    elif jup is True:
        notes.append("✓ jupStrictList")

    # ── T-153 anti-rug penalty-блок (отделён от time-логики) ──
    pen, pen_notes = anti_rug_penalty(onchain, market, extras)
    if pen:
        score -= pen
        notes.append(f"anti-rug penalty total −{pen}")
    notes.extend(pen_notes)

    return max(0, score), notes


def score_market(market: dict, chart: dict | None) -> tuple[int, list[str]]:
    """Pillar 2: Market Metrics (20 pts)."""
    score = 20
    notes = []

    mc = market.get("marketCap", 0) or 0
    liq = (market.get("liquidity", {}) or {}).get("usd", 0) or 0
    vol24 = (market.get("volume", {}) or {}).get("h24", 0) or 0

    if mc > 0:
        if mc >= 5_000_000:
            notes.append(f"MC=${mc/1e6:.1f}M — large cap")
        elif mc >= 1_000_000:
            notes.append(f"MC=${mc/1e6:.1f}M — mid cap")
            score -= 2
        elif mc >= 100_000:
            notes.append(f"MC=${mc/1e3:.0f}K — micro cap")
            score -= 5
        else:
            notes.append(f"MC=${mc:.0f} — nano cap")
            score -= 8

    # Liquidity/MC ratio
    if mc > 0 and liq > 0:
        ratio = liq / mc
        if ratio < 0.05:
            score -= 5
            notes.append(f"⚠️ Liq/MC={ratio:.1%} — thin")
        elif ratio < 0.1:
            score -= 2
            notes.append(f"Liq/MC={ratio:.1%}")
        else:
            notes.append(f"✓ Liq/MC={ratio:.1%}")

    # Volume
    if vol24 > 0 and mc > 0:
        vol_ratio = vol24 / mc
        if vol_ratio > 0.5:
            notes.append(f"✓ Vol/MC={vol_ratio:.1f}x — healthy")
        elif vol_ratio < 0.1:
            score -= 3
            notes.append(f"⚠️ Vol/MC={vol_ratio:.1f}x — low")
        else:
            notes.append(f"Vol/MC={vol_ratio:.1f}x")

    # RSI
    if chart and chart.get("ok"):
        rsi = chart.get("rsi")
        if rsi:
            if rsi > 70:
                notes.append(f"RSI={rsi} — overbought")
                score -= 3
            elif rsi < 30:
                notes.append(f"RSI={rsi} — oversold")
            else:
                notes.append(f"RSI={rsi} — neutral")

    # Price trend
    if chart and chart.get("ok"):
        ch = chart.get("changes", {})
        ch24 = ch.get("24h", 0)
        if ch24 < -20:
            score -= 4
            notes.append(f"⚠️ 24h={ch24:+.0f}% dump")
        elif ch24 < -5:
            notes.append(f"24h={ch24:+.0f}%")
        elif ch24 > 20:
            notes.append(f"24h={ch24:+.0f}% pump")
            score -= 2  # FOMO risk

    # ATH drawdown — critical: SOLID coin shouldn't be -80%+ from ATH
    ath_dd = chart.get("ath_drawdown", 0) if chart else 0
    if ath_dd and ath_dd < -80:
        score -= 8
        notes.append(f"🔴 ATH drawdown={ath_dd:+.0f}% — deep loss")
    elif ath_dd and ath_dd < -50:
        score -= 4
        notes.append(f"🟠 ATH drawdown={ath_dd:+.0f}% — significant")

    # Trend phase penalty
    phase = (chart or {}).get("phase", "")
    trend = (chart or {}).get("trend", "")
    if "decay" in phase.lower() or "затухание" in phase.lower():
        score -= 8
        notes.append("🔴 decay phase — dying")
    elif "distribution" in phase.lower() or "раздача" in phase.lower():
        score -= 5
        notes.append("🟠 distribution phase — selling pressure")
    elif "markup" in phase.lower() or "разгон" in phase.lower():
        score -= 3
        notes.append("⚠️ markup phase — entry risk")
    if "downtrend" in trend.lower():
        score -= 3
        notes.append(f"📉 {trend}")

    return max(0, score), notes


def score_holders(onchain: dict) -> tuple[int, list[str]]:
    """Pillar 3: Holder Distribution (15 pts). Survival tokens (>7d) get conviction credit."""
    score = 15
    notes = []

    top10 = float(onchain.get("top10HolderPercent", 0) or 0)
    creator = float(onchain.get("creatorPercentage", 0) or 0)
    age_days = _get_token_age_days(onchain, {})
    survival = age_days > 7

    if top10 > 0:
        top10_pct = top10 * 100
        if top10_pct > 40:
            if survival:
                notes.append(f"· top10={top10_pct:.0f}% — distribution held ({age_days:.0f}d)")
            else:
                score -= 8
                notes.append(f"⚠️ top10={top10_pct:.0f}% — whale zone")
        elif top10_pct > 25:
            if survival:
                score -= 1
                notes.append(f"top10={top10_pct:.0f}% — held steady ({age_days:.0f}d)")
            else:
                score -= 4
                notes.append(f"top10={top10_pct:.0f}% — moderate")
        elif top10_pct > 10:
            notes.append(f"✓ top10={top10_pct:.0f}% — good")
        else:
            notes.append(f"✓ top10={top10_pct:.0f}% — excellent")

    if creator > 0:
        if creator > 0.10:
            if survival:
                notes.append(f"· creator {creator*100:.0f}% — conviction bag ({age_days:.0f}d)")
            else:
                score -= 5
                notes.append(f"⚠️ creator={creator*100:.0f}% — large bag")
        elif creator < 0.02:
            notes.append(f"✓ creator={creator*100:.1f}% — minimal")

    # Survival bonus for holders
    if survival and creator > 0.10:
        score += 3
        notes.append(f"✓ holders conviction ({age_days:.0f}d + creator held) +3")

    return max(0, score), notes


def score_community(market: dict) -> tuple[int, list[str]]:
    """Pillar 4: Community & Social (25 pts)."""
    score = 15  # Base — can go up or down
    notes = []

    info = market.get("info", {}) or {}
    socials = info.get("socials", []) or []

    has_twitter = any(s.get("type") == "twitter" for s in socials)
    has_telegram = any(s.get("type") == "telegram" for s in socials)
    has_website = bool(info.get("websites"))

    if has_twitter:
        score += 3
        notes.append("✓ X account")
    else:
        notes.append("✗ no X — red flag")

    if has_telegram:
        score += 2
        notes.append("✓ Telegram")
    if has_website:
        score += 1
        notes.append("✓ website")

    # TXN activity as proxy for community
    txns = market.get("txns", {}) or {}
    h24 = txns.get("h24", {}) or {}
    total_txns = (h24.get("buys", 0) or 0) + (h24.get("sells", 0) or 0)
    if total_txns > 5000:
        score += 3
        notes.append(f"✓ {total_txns} txns/24h — active")
    elif total_txns > 1000:
        score += 2
        notes.append(f"{total_txns} txns/24h")
    elif total_txns < 100:
        score -= 3
        notes.append(f"⚠️ only {total_txns} txns/24h — dead")

    # Note: real X engagement score requires live X API
    # Placeholder until X-radar is live

    return max(0, min(25, score)), notes


def score_narrative(token_name: str, market: dict) -> tuple[int, list[str]]:
    """Pillar 5: Meme/Narrative Potency (10 pts)."""
    # Auto-assessment based on available signals
    score = 5  # Base — neutral
    notes = []

    mc = market.get("marketCap", 0) or 0

    # High MC suggests narrative has traction
    if mc > 5_000_000:
        score += 3
        notes.append("proven narrative (MC>5M)")
    elif mc > 1_000_000:
        score += 2
        notes.append("traction (MC>1M)")

    # Token age
    created = market.get("pairCreatedAt", 0) or 0
    if created:
        import time
        age_days = (time.time() * 1000 - created) / (86400 * 1000)
        if age_days > 30:
            score += 2
            notes.append(f"survived {age_days:.0f}d — resilience")
        elif age_days > 3:
            notes.append(f"age={age_days:.0f}d")
        else:
            score -= 2
            notes.append(f"⚠️ {age_days*24:.0f}h old — fresh risk")

    # Note: narrative quality assessment needs Grok
    # Placeholder for manual/Grok narrative score

    return max(0, min(10, score)), notes


def score_influencers(token_name: str = "", market: dict = None) -> tuple[int, list[str]]:
    """Pillar 6: Influencer Backing (10 pts). Checks X account presence from DexScreener socials."""
    score = 5
    notes = []

    if market:
        info = market.get("info", {}) or {}
        socials = info.get("socials", []) or []
        has_twitter = any(s.get("type") == "twitter" for s in socials)
        if has_twitter:
            score += 2
            notes.append("✓ X account found in DexScreener")
        else:
            notes.append("✗ no X account")
    else:
        notes.append("⚠️ market data unavailable")

    return max(0, min(10, score)), notes


def score_whale(gmgn_score: int | None, rugcheck_level: str = "unknown") -> tuple[int, list[str]]:
    """Pillar 7: Whale / Smart-Money & RugCheck (15 pts).

    New pillar from auto-sol study. Folds GMGN smart-money + RugCheck
    into a single 0-15 dimension. RAB9 already has security (freeze/mutable)
    in pillar 1, so this focuses on GMGN whale signals + RugCheck scoring.

    Args:
        gmgn_score: 0-15 smart-money enrichment from GMGN (None if not available).
        rugcheck_level: One of 'low', 'medium', 'high', 'unknown'.
    """
    score = 7  # Neutral base
    notes = []

    # ── GMGN smart-money sub-score (0-8 pts) ──
    if gmgn_score is not None:
        if gmgn_score >= 12:
            score += 5
            notes.append(f"🐋 GMGN smart-money: {gmgn_score}/15 — strong whale signal")
        elif gmgn_score >= 8:
            score += 3
            notes.append(f"🐋 GMGN smart-money: {gmgn_score}/15 — moderate")
        elif gmgn_score >= 4:
            score += 1
            notes.append(f"GMGN smart-money: {gmgn_score}/15 — weak")
        else:
            notes.append(f"GMGN smart-money: {gmgn_score}/15 — negligible")
    else:
        notes.append("GMGN: no data")

    # ── RugCheck sub-score (0-7 pts) ──
    if rugcheck_level == "low":
        score += 4
        notes.append("🟢 RugCheck: clean")
    elif rugcheck_level == "medium":
        score += 1
        notes.append("🟡 RugCheck: medium risk")
    elif rugcheck_level == "high":
        score -= 5
        notes.append("🔴 RugCheck: HIGH risk")
    else:  # unknown
        notes.append("⚪ RugCheck: unknown")

    return max(0, min(15, score)), notes


def score_smart_money_ta(chart: dict | None) -> tuple[int, list[str]]:
    """Pillar 8: Smart-Money TA — накопление/пробой с объёмом (10 pts).

    Самостоятельный smart-money-индикатор (НЕ GMGN on-chain). Wyckoff-сигнал:
    крупный игрок накапливает в диапазоне, затем пробивает сопротивление
    с ростом объёма. Источник — chart_analysis.py (TA).

    Веса:
      - breakout  (цена > resistance И rel_vol ≥ 1.5) → +8 (подтверждённый вход)
      - accumulation (phase=accumulation И bullish_divergence) → +5 (ранний вход)
      - иначе → 0
    """
    if not chart or not chart.get("ok"):
        return 0, ["Smart-Money TA: нет chart-данных"]

    if chart.get("smart_money_breakout"):
        return 8, ["📈 Smart-Money: пробой диапазона с объёмом (цена выше сопротивления, объём ×1.5+)"]

    if chart.get("smart_money_accumulation"):
        return 5, ["📦 Smart-Money: накопление с растущим объёмом (ранний вход, пробоя ещё нет)"]

    return 0, ["Smart-Money TA: нет накопления/пробоя"]


def _resolve_gate_flags(
    onchain: dict,
    security_hints: dict | None,
    honeypot: dict | None,
) -> dict:
    """Собрать флаги hard-gates из Birdeye + optional hints (GMGN/RugCheck) + live honeypot.

    security_hints keys (optional):
      freeze_open: bool | None
      mint_open: bool | None
      lp_locked: bool | None
      top10_pct: float | None  (0–100 organic, after LP filter)
    """
    hints = security_hints or {}

    # Freeze: Birdeye freezeAuthority truthy = open; GMGN renounced_freeze True = closed
    freeze_open = None
    if "freeze_open" in hints and hints["freeze_open"] is not None:
        freeze_open = bool(hints["freeze_open"])
    elif onchain.get("freezeAuthority") is not None:
        freeze_open = bool(onchain.get("freezeAuthority"))
    elif onchain.get("freeze_authority") is not None:
        freeze_open = bool(onchain.get("freeze_authority"))

    # Mint: Birdeye mintAuthority; GMGN renounced_mint True = closed
    mint_open = None
    if "mint_open" in hints and hints["mint_open"] is not None:
        mint_open = bool(hints["mint_open"])
    elif onchain.get("mintAuthority") is not None:
        mint_open = bool(onchain.get("mintAuthority"))
    elif onchain.get("mint_authority") is not None:
        mint_open = bool(onchain.get("mint_authority"))

    # LP lock
    lp_locked = None
    if "lp_locked" in hints and hints["lp_locked"] is not None:
        lp_locked = bool(hints["lp_locked"])
    elif onchain.get("lockInfo") is not None:
        lp_locked = bool(onchain.get("lockInfo"))
    elif onchain.get("locked") is not None:
        lp_locked = bool(onchain.get("locked"))

    # Honeypot live
    hp_status = "unknown"
    if honeypot and honeypot.get("status"):
        hp_status = honeypot["status"]
    elif hints.get("honeypot") is True:
        hp_status = "fail"
    elif hints.get("honeypot") is False:
        hp_status = "pass"

    return {
        "freeze_open": freeze_open,
        "mint_open": mint_open,
        "lp_locked": lp_locked,
        "honeypot_status": hp_status,
        "top10_known": bool(
            onchain.get("top10HolderPercent") is not None
            or hints.get("top10_pct") is not None
        ),
    }


def apply_hard_gates(
    total: int,
    max_total: int,
    gates: dict,
    market: dict,
) -> tuple[int, float, list[str], list[str]]:
    """Hard-gates + caps + confidence ceiling.

    Returns: (final_score, confidence, gate_notes, applied_caps)
    """
    notes: list[str] = []
    caps_applied: list[str] = []
    score = total

    # 1) Honeypot hard-gate: fail → 0
    hp = gates.get("honeypot_status", "unknown")
    if hp == "fail":
        notes.append("🔴 HARD-GATE honeypot: sell-route отсутствует (Jupiter live) → score=0")
        caps_applied.append("honeypot_fail")
        return 0, 1.0, notes, caps_applied
    if hp == "pass":
        notes.append("✓ honeypot pass (Jupiter sell+buy routes)")
    else:
        notes.append("⚪ honeypot unknown (нет уверенного sell-роута)")

    # 2) Caps
    if gates.get("freeze_open") is True:
        if score > CAP_FREEZE_OPEN:
            score = CAP_FREEZE_OPEN
            caps_applied.append(f"freeze_cap_{CAP_FREEZE_OPEN}")
        notes.append(f"⚠️ freeze open → cap {CAP_FREEZE_OPEN}")
    elif gates.get("freeze_open") is False:
        notes.append("✓ freeze revoked")

    if gates.get("mint_open") is True:
        if score > CAP_MINT_OPEN:
            score = CAP_MINT_OPEN
            caps_applied.append(f"mint_cap_{CAP_MINT_OPEN}")
        notes.append(f"⚠️ mint open → cap {CAP_MINT_OPEN}")
    elif gates.get("mint_open") is False:
        notes.append("✓ mint renounced")

    if gates.get("lp_locked") is False:
        if score > CAP_LP_UNLOCKED:
            score = CAP_LP_UNLOCKED
            caps_applied.append(f"lp_cap_{CAP_LP_UNLOCKED}")
        notes.append(f"⚠️ LP unlocked → cap {CAP_LP_UNLOCKED}")
    elif gates.get("lp_locked") is True:
        notes.append("✓ LP locked")

    # 3) Confidence: доля разрешённых критичных сигналов
    # Критичные: honeypot, freeze, mint, lp, top10, market
    critical = []
    critical.append(hp in ("pass", "fail"))  # honeypot resolved
    critical.append(gates.get("freeze_open") is not None)
    critical.append(gates.get("mint_open") is not None)
    critical.append(gates.get("lp_locked") is not None)
    critical.append(bool(gates.get("top10_known")))
    mc = market.get("marketCap") if market else None
    critical.append(bool(mc) or bool((market or {}).get("liquidity")))

    resolved = sum(1 for c in critical if c)
    total_crit = len(critical) or 1
    confidence = resolved / total_crit

    # Floor: tradable (honeypot pass) + market data → минимум 55% confidence.
    # Иначе при dead Birdeye SOLID-токены (BURNIE) таванятся в AVOID.
    if hp == "pass" and critical[-1]:  # market known
        confidence = max(confidence, 0.55)

    # Таванить скор: если данных мало, score не выше confidence * max
    conf_cap = int(round(max_total * max(confidence, 0.15)))
    if score > conf_cap:
        notes.append(
            f"⚪ confidence={confidence:.0%} ({resolved}/{total_crit}) → cap {conf_cap}"
        )
        caps_applied.append(f"confidence_cap_{conf_cap}")
        score = conf_cap
    else:
        notes.append(f"confidence={confidence:.0%} ({resolved}/{total_crit} critical)")

    return max(0, score), confidence, notes, caps_applied


def compute_score(
    address: str,
    chart_data: dict | None = None,
    gmgn_score: int | None = None,
    rugcheck_level: str = "unknown",
    security_hints: dict | None = None,
    skip_honeypot: bool = False,
) -> dict:
    """Main scoring function. Returns structured score.

    Args:
        address: Solana token address.
        chart_data: Optional chart analysis dict.
        gmgn_score: Optional GMGN smart-money score 0-15.
        rugcheck_level: Optional RugCheck level ('low'/'medium'/'high'/'unknown').
        security_hints: Optional dict with freeze_open/mint_open/lp_locked/honeypot
            from GMGN/RugCheck (не ломает старые вызовы). Также extras для anti_rug
            (top_holder, price_impact, trade_speed, …) — недоступные skip.
        skip_honeypot: Если True — не бить Jupiter (для offline/unit-тестов).

    TIMED CHECKPOINTS (T-153, документация — логика НЕ меняется):
      RAB9 делает разовый анализ (snapshot), не re-score в рантайме.
      Если у трекера (burnie_sentiment_tracker.py) есть возраст поста/токена
      (pair age, post timestamp) — паттерн «timed checkpoints» из pumpfun-sniper:
      пере-оценивать сигнал через N минут (m5/m15/h1) и сравнивать delta score.
      Внедрение: cron/tracker, не compute_score. Здесь только якорь-докстринг.
    """
    onchain = fetch_onchain(address)
    market = fetch_market(address)

    if not onchain and not market:
        return {"ok": False, "error": "No data for address", "score": 0, "max": 100}

    # ── Живой honeypot (Jupiter Lite, 2 HTTP) ──
    honeypot: dict | None = None
    if not skip_honeypot:
        try:
            from honeypot_check import check_honeypot
            honeypot = check_honeypot(address)
        except Exception as e:
            honeypot = {
                "ok": False,
                "status": "unknown",
                "error": str(e)[:120],
                "source": "jupiter-lite",
            }

    pillars = {}
    total = 0
    max_total = 0

    # anti_rug extras из security_hints (опционально, без ломки API)
    ar_extras = None
    if security_hints:
        ar_keys = (
            "buy_ratio", "buy_ratio_is_bs", "buy_volume_pct", "dev_holdings",
            "top_holder", "price_impact", "trade_speed", "recent_sells_pct",
            "age_hours", "liquidity_usd", "market_cap",
        )
        ar_extras = {k: security_hints[k] for k in ar_keys if k in security_hints} or None

    s, n = score_security(onchain, market, ar_extras)
    pillars["security"] = {"score": s, "max": 20, "notes": n}
    total += s
    max_total += 20

    s, n = score_market(market, chart_data)
    pillars["market"] = {"score": s, "max": 20, "notes": n}
    total += s
    max_total += 20

    s, n = score_holders(onchain)
    pillars["holders"] = {"score": s, "max": 15, "notes": n}
    total += s
    max_total += 15

    s, n = score_community(market)
    pillars["community"] = {"score": s, "max": 25, "notes": n}
    total += s
    max_total += 25

    token_name = (market.get("baseToken") or {}).get("symbol", "?")
    s, n = score_narrative(token_name, market)
    pillars["narrative"] = {"score": s, "max": 10, "notes": n}
    total += s
    max_total += 10

    s, n = score_influencers(token_name, market)
    pillars["influencers"] = {"score": s, "max": 10, "notes": n}
    total += s
    max_total += 10

    s, n = score_whale(gmgn_score, rugcheck_level)
    pillars["whale_rugcheck"] = {"score": s, "max": 15, "notes": n}
    total += s
    max_total += 15

    s, n = score_smart_money_ta(chart_data)
    pillars["smart_money_ta"] = {"score": s, "max": 10, "notes": n}
    total += s
    max_total += 10

    raw_score = total

    # ── Hard-gates + caps + confidence ──
    gates = _resolve_gate_flags(onchain, security_hints, honeypot)
    final, confidence, gate_notes, caps = apply_hard_gates(
        total, max_total, gates, market
    )
    total = final

    # Tier (scaled for 125 max: 103≈83%, 87≈70%, 60≈48% — сохраняет калибровку 115-шкалы)
    if total <= 0 and gates.get("honeypot_status") == "fail":
        tier = "AVOID"
    elif total >= 103:
        tier = "HIGH CONVICTION"
    elif total >= 87:
        tier = "SOLID"
    elif total >= 60:
        tier = "SPECULATIVE"
    else:
        tier = "AVOID"

    return {
        "ok": True,
        "score": total,
        "raw_score": raw_score,
        "max": max_total,
        "tier": tier,
        "pillars": pillars,
        "token": token_name,
        "confidence": round(confidence, 2),
        "gates": {
            "honeypot": gates.get("honeypot_status"),
            "freeze_open": gates.get("freeze_open"),
            "mint_open": gates.get("mint_open"),
            "lp_locked": gates.get("lp_locked"),
            "caps_applied": caps,
            "notes": gate_notes,
        },
        "honeypot": {
            "status": (honeypot or {}).get("status", "unknown"),
            "sell_ok": (honeypot or {}).get("sell_ok"),
            "buy_ok": (honeypot or {}).get("buy_ok"),
            "source": (honeypot or {}).get("source", "jupiter-lite"),
        },
    }


def format_for_grok(result: dict) -> str:
    if not result.get("ok"):
        return "Score: нет данных."

    conf = result.get("confidence")
    conf_s = f" conf={conf:.0%}" if isinstance(conf, (int, float)) else ""
    raw = result.get("raw_score")
    raw_s = f" (raw={raw})" if raw is not None and raw != result.get("score") else ""
    lines = [
        f"Meme Score: {result['score']}/{result['max']} → {result['tier']}{raw_s}{conf_s}",
        "",
    ]
    # Hard-gates / honeypot upfront
    gates = result.get("gates") or {}
    if gates.get("notes"):
        lines.append("  gates:")
        for n in gates["notes"][:6]:
            lines.append(f"    {n}")
    hp = result.get("honeypot") or {}
    if hp.get("status"):
        lines.append(
            f"  honeypot={hp.get('status')} sell={hp.get('sell_ok')} buy={hp.get('buy_ok')}"
        )
    for name, p in result["pillars"].items():
        lines.append(f"  {name}: {p['score']}/{p['max']}")
        for n in p["notes"][:3]:
            lines.append(f"    {n}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: meme_score.py <address> [--chart]"}))
        sys.exit(1)

    address = sys.argv[1]
    chart_data = None
    if "--chart" in sys.argv:
        # Run chart_analysis internally
        import subprocess, os
        rab9_dir = os.path.dirname(os.path.abspath(__file__))
        chart_addr = address
        try:
            r = subprocess.run(
                [sys.executable, os.path.join(rab9_dir, "chart_analysis.py"), chart_addr],
                capture_output=True, text=True, timeout=20,
            )
            if r.returncode == 0 and r.stdout.strip():
                chart_data = json.loads(r.stdout.strip())
        except Exception as e:
            print(f"[SCORE] chart_analysis failed: {e}", file=sys.stderr)

    result = compute_score(address, chart_data)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
