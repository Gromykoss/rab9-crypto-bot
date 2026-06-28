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

TIMEOUT = 10


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
    }


def format_for_grok(result: dict) -> str:
    if not result.get("ok"):
        return "Chart: нет данных."

    lines = [f"Chart ({result.get('days',0):.0f}d, {result['candles']} candles):"]
    lines.append(f"  Цена=${result['price']} | ATH=${result['ath']} | Drawdown={result['ath_drawdown']}%")
    lines.append(f"  Тренд: {result['trend']} | Momentum: {result['momentum']} | Vol: {result['volume_trend']}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: chart_analysis.py <address>"}))
        sys.exit(1)
    result = analyze(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
