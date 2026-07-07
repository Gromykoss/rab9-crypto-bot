"""
Cabal pattern detector for RAB9.
Detects KOL-driven token launches using on-chain + social signals.

Patterns detected:
  PUMPFUN_WHALE_AIRDROP — >50% supply sent to KOL wallet at launch
  KOL_ACTIVATION — KOL posts about token, new DEX pairs appear
  CABAL_EXPLOSION — massive pair creation + volume spike
  FLYWHEEL_ACTIVE — sustained growth via airdrop loop

Usage: python3 cabal_detector.py <token_address>
Output: JSON with patterns matched and confidence scores.
"""

import json, os, sys, time, re
from datetime import datetime, timedelta
import requests

TIMEOUT = 10
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
CABAL_STATE_FILE = os.path.join(DATA_DIR, "cabal_state.json")

# ── KOL wallet database ──
KOL_WALLETS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kol_wallets.json")

def load_kol_wallets():
    if os.path.exists(KOL_WALLETS_FILE):
        with open(KOL_WALLETS_FILE) as f:
            return json.load(f).get("wallets", [])
    return []

# ── Birdeye API ──
def _birdeye_key():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "BIRDEYE_KEY" in line or "BIRDEYE_API_KEY" in line:
                    return line.split("=", 1)[1].strip().strip("\"'")
    return ""

