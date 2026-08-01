#!/usr/bin/env python3
"""BURNIE community sentiment tracker.

Runs read-only X checks through the configured xurl CLI, appends one JSONL
snapshot, and prints an alert only for strong negative community signals.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
RAB9_DIR = Path("/home/hermes-workspace/rab9")
OUTFILE = RAB9_DIR / "community_sentiment.jsonl"
ACCOUNT = "BurnieSendersX"
NEGATIVE_QUERY = (
    'BURNIE (rug OR scam OR dump OR dumped OR warning OR abandoned OR dead '
    'OR "exit liquidity") -is:retweet'
)
BULLISH_QUERY = (
    'BURNIE (toly OR anatoly OR buy OR signal OR primed OR send OR sending '
    'OR moonshot OR listing OR vote OR accumulation OR bottom OR bounce OR '
    'pump OR breakout OR bullish) -is:retweet'
)

NEGATIVE_TERMS = (
    "rug",
    "rugpull",
    "rug pull",
    "dump warning",
    "dumped",
    "abandoned",
    "dead coin",
    "exit liquidity",
    "dev sold",
    "honeypot",
)
SCAM_PATTERNS = (
    "burnie scam",
    "burnie is a scam",
    "$burnie scam",
    "$burnie is a scam",
)
POSITIVE_TERMS = (
    "bullish",
    "send",
    "sending",
    "moon",
    "100x",
    "based",
    "solid",
    "accumulation",
    "primed",
    "bounce",
    "breakout",
    "pump",
)
TOLY_TERMS = (
    "toly",
    "anatoly",
    "yakovenko",
    "@toly",
)
AI_BUY_TERMS = (
    "buy signal",
    "strong buy",
    "target",
    "upside",
    "x from",
    "openclaw",
    "iscan",
)


def run_xurl(args: list[str], timeout: int = 45) -> tuple[int, dict[str, Any] | None, str]:
    proc = subprocess.run(
        ["xurl", *args],
        cwd=str(RAB9_DIR),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = (proc.stdout or proc.stderr or "").strip()
    try:
        payload = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        payload = None
    return proc.returncode, payload, raw[:300]


def items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def compact_text(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def term_count(texts: list[str], terms: tuple[str, ...]) -> int:
    blob = "\n".join(texts).lower()
    return sum(blob.count(term) for term in terms)


def totals(posts: list[dict[str, Any]]) -> dict[str, int]:
    out = {"likes": 0, "rt": 0, "replies": 0, "views": 0}
    for post in posts:
        metrics = post.get("public_metrics") or {}
        out["likes"] += int(metrics.get("like_count") or 0)
        out["rt"] += int(metrics.get("retweet_count") or 0)
        out["replies"] += int(metrics.get("reply_count") or 0)
        out["views"] += int(metrics.get("impression_count") or 0)
    return out


def first_error(label: str, code: int, payload: dict[str, Any] | None, raw: str) -> str | None:
    if code == 0:
        return None
    status = payload.get("status") if isinstance(payload, dict) else None
    title = payload.get("title") if isinstance(payload, dict) else None
    if status or title:
        return f"{label} failed: {status or code} {title or ''}".strip()
    return f"{label} failed: exit={code} {compact_text(raw, 120)}"


def build_snapshot() -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []

    user_code, user_payload, user_raw = run_xurl(["user", ACCOUNT])
    neg_code, neg_payload, neg_raw = run_xurl(["search", NEGATIVE_QUERY, "-n", "10"])
    bull_code, bull_payload, bull_raw = run_xurl(["search", BULLISH_QUERY, "-n", "10"])

    for label, code, payload, raw in (
        (f"@{ACCOUNT} API", user_code, user_payload, user_raw),
        ("negative scan", neg_code, neg_payload, neg_raw),
        ("bullish scan", bull_code, bull_payload, bull_raw),
    ):
        err = first_error(label, code, payload, raw)
        if err:
            errors.append(err)

    user_data = user_payload.get("data") if isinstance(user_payload, dict) else {}
    user_metrics = user_data.get("public_metrics") if isinstance(user_data, dict) else {}
    followers = int(user_metrics.get("followers_count") or 0)
    tweet_count = int(user_metrics.get("tweet_count") or 0)

    community_posts: list[dict[str, Any]] = []
    recent_posts: list[dict[str, Any]] = []
    negative_posts = items(neg_payload)
    bullish_posts = items(bull_payload)
    community_texts: list[str] = []
    negative_texts = [str(post.get("text") or "") for post in negative_posts]
    bullish_texts = [str(post.get("text") or "") for post in bullish_posts]
    all_scan_texts = negative_texts + bullish_texts

    neg_hits = term_count(all_scan_texts, NEGATIVE_TERMS) + term_count(
        all_scan_texts, SCAM_PATTERNS
    )
    pos_hits = term_count(all_scan_texts, POSITIVE_TERMS)
    toly_hits = term_count(all_scan_texts, TOLY_TERMS)
    ai_buy_hits = term_count(all_scan_texts, AI_BUY_TERMS)
    strong_negative = [
        compact_text(text, 100)
        for text in all_scan_texts
        if any(term in text.lower() for term in NEGATIVE_TERMS + SCAM_PATTERNS)
    ][:3]
    strong_bullish = [
        compact_text(text, 100)
        for text in bullish_texts
        if any(term in text.lower() for term in POSITIVE_TERMS + TOLY_TERMS + AI_BUY_TERMS)
    ][:3]

    # Track follower growth from previous snapshot
    prev_followers = 0
    if OUTFILE.exists():
        try:
            with OUTFILE.open("r") as fh:
                lines = fh.readlines()
                if lines:
                    prev = json.loads(lines[-1])
                    prev_followers = prev.get("followers", 0)
        except (json.JSONDecodeError, OSError):
            pass
    follower_delta = followers - prev_followers if prev_followers else 0

    # Weighted sentiment: Toly + AI signals are strong bullish multipliers
    bullish_score = (toly_hits * 3) + (ai_buy_hits * 2) + pos_hits + (1 if len(bullish_posts) >= 5 else 0) + (1 if follower_delta > 50 else 0)
    bearish_score = neg_hits + len(strong_negative)

    if strong_negative and neg_hits >= 3 and bullish_score < bearish_score:
        sentiment = "neg"
    elif bullish_score > bearish_score:
        sentiment = "pos"
    elif toly_hits >= 1 or ai_buy_hits >= 2:
        sentiment = "pos"
    else:
        sentiment = "neutral"

    recent_totals: dict[str, int] = {}
    notes = [
        f"negative scan: {len(negative_posts)} hits, strong_hits={len(strong_negative)}",
        f"bullish scan: {len(bullish_posts)} hits, toly={toly_hits} ai_buy={ai_buy_hits}",
        f"sentiment_terms neg={neg_hits} pos={pos_hits} toly={toly_hits} ai={ai_buy_hits}",
    ]
    if followers:
        delta_str = f"+{follower_delta}" if follower_delta > 0 else str(follower_delta)
        notes.append(f"@{ACCOUNT}: {followers} followers ({delta_str}), {tweet_count} tweets")
    if strong_negative:
        notes.append("strong_negative: " + " | ".join(strong_negative))
    elif not errors:
        notes.append("no rug-pull accusations or dump warnings detected")
    if strong_bullish:
        notes.append("strong_bullish: " + " | ".join(strong_bullish))
    if errors:
        notes.extend(errors)

    snapshot = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "followers": followers,
        "followers_delta": follower_delta,
        "tweets": tweet_count,
        "sentiment": sentiment,
        "neg_hits": neg_hits,
        "pos_hits": pos_hits,
        "toly_hits": toly_hits,
        "ai_buy_hits": ai_buy_hits,
        "strong_negative": strong_negative,
        "strong_bullish": strong_bullish,
        "notes": "; ".join(notes),
    }
    return snapshot, strong_negative


BURNIE_MINT = "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump"


def fetch_dex_metrics() -> dict[str, Any]:
    """Fetch BURNIE market data from DexScreener (free, no X credits)."""
    out: dict[str, Any] = {"ok": False}
    try:
        url = f"https://api.dexscreener.com/latest/dex/tokens/{BURNIE_MINT}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) RAB9/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pairs = data.get("pairs") or []
        if not pairs:
            return out
        best = sorted(pairs, key=lambda p: float(p.get("liquidity", {}).get("usd") or 0), reverse=True)[0]
        price_usd = best.get("priceUsd")
        out.update(
            {
                "ok": True,
                "price_usd": float(price_usd) if price_usd else None,
                "market_cap": best.get("marketCap"),
                "volume_24h": best.get("volume", {}).get("h24"),
                "liquidity_usd": best.get("liquidity", {}).get("usd"),
                "change_24h": best.get("priceChange", {}).get("h24"),
                "txns_24h": best.get("txns", {}).get("h24"),
                "pair_url": best.get("url"),
            }
        )
    except Exception:
        pass
    return out


def send_telegram(text: str) -> bool:
    """Send alert to configured Telegram chat via Bot API (no extra deps)."""
    try:
        env_path = RAB9_DIR / ".env"
        token = ""
        chat_id = ""
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip("\"'")
                elif line.startswith("TELEGRAM_GROUP_ID="):
                    chat_id = line.split("=", 1)[1].strip().strip("\"'")
        if not token or not chat_id:
            return False
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": text[:3500]}
        ).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception:
        return False


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


RISK_TERMS_RU = {
    "rug": "обвинение в скаме (rug pull)",
    "rugpull": "обвинение в скаме (rug pull)",
    "rug pull": "обвинение в скаме (rug pull)",
    "dumped": "кто-то слил токен",
    "dump warning": "предупреждение о сливе",
    "exit liquidity": "«выходная ликвидность» — покупателей разводят",
    "dev sold": "разработчик продал",
    "honeypot": "ловушка (нельзя продать)",
    "scam": "скам",
    "abandoned": "токен заброшен",
    "dead": "токен мёртв",
}

DRIVER_TERMS_RU = {
    "moonshot": "голосование за листинг на Moonshot",
    "listing": "листинг",
    "vote": "голосование за листинг",
    "toly": "упоминание Toly (основателя Solana)",
    "anatoly": "упоминание Toly (основателя Solana)",
    "buy signal": "сигнал на покупку",
    "strong buy": "сигнал на покупку",
    "accumulation": "накопление",
    "primed": "«взведён» — готов к росту",
    "breakout": "пробой уровня",
    "pump": "памп",
    "100x": "ожидание 100x",
}


def explain_terms(text: str, terms_ru: dict[str, str], limit: int = 3) -> str:
    """Map English meme-coins terms found in a post to plain Russian."""
    low = text.lower()
    found = []
    for term, ru in terms_ru.items():
        if term in low and ru not in found:
            found.append(ru)
        if len(found) >= limit:
            break
    return ", ".join(found) if found else "нет ключевых слов"


def format_alert(snapshot: dict[str, Any]) -> str:
    """Build a human-readable BURNIE report with verdict (plain Russian)."""
    senti = snapshot["sentiment"]
    if senti == "neg":
        header = "🔴 BURNIE — негативный сентимент"
    elif senti == "pos":
        header = "🟢 BURNIE — позитивный сентимент"
    else:
        header = "⚪ BURNIE — нейтральный сентимент"

    delta = snapshot.get("followers_delta", 0)
    delta_s = f"+{delta}" if delta > 0 else str(delta)
    neg_h = snapshot.get("neg_hits", 0)
    pos_h = snapshot.get("pos_hits", 0)
    toly = snapshot.get("toly_hits", 0)
    ai = snapshot.get("ai_buy_hits", 0)

    mc = snapshot.get("market_cap")
    price = snapshot.get("price_usd")
    chg = snapshot.get("change_24h")
    vol = snapshot.get("volume_24h")

    if mc is not None:
        mc_s = f"${float(mc)/1e6:.1f}M" if float(mc) >= 1e6 else f"${float(mc):,.0f}"
    else:
        mc_s = "N/A"
    price_s = f"${float(price):.6f}" if price is not None else "N/A"
    chg_s = f"{float(chg):+.1f}%" if chg is not None else "?"
    vol_s = f"${float(vol)/1e3:.0f}K" if vol is not None else "N/A"

    lines = [
        header,
        "",
        f"📊 Сентимент: {pos_h} позитивных / {neg_h} негативных постов",
    ]
    if toly:
        lines.append(f"👤 Toly (основатель Solana) упомянут в {toly} постах — это ключевой сигнал.")
    if ai:
        lines.append(f"🤖 AI-боты дают сигнал на покупку: {ai} постов.")
    lines.append(f"👥 Фолловеры: {snapshot.get('followers', 0):,} ({delta_s} за период) | Капитализация: {mc_s}")
    lines.append(f"💵 Цена: {price_s} | За 24ч: {chg_s} | Объём: {vol_s}")

    # Market read
    if chg is not None and mc is not None:
        if float(chg) < -10:
            lines.append("📉 Цена заметно падает — возможен слив, осторожно.")
        elif float(chg) > 10:
            lines.append("📈 Цена растёт — идёт разогрев.")
        else:
            lines.append("➡️ Цена в боковике — рынок ждёт, накопление.")

    neg = snapshot.get("strong_negative") or []
    bull = snapshot.get("strong_bullish") or []
    if neg:
        first = neg[0]
        lines.append("⚠️ Риск: " + explain_terms(first, RISK_TERMS_RU))
        lines.append("   «" + first[:120].rstrip() + "…»")
    elif senti == "pos":
        lines.append("✅ Серьёзных обвинений (скам/слив) не обнаружено.")
    if bull:
        first = next(
            (b for b in bull if explain_terms(b, DRIVER_TERMS_RU) != "нет ключевых слов"),
            bull[0],
        )
        lines.append("🔥 Драйвер: " + explain_terms(first, DRIVER_TERMS_RU))
        lines.append("   «" + first[:120].rstrip() + "…»")

    # Verdict
    lines.append("")
    if senti == "neg":
        lines.append("📌 Вердикт: НЕ СЛЕДИТЬ — негатив растёт, риск слива.")
    elif senti == "pos" and toly >= 5:
        lines.append("📌 Вердикт: СЛЕДИТЬ — Toly активно пишет про BURNIE, сентимент бычий. Листинг на Moonshot близко.")
    elif senti == "pos":
        lines.append("📌 Вердикт: НАБЛЮДАТЬ — сентимент бычий, но явных триггеров нет.")
    else:
        lines.append("📌 Вердикт: НАБЛЮДАТЬ — сигналов недостаточно.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print snapshot without writing JSONL")
    args = parser.parse_args()

    snapshot, strong_negative = build_snapshot()
    dex = fetch_dex_metrics()
    if dex.get("ok"):
        snapshot["market_cap"] = dex.get("market_cap")
        snapshot["price_usd"] = dex.get("price_usd")
        snapshot["volume_24h"] = dex.get("volume_24h")
        snapshot["liquidity_usd"] = dex.get("liquidity_usd")
        snapshot["change_24h"] = dex.get("change_24h")
    if args.dry_run:
        print(json.dumps(snapshot, ensure_ascii=False, indent=2))
        return 0

    append_jsonl(OUTFILE, snapshot)
    if snapshot["sentiment"] in ("neg", "pos"):
        print(format_alert(snapshot))
    else:
        print("[SILENT]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
