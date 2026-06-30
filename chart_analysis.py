"""Long-term chart analysis for meme coins.

Uses daily candles (1D) for trend analysis, falls back to 4H/1H.
Focus: trend direction, ATH, drawdown, accumulation/distribution.

Usage: python3 chart_analysis.py "token_address"
"""
import json
import sys
import os
import time
import requests
from datetime import datetime, timezone

TIMEOUT = 10


def _seasonal_volume_multiplier() -> float:
    """Adjust volume thresholds for seasonal patterns.
    Summer (Jun-Aug): lower volume is normal — be more lenient.
    Spring (Mar-May): high activity — stricter thresholds.
    """
    month = datetime.now(timezone.utc).month
    if month in (6, 7, 8):
        return 0.65  # Summer lull: 35% vol drop ≈ normal
    elif month in (3, 4, 5):
        return 1.2   # Spring: volume should hold stronger
    return 1.0       # Autumn/Winter: normal


def _read_birdeye_key():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "BIRDEYE_API_KEY" in line:
                    return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def fetch_ohlcv(address: str, tf: str = "1D", days: int = 90) -> list[dict]:
    key = _read_birdeye_key()
    if not key:
        return []
    now = int(time.time())
    since = now - days * 86400
    try:
        r = requests.get(
            "https://public-api.birdeye.so/defi/ohlcv",
            params={"address": address, "type": tf, "time_from": since, "time_to": now},
            headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
            timeout=TIMEOUT,
        )
        if r.ok:
            return r.json().get("data", {}).get("items", [])
    except Exception:
        pass
    return []