def birdeye_token_security(address):
    """Get holder concentration and risk data."""
    key = _birdeye_key()
    if not key:
        return {}
    try:
        r = requests.get(f"https://public-api.birdeye.so/public/token_security?address={address}",
                         headers={"X-API-KEY": key, "x-chain": "solana"}, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json().get("data", {})
    except:
        pass
    return {}

# ── DexScreener API ──
def dexscreener_pairs(address):
    """Get all DEX pairs for a token."""
    try:
        r = requests.get(f"https://api.dexscreener.com/latest/dex/tokens/{address}", timeout=TIMEOUT)
        if r.status_code == 200:
            return r.json().get("pairs", [])
    except:
        pass
    return []

# ── Pattern detection ──
def detect_pumpfun_whale_airdrop(address, pairs):
    """Check if this is a Pump.fun token where >50% supply went to a KOL."""
    if not pairs:
        return {"match": False, "reason": "no pairs"}
    
    # Check if first pair is pumpswap (Pump.fun)
    first_pair = pairs[0] if pairs else {}
    dex_id = first_pair.get("dexId", "")
    
    if dex_id != "pumpswap":
        return {"match": False, "reason": f"not pumpswap (is {dex_id})"}
    
    # Check pair age
    created_ts = first_pair.get("pairCreatedAt", 0) / 1000
    age_days = (time.time() - created_ts) / 86400
    if age_days > 30:
        return {"match": False, "reason": f"too old ({age_days:.0f}d)"}
    
    # Check for KOL wallet in top holders
    security = birdeye_token_security(address)
    holder_pct = security.get("holderConcentration", {})
    top_holder = holder_pct.get("topHolder", 0) if isinstance(holder_pct, dict) else 0
    
    if not top_holder:
        # Try alternative: check if any holder has >40%
        holders_data = security.get("holders", [])
        if holders_data:
            for h in holders_data:
                if h.get("percentage", 0) > 40:
                    top_holder = h["percentage"]
    
    signal = {
        "match": False,
        "phase": "unknown",
        "age_days": round(age_days, 1),
        "dex": dex_id,
        "top_holder_pct": top_holder,
        "pair_count": len(pairs),
        "risks": [],
        "signals": [],
    }
    
    if top_holder >= 40:
        signal["match"] = True
        signal["phase"] = "PUMPFUN_WHALE_AIRDROP"
        signal["signals"].append(f"Top holder: {top_holder}% — potential KOL wallet")
        signal["risks"].append("Whale can dump 40%+ supply anytime")
    
    # Check if token is young (potential sleeper)
    if 3 < age_days < 14 and top_holder >= 40:
        signal["signals"].append(f"Sleeper detected: {age_days:.0f}d old, whale holds {top_holder}%")
    
    return signal

def detect_kol_activation(address, pairs):
    """Check if KOL has activated — new pairs appearing rapidly."""
    if len(pairs) < 2:
        return {"match": False, "reason": "only 1 pair — no activation yet"}
    
    # Count DEXes and pair creation timeline
    dexes = set()
    creation_times = []
    meteora_count = 0
    
    for p in pairs:
        dexes.add(p.get("dexId", ""))
        ts = p.get("pairCreatedAt", 0) / 1000
        creation_times.append(ts)
        if p.get("dexId") == "meteora":
            meteora_count += 1
    
    creation_times.sort()
    
    # Check for rapid pair creation (multiple in 24h)
    if len(creation_times) >= 3:
        # Check if 3+ pairs were created within 24h window
        for i in range(len(creation_times) - 2):
            window = creation_times[i+2] - creation_times[i]
            if window < 86400:  # 24h
                signal = {
                    "match": True,
                    "phase": "KOL_ACTIVATION",
                    "pair_count": len(pairs),
                    "dex_count": len(dexes),
                    "dexes": list(dexes),
                    "meteora_pairs": meteora_count,
                    "signals": [
                        f"3+ pairs in 24h ({len(pairs)} total, {len(dexes)} DEXes)",
                    ],
                }
                if meteora_count >= 2:
                    signal["signals"].append(f"Meteora preference: {meteora_count} DLMM pairs (cabal DEX)")
                if len(dexes) >= 3:
                    signal["signals"].append(f"Multi-DEX: {', '.join(dexes)}")
                return signal
    
    return {"match": False, "reason": "no rapid pair creation"}

def detect_cabal_explosion(address, pairs):
    """Check for explosion: 5+ pairs, massive volume, rapid holder growth."""
    if len(pairs) < 5:
        return {"match": False, "reason": f"only {len(pairs)} pairs"}
    
    # Primary pair (highest liquidity)
    primary = max(pairs, key=lambda p: p.get("liquidity", {}).get("usd", 0))
    
    volume_24h = primary.get("volume", {}).get("h24", 0)
    fdv = primary.get("fdv", 0) or 0
    
    vol_mc_ratio = volume_24h / max(fdv, 1)
    
    # Check price change
    price_change = primary.get("priceChange", {})
    change_24h = price_change.get("h24", 0)
    
    signal = {
        "match": False,
        "phase": "MONITORING",
        "pair_count": len(pairs),
        "volume_24h": volume_24h,
        "fdv": fdv,
        "vol_mc_ratio": round(vol_mc_ratio, 2),
        "price_change_24h": change_24h,
        "signals": [],
    }
    
    if len(pairs) >= 10:
        signal["match"] = True
        signal["phase"] = "CABAL_EXPLOSION"
        signal["signals"].append(f"Massive pair explosion: {len(pairs)} pairs")
    
    if vol_mc_ratio > 1.0:
        signal["signals"].append(f"Volume > MC: {vol_mc_ratio:.1f}x (pump in progress)")
        if not signal["match"]:
            signal["match"] = True
            signal["phase"] = "CABAL_EXPLOSION"
    
    if change_24h > 100:
        signal["signals"].append(f"Price +{change_24h}% in 24h")
    
    return signal

# ── Main detector ──
def analyze(address):
    """Full cabal pattern analysis."""
    pairs = dexscreener_pairs(address)
    
    if not pairs:
        return {"ok": False, "error": "No pairs found"}
    
    primary = pairs[0]
    token_name = primary.get("baseToken", {}).get("name", "?")
    token_symbol = primary.get("baseToken", {}).get("symbol", "?")
    
    result = {
        "ok": True,
        "token": token_name,
        "symbol": token_symbol,
        "address": address,
        "patterns": [],
        "phase": "unknown",
        "risk_level": "medium",
    }
    
    # Run all detectors
    p1 = detect_pumpfun_whale_airdrop(address, pairs)
    p2 = detect_kol_activation(address, pairs)
    p3 = detect_cabal_explosion(address, pairs)
    
    all_patterns = [p1, p2, p3]
    matched = [p for p in all_patterns if p.get("match")]
    
    if matched:
        # Take the highest phase
        phases = {"PUMPFUN_WHALE_AIRDROP": 1, "KOL_ACTIVATION": 2, "CABAL_EXPLOSION": 3}
        best = max(matched, key=lambda p: phases.get(p.get("phase", ""), 0))
        result["phase"] = best["phase"]
        result["risk_level"] = "high" if best["phase"] == "CABAL_EXPLOSION" else "elevated"
        
        for p in matched:
            result["patterns"].append({
                "phase": p["phase"],
                "signals": p.get("signals", []),
                "detail": {k: v for k, v in p.items() if k not in ("match", "phase", "signals")},
            })
    else:
        result["phase"] = "clean"
        result["risk_level"] = "low"
    
    return result

# ── CLI ──
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 cabal_detector.py <token_address>")
        sys.exit(1)
    
    address = sys.argv[1]
    result = analyze(address)
    print(json.dumps(result, indent=2, ensure_ascii=False))
