"""Creator wallet monitor for RAB9.

Tracks creator balance over time to detect conviction (holding) vs dumping.
Stores snapshots as JSON files in data/creator_snapshots/.

Usage: python3 creator_monitor.py <token_address>
Output: JSON with conviction signal and balance history.
"""
import json
import sys
import os
import time
import requests

TIMEOUT = 10
SNAPSHOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "creator_snapshots")


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


def _get_snapshot_path(address: str) -> str:
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    return os.path.join(SNAPSHOTS_DIR, f"{address}.json")


def fetch_creator_balance(address: str) -> dict | None:
    """Fetch current creator balance from Birdeye token_security."""
    key = _read_birdeye_key()
    if not key:
        return None
    try:
        r = requests.get(
            "https://public-api.birdeye.so/defi/token_security",
            params={"address": address},
            headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
            timeout=TIMEOUT,
        )
        if r.ok:
            data = r.json().get("data", {})
            return {
                "creator_address": data.get("creatorAddress"),
                "balance": data.get("creatorBalance", 0) or 0,
                "pct": float(data.get("creatorPercentage", 0) or 0),
                "supply": float(data.get("totalSupply", 0) or 0),
                "creation_time": data.get("creationTime", 0) or 0,
            }
    except Exception:
        pass
    return None


def load_history(address: str) -> list[dict]:
    """Load snapshot history for a token."""
    path = _get_snapshot_path(address)
    if os.path.exists(path):
        try:
            with open(path) as f:
                return json.load(f)
        except Exception:
            pass
    return []


def save_snapshot(address: str, current: dict):
    """Append a snapshot to history."""
    history = load_history(address)
    snapshot = {
        "ts": int(time.time()),
        "balance": current["balance"],
        "pct": current["pct"],
    }
    history.append(snapshot)
    # Keep last 90 snapshots (~3 months if daily)
    if len(history) > 90:
        history = history[-90:]
    path = _get_snapshot_path(address)
    with open(path, "w") as f:
        json.dump(history, f, indent=2)


def _get_current_price(address: str) -> float | None:
    """Get current price from DexScreener."""
    try:
        r = requests.get(
            f"https://api.dexscreener.com/latest/dex/search?q={address}",
            timeout=TIMEOUT,
        )
        if r.ok:
            pairs = r.json().get("pairs", [])
            for p in pairs:
                price = p.get("priceUsd")
                if price and float(price) > 0:
                    return float(price)
    except Exception:
        pass
    return None


def _get_price_at_time(address: str, timestamp: int) -> float | None:
    """Get approximate price at a given timestamp from Birdeye OHLCV."""
    key = _read_birdeye_key()
    if not key:
        return None
    try:
        from_time = timestamp - 86400 * 3
        to_time = timestamp + 86400 * 3
        r = requests.get(
            "https://public-api.birdeye.so/defi/ohlcv",
            params={"address": address, "type": "1D", "time_from": from_time, "time_to": to_time},
            headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
            timeout=TIMEOUT,
        )
        if r.ok:
            items = r.json().get("data", {}).get("items", [])
            if items:
                closest = min(items, key=lambda c: abs(c["unixTime"] - timestamp))
                return closest.get("c") or closest.get("o")
    except Exception:
        pass
    return None


def analyze_creator(address: str) -> dict:
    """Analyze creator behavior: conviction, dumping, or unknown."""
    current = fetch_creator_balance(address)
    if not current:
        return {"ok": False, "error": "No creator data from Birdeye"}

    # Save current snapshot
    save_snapshot(address, current)
    history = load_history(address)

    result = {
        "ok": True,
        "creator_address": current["creator_address"],
        "current_balance": current["balance"],
        "current_pct": current["pct"],
        "creation_time": current["creation_time"],
        "snapshots": len(history),
    }

    if len(history) < 2:
        result["signal"] = "unknown"
        result["note"] = "first snapshot — need 2+ data points"
        return result

    oldest = history[0]
    newest = history[-1]
    age_days = (newest["ts"] - oldest["ts"]) / 86400
    balance_change_pct = 0
    if oldest["balance"] > 0:
        balance_change_pct = (newest["balance"] - oldest["balance"]) / oldest["balance"] * 100

    result["age_days"] = round(age_days, 1)
    result["balance_change_pct"] = round(balance_change_pct, 1)

    # Signal logic
    if age_days < 3:
        result["signal"] = "unknown"
        result["note"] = f"monitoring {age_days:.1f}d — too early"
    elif balance_change_pct < -80:
        # Check price reaction: did market absorb the dump?
        price_now = _get_current_price(address)
        price_at_start = _get_price_at_time(address, oldest["ts"]) if history else None
        if price_now and price_at_start and price_at_start > 0:
            price_change = (price_now - price_at_start) / price_at_start * 100
            result["price_change"] = round(price_change, 1)
            if price_change > 20:
                result["signal"] = "wallet_rotation"
                result["note"] = f"· creator wallet emptied ({abs(balance_change_pct):.0f}%) BUT price +{price_change:.0f}% — market absorbed, possible rotation to fresh wallets"
            elif price_change > -20:
                result["signal"] = "wallet_rotation"
                result["note"] = f"· creator wallet emptied ({abs(balance_change_pct):.0f}%) but price held ({price_change:+.0f}%) — market didn't care"
            else:
                result["signal"] = "dumped"
                result["note"] = f"⚠️ creator dumped + price crashed {abs(price_change):.0f}% — genuine exit"
        else:
            result["signal"] = "dumped"
            result["note"] = f"⚠️ creator dumped {abs(balance_change_pct):.0f}% over {age_days:.0f}d — price data unavailable"
    elif balance_change_pct < -20:
        # Check price correlation
        price_now = _get_current_price(address)
        price_at_start = _get_price_at_time(address, oldest["ts"]) if history else None
        if price_now and price_at_start and price_at_start > 0:
            price_change = (price_now - price_at_start) / price_at_start * 100
            result["price_change"] = round(price_change, 1)
            if price_change > 10:
                result["signal"] = "partial_rotation"
                result["note"] = f"creator sold {abs(balance_change_pct):.0f}% but price +{price_change:.0f}% — likely profit-taking, not exit"
            else:
                result["signal"] = "selling"
                result["note"] = f"⚠️ creator selling ({abs(balance_change_pct):.0f}%, price {price_change:+.0f}%)"
        else:
            result["signal"] = "selling"
            result["note"] = f"⚠️ creator selling ({abs(balance_change_pct):.0f}% over {age_days:.0f}d)"
    elif balance_change_pct >= -5:
        result["signal"] = "conviction"
        result["note"] = f"✓ creator holding ({age_days:.0f}d, {balance_change_pct:+.0f}%)"
    else:
        result["signal"] = "partial_sell"
        result["note"] = f"creator slowly reducing ({abs(balance_change_pct):.0f}% over {age_days:.0f}d)"

    return result


def format_for_grok(result: dict) -> str:
    """Format creator analysis for Grok prompt."""
    if not result.get("ok"):
        return "Creator: нет данных."

    lines = [f"Creator ({result.get('creator_address', '?')[:10]}...):"]
    lines.append(f"  Balance: {result['current_balance']:,.0f} ({result['current_pct']*100:.1f}%)")
    if result.get("signal") != "unknown":
        lines.append(f"  Signal: {result['signal'].upper()}")
        lines.append(f"  {result['note']}")
        if result.get("age_days"):
            lines.append(f"  Tracked: {result['age_days']}d, {result['snapshots']} snapshots")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: creator_monitor.py <address>"}))
        sys.exit(1)

    result = analyze_creator(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