def analyze(address: str) -> dict:
    """Long-term trend analysis using daily candles."""
    candles = fetch_ohlcv(address, "1D", 90)
    if not candles:
        candles = fetch_ohlcv(address, "4H", 30)
    if not candles:
        candles = fetch_ohlcv(address, "1H", 7)
    if not candles:
        return {"ok": False, "error": "No OHLCV data"}

    closes = [c["c"] for c in candles]
    highs = [c["h"] for c in candles]
    lows = [c["l"] for c in candles]
    volumes = [c["v"] for c in candles]
    n = len(closes)

    current = closes[-1]
    ath = max(highs)
    atl = min(lows)
    ath_drawdown = round((current - ath) / ath * 100, 1)

    # Trend: compare first half avg vs second half avg
    mid = n // 2
    first_half_avg = sum(closes[:mid]) / mid if mid > 0 else current
    second_half_avg = sum(closes[mid:]) / (n - mid) if n > mid else current
    if second_half_avg > first_half_avg * 1.05:
        trend = "UPTREND 📈"
    elif second_half_avg < first_half_avg * 0.95:
        trend = "DOWNTREND 📉"
    else:
        trend = "RANGE ↔"

    # Recent momentum: last 3 candles vs previous 3
    if n >= 6:
        recent_3 = sum(closes[-3:]) / 3
        prev_3 = sum(closes[-6:-3]) / 3
        if recent_3 > prev_3 * 1.03:
            momentum = "BULLISH ▲"
        elif recent_3 < prev_3 * 0.97:
            momentum = "BEARISH ▼"
        else:
            momentum = "FLAT —"
    else:
        momentum = "?"

    # Volume trend
    if n >= 6:
        recent_vol = sum(volumes[-3:]) / 3
        prev_vol = sum(volumes[-6:-3]) / 3 if n >= 6 else recent_vol
        vol_trend = "RISING" if recent_vol > prev_vol * 1.2 else ("FALLING" if recent_vol < prev_vol * 0.8 else "STABLE")
    else:
        vol_trend = "?"

    # ── Accumulation / Breakout detection ──
    phase = "unknown"
    flat_days = 0
    breakout_mult = 1.0
    vol_trend_zone = "?"
    if n >= 10:
        # Skip launch volatility: find when price stabilizes (low daily range)
        stable_start = 0
        for i in range(1, n):
            if closes[i] > 0:
                daily_range = abs(highs[i] - lows[i]) / max(closes[i], 1e-12)
                if daily_range < 0.5:  # <50% daily range = stabilized
                    stable_start = i
                    break
        if stable_start == 0:
            stable_start = 3  # skip first 3 candles minimum

        # Find breakout: price > 3x the average of the last N stable candles
        acc_closes = closes[stable_start:]
        acc_vols = volumes[stable_start:]
        m = len(acc_closes)

        breakout_idx = None
        lookback = min(7, m // 2) if m >= 4 else m
        for i in range(lookback + 2, m):
            baseline_avg = sum(acc_closes[i-lookback:i]) / lookback
            if baseline_avg > 0 and acc_closes[i] > baseline_avg * 3:
                breakout_idx = i + stable_start  # absolute index
                break

        # ── Zone analysis (flat zone = where price is now) ──
        # Determine the current zone (last N candles within 3x range)
        zone_start = n - 1
        current_price = closes[-1]
        for i in range(n - 2, max(stable_start, 0), -1):
            if closes[i] <= 0:
                continue
            if closes[i] > current_price * 3 or closes[i] < current_price / 3:
                zone_start = i + 1
                break
        if zone_start <= stable_start:
            zone_start = stable_start

        zone_len = n - zone_start
        if zone_len >= 5:
            flat_days = zone_len
            seasonal_mult = _seasonal_volume_multiplier()
            # Volume trend within zone: compare first half vs second half
            mid = zone_start + zone_len // 2
            vol_first = sum(volumes[zone_start:mid]) / max(mid - zone_start, 1)
            vol_second = sum(volumes[mid:n]) / max(n - mid, 1)
            if vol_second > vol_first * (1.3 / seasonal_mult):
                vol_trend_zone = "rising"
            elif vol_second < vol_first * (0.7 * seasonal_mult):
                vol_trend_zone = "falling"
            else:
                vol_trend_zone = "stable"

            # ALSO check RECENT volume trend (last 14 vs prior 14) — more signal-rich
            recent_n = min(14, zone_len)
            if n >= recent_n * 2:
                recent_vol = sum(volumes[n-recent_n:]) / recent_n
                prior_vol = sum(volumes[n-recent_n*2:n-recent_n]) / recent_n
                if prior_vol > 0 and recent_vol < prior_vol * (0.6 * seasonal_mult):
                    # Recent volume collapsing — override zone trend
                    if vol_trend_zone != "falling":
                        vol_trend_zone = "falling"

            # Phase classification based on price trend + volume
            zone_closes = closes[zone_start:]
            zone_first = sum(zone_closes[:len(zone_closes)//2]) / max(len(zone_closes)//2, 1)
            zone_last = sum(zone_closes[len(zone_closes)//2:]) / max(len(zone_closes) - len(zone_closes)//2, 1)

            if breakout_idx and breakout_idx > zone_start:
                # There was a breakout earlier — we're post-pump
                if zone_last < zone_first * 0.85:
                    phase = "distribution"  # falling from pump
                    if vol_trend_zone == "falling":
                        phase = "decay"  # volume dying = decay
                elif vol_trend_zone == "rising" and zone_last >= zone_first:
                    phase = "accumulation"  # re-accumulating after pump
                elif vol_trend_zone == "falling":
                    phase = "decay"  # flat + falling volume = dying
                else:
                    phase = "accumulation"  # flat + stable volume = possible base
            elif breakout_idx and breakout_idx <= zone_start:
                # Breakout is happening now or recently
                post = closes[breakout_idx:]
                if len(post) >= 2 and post[-1] > post[0]:
                    phase = "markup"
                elif vol_trend_zone == "falling":
                    phase = "decay"  # post-pump, volume dying
                else:
                    phase = "distribution"
            else:
                # No breakout detected — pre-pump zone
                if current_price < atl * 1.15 and flat_days > 14:
                    phase = "decay"  # Flat near ATL = dead, not accumulation
                elif vol_trend_zone == "rising":
                    phase = "accumulation"  # quiet buying
                elif vol_trend_zone == "falling":
                    phase = "decay"  # bleeding out
                else:
                    phase = "accumulation"  # neutral flat base

            if breakout_idx:
                pre_min = min([c for c in closes[stable_start:breakout_idx] if c > 0] or [1e-12])
                breakout_mult = closes[-1] / max(pre_min, 1e-12)

        elif all(c == closes[0] for c in closes[1:]):
            phase = "dead"

    # Days of data
    if candles:
        first_ts = candles[0]["unixTime"]
        last_ts = candles[-1]["unixTime"]
        days_span = (last_ts - first_ts) / 86400
    else:
        days_span = 0

    return {
        "ok": True,
        "candles": n,
        "days": round(days_span, 1),
        "price": round(current, 8),
        "ath": round(ath, 8),
        "atl": round(atl, 8),
        "ath_drawdown": ath_drawdown,
        "trend": trend,
        "momentum": momentum,
        "volume_trend": vol_trend,
        "phase": phase,
        "flat_days": flat_days,
        "breakout_mult": round(breakout_mult, 1),
        "vol_trend_zone": vol_trend_zone,
        "seasonal": {6: "summer", 7: "summer", 8: "summer", 3: "spring", 4: "spring", 5: "spring"}.get(
            datetime.now(timezone.utc).month, "normal"
        ),
    }


def format_for_grok(result: dict) -> str:
    if not result.get("ok"):
        return "Chart: нет данных."

    lines = [f"Chart ({result.get('days',0):.0f}d, {result['candles']} candles):"]
    lines.append(f"  Цена=${result['price']} | ATH=${result['ath']} | Drawdown={result['ath_drawdown']}%")
    lines.append(f"  Тренд: {result['trend']} | Momentum: {result['momentum']} | Vol: {result['volume_trend']}")
    if result.get('phase') and result['phase'] != 'unknown':
        phase_label = {
            'accumulation': '📦 НАКОПЛЕНИЕ',
            'markup': '🚀 РАЗГОН',
            'distribution': '📤 РАЗДАЧА',
            'decay': '💤 ЗАТУХАНИЕ',
            'dead': '💀 МЁРТВ',
        }.get(result['phase'], result['phase'])
        lines.append(f"  Фаза: {phase_label}")
        vol_label = {'rising': '▲', 'falling': '▼', 'stable': '—'}.get(result.get('vol_trend_zone', ''), '')
        if vol_label:
            lines[-1] += f" (vol {vol_label})"
        if result.get('flat_days', 0) > 0:
            lines.append(f"  Накопление: {result['flat_days']} дней, breakout x{result['breakout_mult']}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: chart_analysis.py <address>"}))
        sys.exit(1)
    result = analyze(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
