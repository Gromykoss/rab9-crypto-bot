"""Long-term chart analysis for meme coins — with classic TA indicators.

Indicators: RSI(14), SMA(20/50), EMA(12/26), MACD(12,26,9),
Volume-Price Divergence, Support/Resistance swing points.

Phase detection: accumulation/distribution based on volume-price
divergence + indicator confluence, not just 3x breakout.

Usage: python3 chart_analysis.py "token_address"
"""

import json
import subprocess
import sys
import os
import time
import requests
from datetime import datetime, timezone
from pathlib import Path


TIMEOUT = 10


# ── Indicator functions ──

def _sma(data: list[float], period: int) -> list[float | None]:
    """Simple Moving Average. Returns list same length, None for first period-1."""
    result = [None] * len(data)
    if len(data) < period:
        return result
    window_sum = sum(data[:period])
    result[period - 1] = window_sum / period
    for i in range(period, len(data)):
        window_sum += data[i] - data[i - period]
        result[i] = window_sum / period
    return result


def _ema(data: list[float], period: int) -> list[float | None]:
    """Exponential Moving Average."""
    result = [None] * len(data)
    if len(data) < period:
        return result
    multiplier = 2 / (period + 1)
    # Seed with SMA
    seed = sum(data[:period]) / period
    result[period - 1] = seed
    for i in range(period, len(data)):
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def _rsi(closes: list[float], period: int = 14) -> list[float | None]:
    """Relative Strength Index (Wilder's smoothing)."""
    result = [None] * len(closes)
    if len(closes) < period + 1:
        return result

    gains = [max(closes[i] - closes[i - 1], 0) for i in range(1, len(closes))]
    losses = [max(closes[i - 1] - closes[i], 0) for i in range(1, len(closes))]

    # First average
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(closes)):
        avg_gain = (avg_gain * (period - 1) + gains[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i - 1]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))

    return result


def _macd(closes: list[float]) -> dict:
    """MACD (12, 26, 9). Returns {macd_line, signal_line, histogram}."""
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = [None] * len(closes)
    for i in range(len(closes)):
        if ema12[i] is not None and ema26[i] is not None:
            macd_line[i] = ema12[i] - ema26[i]

    # Signal line: 9-period EMA of MACD line
    valid_macd = [(v if v is not None else 0) for v in macd_line]
    signal = _ema(valid_macd, 9)

    histogram = [None] * len(closes)
    for i in range(len(closes)):
        if macd_line[i] is not None and signal[i] is not None:
            histogram[i] = macd_line[i] - signal[i]

    return {"macd_line": macd_line, "signal_line": signal, "histogram": histogram}


def _swing_points(highs: list[float], lows: list[float], lookback: int = 5) -> dict:
    """Find swing highs and lows (local extremes)."""
    swing_highs = []
    swing_lows = []
    for i in range(lookback, len(highs) - lookback):
        # Swing high: higher than all neighbors in window
        if highs[i] == max(highs[i - lookback:i + lookback + 1]):
            swing_highs.append({"index": i, "price": highs[i]})
        # Swing low: lower than all neighbors
        if lows[i] == min(lows[i - lookback:i + lookback + 1]):
            swing_lows.append({"index": i, "price": lows[i]})
    return {"highs": swing_highs, "lows": swing_lows}


def _support_resistance(swings: dict, current_price: float) -> dict:
    """Find nearest support and resistance from swing points."""
    supports = []
    resistances = []
    for s in swings["lows"]:
        if s["price"] < current_price:
            supports.append(s)
    for s in swings["highs"]:
        if s["price"] > current_price:
            resistances.append(s)

    # Cluster nearby levels (within 5%)
    def cluster(levels, max_diff_pct=5):
        if not levels:
            return []
        levels.sort(key=lambda x: x["price"])
        clusters = []
        current_cluster = [levels[0]]
        for l in levels[1:]:
            if abs(l["price"] - current_cluster[-1]["price"]) / current_cluster[-1]["price"] * 100 < max_diff_pct:
                current_cluster.append(l)
            else:
                clusters.append(current_cluster)
                current_cluster = [l]
        clusters.append(current_cluster)
        return [{"price": sum(x["price"] for x in c) / len(c), "touches": len(c)} for c in clusters]

    s_clusters = cluster(supports)
    r_clusters = cluster(resistances)

    nearest_support = s_clusters[-1] if s_clusters else None
    nearest_resistance = r_clusters[0] if r_clusters else None

    return {
        "support": nearest_support,
        "resistance": nearest_resistance,
        "support_levels": s_clusters[-3:] if s_clusters else [],
        "resistance_levels": r_clusters[:3] if r_clusters else [],
    }


