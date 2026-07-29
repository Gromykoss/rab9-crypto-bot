"""On-chain security check for RAB9 using Birdeye token_security.

Usage: python3 onchain_check.py "token_address"
Returns: JSON with security analysis (rug-check, holder concentration, freeze risk).
"""
import json
import sys
import os
import requests

TIMEOUT = 10


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


def analyze(address: str) -> dict:
    """Fetch token security data and produce risk assessment."""
    key = _read_birdeye_key()
    if not key:
        return {"ok": False, "error": "No Birdeye key"}

    try:
        r = requests.get(
            "https://public-api.birdeye.so/defi/token_security",
            params={"address": address},
            headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
            timeout=TIMEOUT,
        )
        if not r.ok:
            return {"ok": False, "error": f"API {r.status_code}"}

        data = r.json().get("data", {})

        # Risk assessment
        risks = []

        # Freeze authority
        freeze_auth = data.get("freezeAuthority")
        if freeze_auth:
            risks.append("FREEZE: токен может быть заморожен владельцем")

        # Mutable metadata (rug via metadata change)
        if data.get("mutableMetadata"):
            risks.append("MUTABLE: метаданные можно изменить")

        # Transfer fee
        if data.get("transferFeeEnable"):
            risks.append("FEE: встроенная комиссия на трансферы")

        # Creator balance %
        creator_pct = data.get("creatorPercentage")
        if creator_pct is not None:
            creator_pct = float(creator_pct)
            if creator_pct > 5:
                risks.append(f"CREATOR: держит {creator_pct:.1f}% supply")

        # Top 10 concentration
        top10_pct = data.get("top10HolderPercent")
        if top10_pct is not None:
            top10_pct = float(top10_pct)
            if top10_pct > 50:
                risks.append(f"HOLDERS: топ-10 держат {top10_pct:.0f}% — централизация")

        # Lock info
        lock = data.get("lockInfo")
        locked = bool(lock) if lock else False

        # Jupiter strict list
        jup_listed = data.get("jupStrictList", False)

        # Overall risk level
        if not risks:
            risk_level = "LOW"
        elif len(risks) <= 1:
            risk_level = "MEDIUM"
        else:
            risk_level = "HIGH"

        return {
            "ok": True,
            "risk_level": risk_level,
            "risks": risks,
            "locked": locked,
            "jupiter_listed": jup_listed,
            "freeze_authority": bool(freeze_auth),
            "mutable_metadata": bool(data.get("mutableMetadata")),
            "creator_pct": round(creator_pct * 100, 1) if creator_pct else None,
            "top10_pct": round(top10_pct * 100, 1) if top10_pct else None,
            "is_token2022": data.get("isToken2022", False),
        }

    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def format_for_grok(result: dict) -> str:
    if not result.get("ok"):
        return "On-chain: нет данных."

    risk = result["risk_level"]
    lines = [f"On-chain (risk={risk}):"]

    lines.append(f"  Freeze={'⚠️' if result['freeze_authority'] else '✓'} Meta={'⚠️' if result['mutable_metadata'] else '✓'}")
    lines.append(f"  Creator={result['creator_pct']}% Top10={result['top10_pct']}%")
    lines.append(f"  Lock={'✓' if result['locked'] else '⚠️'} Jupiter={'✓' if result['jupiter_listed'] else '✗'}")

    if result["risks"]:
        lines.append(f"  ⚠️ {'; '.join(result['risks'][:2])}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: onchain_check.py <address>"}))
        sys.exit(1)

    result = analyze(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
