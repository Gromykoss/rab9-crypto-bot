"""On-chain security check for RAB9.

Birdeye token_security (если ключ жив) + живой Jupiter honeypot (keyless).
jupStrictList из Birdeye — legacy soft-flag; реальный honeypot = Jupiter quote.

Usage: python3 onchain_check.py "token_address"
Returns: JSON with security analysis (rug-check, holder concentration, freeze risk, honeypot).
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


def _live_honeypot(address: str) -> dict:
    """Живой honeypot через Jupiter Lite (keyless). Fail-open → unknown."""
    try:
        from honeypot_check import check_honeypot
        return check_honeypot(address)
    except Exception as e:
        return {
            "ok": False,
            "status": "unknown",
            "error": str(e)[:120],
            "source": "jupiter-lite",
        }


def analyze(address: str) -> dict:
    """Fetch token security data and produce risk assessment.

    Birdeye optional (ключ часто suspended) — без ключа всё равно
    возвращаем ok=True с живым honeypot.
    """
    # ── Живой honeypot всегда (не зависит от Birdeye) ──
    honeypot = _live_honeypot(address)
    hp_status = honeypot.get("status", "unknown")

    key = _read_birdeye_key()
    data: dict = {}
    birdeye_ok = False

    if key:
        try:
            r = requests.get(
                "https://public-api.birdeye.so/defi/token_security",
                params={"address": address},
                headers={"X-API-KEY": key, "x-chain": "solana", "accept": "application/json"},
                timeout=TIMEOUT,
            )
            if r.ok:
                data = r.json().get("data", {}) or {}
                birdeye_ok = bool(data)
        except Exception:
            data = {}

    # Risk assessment
    risks = []

    # Freeze authority
    freeze_auth = data.get("freezeAuthority")
    if freeze_auth:
        risks.append("FREEZE: токен может быть заморожен владельцем")

    # Mint authority
    mint_auth = data.get("mintAuthority")
    if mint_auth:
        risks.append("MINT: mint authority не renounced")

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

    # Jupiter strict list — legacy soft (Birdeye). Реальный тест = honeypot live.
    jup_listed = data.get("jupStrictList", False)

    if hp_status == "fail":
        risks.append("HONEYPOT: sell-route отсутствует (Jupiter live)")
    elif hp_status == "unknown" and honeypot.get("ok"):
        risks.append("HONEYPOT?: роуты не подтверждены")

    # Overall risk level
    if hp_status == "fail":
        risk_level = "HIGH"
    elif not risks:
        risk_level = "LOW"
    elif len(risks) <= 1:
        risk_level = "MEDIUM"
    else:
        risk_level = "HIGH"

    # Без Birdeye и без honeypot-сигнала — всё равно ok (honeypot даёт хоть что-то)
    if not birdeye_ok and not honeypot.get("ok") and hp_status == "unknown":
        return {
            "ok": False,
            "error": "No Birdeye key and honeypot unavailable",
            "honeypot": honeypot,
            "honeypot_status": hp_status,
        }

    creator_out = None
    if creator_pct is not None:
        # Birdeye иногда отдаёт fraction 0–1, иногда уже %
        creator_out = round(creator_pct * 100, 1) if creator_pct <= 1 else round(creator_pct, 1)

    top10_out = None
    if top10_pct is not None:
        top10_out = round(top10_pct * 100, 1) if top10_pct <= 1 else round(top10_pct, 1)

    return {
        "ok": True,
        "risk_level": risk_level,
        "risks": risks,
        "locked": locked,
        "jupiter_listed": jup_listed,  # legacy soft
        "freeze_authority": bool(freeze_auth) if freeze_auth is not None else None,
        "mint_authority": bool(mint_auth) if mint_auth is not None else None,
        "mutable_metadata": bool(data.get("mutableMetadata")) if data else None,
        "creator_pct": creator_out,
        "top10_pct": top10_out,
        "is_token2022": data.get("isToken2022", False) if data else None,
        "honeypot_status": hp_status,
        "honeypot": {
            "status": hp_status,
            "sell_ok": honeypot.get("sell_ok"),
            "buy_ok": honeypot.get("buy_ok"),
            "source": honeypot.get("source", "jupiter-lite"),
        },
        "source": "birdeye+jupiter" if birdeye_ok else "jupiter-only",
    }


def format_for_grok(result: dict) -> str:
    if not result.get("ok"):
        # Даже при fail покажем honeypot если есть
        hp = (result.get("honeypot") or {}).get("status") or result.get("honeypot_status")
        if hp:
            return f"On-chain: нет Birdeye. Honeypot={hp}."
        return "On-chain: нет данных."

    risk = result["risk_level"]
    lines = [f"On-chain (risk={risk}, src={result.get('source', '?')}):"]

    fr = result.get("freeze_authority")
    meta = result.get("mutable_metadata")
    fr_s = "⚠️" if fr else ("✓" if fr is False else "?")
    meta_s = "⚠️" if meta else ("✓" if meta is False else "?")
    lines.append(f"  Freeze={fr_s} Meta={meta_s}")
    lines.append(f"  Creator={result.get('creator_pct')}% Top10={result.get('top10_pct')}%")
    lock_s = "✓" if result.get("locked") else "⚠️"
    jup_s = "✓" if result.get("jupiter_listed") else "✗"
    lines.append(f"  Lock={lock_s} jupStrict={jup_s} (legacy)")

    hp = result.get("honeypot_status") or (result.get("honeypot") or {}).get("status")
    hp_emoji = {"pass": "✓", "fail": "🔴", "unknown": "⚪"}.get(hp, "?")
    lines.append(f"  Honeypot live={hp_emoji} {hp}")

    if result.get("risks"):
        lines.append(f"  ⚠️ {'; '.join(result['risks'][:2])}")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: onchain_check.py <address>"}))
        sys.exit(1)

    result = analyze(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["ok"] else 1)