def _volume_divergence(closes: list[float], volumes: list[float], window: int = 10) -> str:
    """Detect price-volume divergence in recent window.

    Returns: 'bullish_divergence' | 'bearish_divergence' | 'confluence' | 'none'
    """
    if len(closes) < window:
        return "insufficient_data"

    recent_c = closes[-window:]
    recent_v = volumes[-window:]

    # Split window in half and compare trends
    mid = window // 2
    first_c = sum(recent_c[:mid]) / mid
    last_c = sum(recent_c[mid:]) / (window - mid)
    first_v = sum(recent_v[:mid]) / mid
    last_v = sum(recent_v[mid:]) / (window - mid)

    price_rising = last_c > first_c * 1.02
    price_falling = last_c < first_c * 0.98
    vol_rising = last_v > first_v * 1.1
    vol_falling = last_v < first_v * 0.9

    # Bullish divergence: price making lower lows, volume rising (accumulation)
    if price_falling and vol_rising:
        return "bullish_divergence"

    # Bearish divergence: price making higher highs, volume falling (distribution)
    if price_rising and vol_falling:
        return "bearish_divergence"

    # Confluence: price and volume moving together
    if (price_rising and vol_rising) or (price_falling and vol_falling):
        return "confluence"

    return "none"


# ── Data fetching ──

def _seasonal_volume_multiplier() -> float:
    month = datetime.now(timezone.utc).month
    if month in (6, 7, 8):
        return 0.65
    elif month in (3, 4, 5):
        return 1.2
    return 1.0


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


def fetch_ohlcv(address: str, tf: str = "1D", days: int = 90) -> list[dict]:
    """Fetch OHLCV candles. Birdeye → GMGN kline (free) → local archive."""
    # 1. Birdeye (legacy, key often suspended)
    key = _read_birdeye_key()
    if key:
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
                items = r.json().get("data", {}).get("items", [])
                if items:
                    return items
        except Exception:
            pass
    # 2. GMGN kline — free, 100+ days, no key
    candles = fetch_ohlcv_gmgn(address, tf=tf, days=days)
    if candles:
        return candles
    # 3. Local archive (accumulated snapshots) — grows over time
    return _load_local_ohlcv(address, days)


def fetch_ohlcv_gmgn(address: str, tf: str = "1D", days: int = 90) -> list[dict]:
    """Fetch OHLCV via gmgn-cli market kline (free, no API key).

    Returns candles in Birdeye format: {"unixTime", "o", "h", "l", "c", "v"}.
    Also appends new candles to the local archive (data/ohlcv_archive/{address}.jsonl)
    so the archive grows beyond the provider window.
    """
    resolution = {"1D": "1d", "4H": "4h", "1H": "1h"}.get(tf, "1d")
    since = int(time.time()) - days * 86400
    cmd = [
        "gmgn-cli", "market", "kline",
        "--chain", "sol", "--address", address,
        "--resolution", resolution,
        "--from", str(since),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        payload = json.loads(proc.stdout or "{}")
        rows = payload.get("list") or []
    except Exception:
        rows = []
    candles = []
    for r in rows:
        try:
            candles.append(
                {
                    "unixTime": int(r["time"]) // 1000,
                    "o": float(r["open"]),
                    "h": float(r["high"]),
                    "l": float(r["low"]),
                    "c": float(r["close"]),
                    "v": float(r["volume"]),
                }
            )
        except (KeyError, TypeError, ValueError):
            continue
    candles.sort(key=lambda x: x["unixTime"])
    if candles:
        _append_local_ohlcv(address, candles)
    return candles


def _archive_path(address: str) -> Path:
    return Path(__file__).resolve().parent / "data" / "ohlcv_archive" / f"{address}.jsonl"


def _append_local_ohlcv(address: str, candles: list[dict]) -> None:
    """Append new candles to local archive (dedupe by unixTime)."""
    try:
        path = _archive_path(address)
        path.parent.mkdir(parents=True, exist_ok=True)
        seen: set[int] = set()
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    seen.add(int(json.loads(line)["unixTime"]))
                except Exception:
                    continue
        with path.open("a") as fh:
            for c in candles:
                if int(c["unixTime"]) not in seen:
                    fh.write(json.dumps(c, separators=(",", ":")) + "\n")
                    seen.add(int(c["unixTime"]))
    except Exception:
        pass


def _load_local_ohlcv(address: str, days: int) -> list[dict]:
    """Read accumulated candles from local archive, newest first capped to days."""
    try:
        path = _archive_path(address)
        if not path.exists():
            return []
        candles = []
        cutoff = int(time.time()) - days * 86400
        for line in path.read_text().splitlines():
            try:
                c = json.loads(line)
                if int(c["unixTime"]) >= cutoff:
                    candles.append(c)
            except Exception:
                continue
        candles.sort(key=lambda x: int(x["unixTime"]))
        return candles
    except Exception:
        return []


# ── Main analysis ──

def analyze(address: str) -> dict:
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

    # ── TA Indicators ──

    # RSI(14)
    rsi_values = _rsi(closes, 14)
    rsi = round(rsi_values[-1], 1) if rsi_values[-1] is not None else None

    # SMA
    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    sma20_val = round(sma20[-1], 8) if sma20[-1] is not None else None
    sma50_val = round(sma50[-1], 8) if sma50[-1] is not None else None

    # EMA
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    ema12_val = round(ema12[-1], 8) if ema12[-1] is not None else None
    ema26_val = round(ema26[-1], 8) if ema26[-1] is not None else None

    # MACD
    macd_data = _macd(closes)
    macd_val = round(macd_data["macd_line"][-1], 8) if macd_data["macd_line"][-1] is not None else None
    macd_signal = round(macd_data["signal_line"][-1], 8) if macd_data["signal_line"][-1] is not None else None
    macd_hist = round(macd_data["histogram"][-1], 8) if macd_data["histogram"][-1] is not None else None

    # MACD crossover detection (last 3 bars)
    macd_cross = "none"
    if n >= 3:
        h_prev = macd_data["histogram"]
        valid = [(i, h_prev[i]) for i in range(n-3, n) if h_prev[i] is not None]
        if len(valid) >= 2:
            if valid[0][1] < 0 and valid[-1][1] > 0:
                macd_cross = "bullish_crossover"
            elif valid[0][1] > 0 and valid[-1][1] < 0:
                macd_cross = "bearish_crossover"

    # Volume divergence
    vol_div = _volume_divergence(closes, volumes)

    # Support / Resistance
    swings = _swing_points(highs, lows)
    sr = _support_resistance(swings, current)

    # ── Trend ──
    mid = n // 2
    first_half_avg = sum(closes[:mid]) / mid if mid > 0 else current
    second_half_avg = sum(closes[mid:]) / (n - mid) if n > mid else current
    if second_half_avg > first_half_avg * 1.05:
        trend = "UPTREND"
    elif second_half_avg < first_half_avg * 0.95:
        trend = "DOWNTREND"
    else:
        trend = "RANGE"

    # Momentum
    if n >= 6:
        recent_3 = sum(closes[-3:]) / 3
        prev_3 = sum(closes[-6:-3]) / 3
        if recent_3 > prev_3 * 1.03:
            momentum = "BULLISH"
        elif recent_3 < prev_3 * 0.97:
            momentum = "BEARISH"
        else:
            momentum = "FLAT"
    else:
        momentum = "?"

    # Volume trend
    if n >= 6:
        recent_vol = sum(volumes[-3:]) / 3
        prev_vol = sum(volumes[-6:-3]) / 3 if n >= 6 else recent_vol
        if recent_vol > prev_vol * 1.2:
            vol_trend = "RISING"
        elif recent_vol < prev_vol * 0.8:
            vol_trend = "FALLING"
        else:
            vol_trend = "STABLE"
    else:
        vol_trend = "?"

    # Relative volume (vs 20-day average)
    if n >= 20:
        avg_vol20 = sum(volumes[-20:]) / 20
        rel_vol = volumes[-1] / avg_vol20 if avg_vol20 > 0 else 1.0
    else:
        rel_vol = 1.0

    # ── Phase Detection (TA-informed) ──

    # Price vs SMA
    above_sma20 = sma20_val is not None and current > sma20_val
    above_sma50 = sma50_val is not None and current > sma50_val
    sma_bullish = sma20_val is not None and sma50_val is not None and sma20_val > sma50_val

    # Golden cross / death cross
    golden_cross = False
    death_cross = False
    if n >= 3 and sma20[-1] is not None and sma50[-1] is not None:
        if sma20[-3] is not None and sma50[-3] is not None:
            if sma20[-3] <= sma50[-3] and sma20[-1] > sma50[-1]:
                golden_cross = True
            elif sma20[-3] >= sma50[-3] and sma20[-1] < sma50[-1]:
                death_cross = True

    # Phase decision matrix
    phase = "unknown"
    phase_confidence = "low"

    # Accumulation signals (priority order of evidence strength)
    acc_signals = 0
    acc_total = 8

    if rsi is not None and rsi < 40:
        acc_signals += 1  # oversold zone
    elif rsi is not None and rsi < 50:
        acc_signals += 0.5  # neutral-low

    if vol_div == "bullish_divergence":
        acc_signals += 2  # strong: volume rising while price falling

    if macd_cross == "bullish_crossover":
        acc_signals += 2  # strong: MACD crossing up

    if golden_cross:
        acc_signals += 2  # very strong: SMA20 crossing above SMA50

    if rel_vol > 1.2:
        acc_signals += 1  # above-average volume

    if momentum == "BULLISH":
        acc_signals += 1

    if trend == "UPTREND":
        acc_signals += 1

    if sma_bullish and not above_sma20:
        acc_signals += 0.5  # SMA aligned but price below — potential bounce

    acc_score = acc_signals / acc_total

    # Distribution signals
    dist_signals = 0
    dist_total = 8

    if rsi is not None and rsi > 60:
        dist_signals += 1
    elif rsi is not None and rsi > 70:
        dist_signals += 2  # overbought

    if vol_div == "bearish_divergence":
        dist_signals += 3  # strongest: volume falling while price rising

    if macd_cross == "bearish_crossover":
        dist_signals += 2

    if death_cross:
        dist_signals += 2

    if rel_vol < 0.6:
        dist_signals += 1  # low relative volume

    if momentum == "BEARISH":
        dist_signals += 1

    if trend == "DOWNTREND":
        dist_signals += 1

    if ath_drawdown < -70:
        dist_signals += 1  # deep loss = distribution likely happened

    dist_score = dist_signals / dist_total

    # Decision
    if acc_score >= 0.5:
        phase = "accumulation"
        phase_confidence = "high" if acc_score >= 0.7 else "medium"
    elif dist_score >= 0.5:
        phase = "distribution"
        phase_confidence = "high" if dist_score >= 0.7 else "medium"
    elif dist_score >= 0.35 and vol_div == "bearish_divergence":
        phase = "distribution"
        phase_confidence = "medium"
    elif acc_score >= 0.35 and vol_div == "bullish_divergence":
        phase = "accumulation"
        phase_confidence = "medium"
    else:
        # Fallback to trend-based — BUT post-pump tokens at deep ATH drawdown
        # are NOT distribution (that was the "садись 2" lesson). Deep loss +
        # neutral RSI + flat price = decay (post-pump base), which for
        # event-driven tokens is pre-catalyst accumulation zone.
        if trend == "UPTREND":
            phase = "accumulation"
        elif ath_drawdown < -70 and rsi is not None and rsi < 50:
            phase = "decay"  # post-pump bottom, not distribution
        elif trend == "DOWNTREND":
            phase = "distribution"
        else:
            phase = "accumulation" if rsi and rsi < 50 else "distribution"
        phase_confidence = "low"

    # ── Volume zone detection (from zone analysis — kept for phase_detector compat) ──
    vol_trend_zone = "falling" if vol_trend == "FALLING" else ("rising" if vol_trend == "RISING" else "stable")
    flat_days = 0
    if n >= 10:
        zone_start = n - 1
        for i in range(n - 2, 0, -1):
            if closes[i] <= 0:
                continue
            if closes[i] > closes[-1] * 3 or closes[i] < closes[-1] / 3:
                zone_start = i + 1
                break
        flat_days = n - zone_start

    # Days of data
    if candles:
        days_span = (candles[-1]["unixTime"] - candles[0]["unixTime"]) / 86400
    else:
        days_span = 0

    # ── Signal recommendation ──
    signal = "WAIT"
    if phase == "accumulation" and phase_confidence in ("high", "medium"):
        if vol_div == "bullish_divergence" and macd_cross == "bullish_crossover":
            signal = "BUY"  # strong confluence
        elif acc_score >= 0.6:
            signal = "ACCUMULATE"
        else:
            signal = "WATCH"
    elif phase == "distribution" and phase_confidence in ("high", "medium"):
        if vol_div == "bearish_divergence" and macd_cross == "bearish_crossover":
            signal = "SELL"  # strong confluence
        elif dist_score >= 0.6:
            signal = "REDUCE"
        else:
            signal = "WAIT"
    elif phase == "distribution" and ath_drawdown < -85 and rel_vol < 0.3:
        signal = "DEAD"

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
        "relative_volume": round(rel_vol, 2),
        # TA indicators
        "rsi": rsi,
        "sma20": sma20_val,
        "sma50": sma50_val,
        "ema12": ema12_val,
        "ema26": ema26_val,
        "macd": macd_val,
        "macd_signal": macd_signal,
        "macd_histogram": macd_hist,
        "macd_crossover": macd_cross,
        "volume_divergence": vol_div,
        "support": sr.get("support"),
        "resistance": sr.get("resistance"),
        # Phase
        "phase": phase,
        "phase_confidence": phase_confidence,
        "accumulation_score": round(acc_score, 2),
        "distribution_score": round(dist_score, 2),
        "signal": signal,
        # Legacy compat
        "flat_days": flat_days,
        "vol_trend_zone": vol_trend_zone,
        "seasonal": {6: "summer", 7: "summer", 8: "summer", 3: "spring", 4: "spring", 5: "spring"}.get(
            datetime.now(timezone.utc).month, "normal"
        ),
    }


def format_for_grok(result: dict) -> str:
    if not result.get("ok"):
        return "Chart: нет данных."

    lines = [f"Chart ({result.get('days', 0):.0f}d, {result['candles']} candles):"]
    lines.append(f"  Цена=${result['price']} | ATH=${result['ath']} | Drawdown={result['ath_drawdown']}%")

    # TA summary
    indicators = []
    if result.get("rsi") is not None:
        rsi_label = "oversold" if result["rsi"] < 30 else ("overbought" if result["rsi"] > 70 else "neutral")
        indicators.append(f"RSI={result['rsi']} ({rsi_label})")
    if result.get("macd_crossover") and result["macd_crossover"] != "none":
        cross_label = "🟢 MACD ▲" if "bullish" in result["macd_crossover"] else "🔴 MACD ▼"
        indicators.append(cross_label)
    if result.get("volume_divergence") and result["volume_divergence"] != "none":
        div_label = {"bullish_divergence": "🟢 VolDiv BULLISH (acc)", "bearish_divergence": "🔴 VolDiv BEARISH (dist)"}.get(
            result["volume_divergence"], result["volume_divergence"])
        indicators.append(div_label)
    if indicators:
        lines.append(f"  Indicators: {' | '.join(indicators)}")

    # Trend + MAs
    ma_parts = []
    if result.get("sma20") is not None:
        ma_parts.append(f"SMA20=${result['sma20']:.6f}")
    if result.get("sma50") is not None:
        ma_parts.append(f"SMA50=${result['sma50']:.6f}")
    if ma_parts:
        lines.append(f"  {', '.join(ma_parts)}")

    lines.append(f"  Trend: {result['trend']} | Mom: {result['momentum']} | Vol: {result['volume_trend']} (rel={result.get('relative_volume', 1):.1f}x)")

    # Phase
    phase_label = {
        "accumulation": "📦 НАКОПЛЕНИЕ",
        "distribution": "📤 РАЗДАЧА",
        "decay": "💤 ЗАТУХАНИЕ",
        "dead": "💀 МЁРТВ",
        "unknown": "❓ НЕИЗВЕСТНО",
    }.get(result.get("phase", "unknown"), result.get("phase", "?"))
    lines.append(f"  Phase: {phase_label} (confidence: {result.get('phase_confidence', '?')}, acc={result.get('accumulation_score', 0):.2f} dist={result.get('distribution_score', 0):.2f})")

    # Signal
    signal = result.get("signal", "?")
    signal_emoji = {"BUY": "🟢", "ACCUMULATE": "🟡", "WATCH": "🟡", "WAIT": "⏳", "REDUCE": "🟠", "SELL": "🔴", "DEAD": "💀"}.get(signal, "")
    lines.append(f"  Signal: {signal_emoji} {signal}")

    # S/R
    if result.get("support"):
        lines.append(f"  Support: ${result['support']['price']:.6f} ({result['support']['touches']} touches)")
    if result.get("resistance"):
        lines.append(f"  Resistance: ${result['resistance']['price']:.6f} ({result['resistance']['touches']} touches)")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: chart_analysis.py <address>"}))
        sys.exit(1)
    result = analyze(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
