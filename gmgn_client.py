"""GMGN OpenAPI enrichment client for RAB9 MSF pipeline.

Uses official gmgn-cli (read-only). Never executes swap/trade.
If CLI/API unavailable → silent skip (never blocks MSF delivery).

Usage:
    from gmgn_client import get_smart_money_score, enrich_token, format_for_grok
    score = get_smart_money_score("CGEDT9...")          # 0–15 or None
    report = enrich_token("CGEDT9...")                  # full dict
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

TIMEOUT = 25
DEFAULT_CHAIN = "sol"
logger = logging.getLogger("rab9.gmgn")

# Prefer absolute path — systemd PATH may not include hermes node bin
_GMGN_CLI_CANDIDATES = (
    os.environ.get("GMGN_CLI"),
    "/home/hermes-workspace/.hermes/node/bin/gmgn-cli",
    str(Path.home() / ".hermes/node/bin/gmgn-cli"),
    shutil.which("gmgn-cli"),
    "gmgn-cli",
)

# Holder tags that count as smart-money / quality signal
_SMART_TAGS = frozenset(
    {
        "smart",
        "smart_degen",
        "smart_money",
        "smartmoney",
        "kol",
        "whale",
        "vc",
        "fresh_wallet",  # mixed; counted lightly via weight below
    }
)
_QUALITY_TAGS = frozenset({"smart", "smart_degen", "smart_money", "smartmoney", "kol", "whale", "vc"})
_RISK_TAGS = frozenset({"bundler", "sniper", "rat_trader", "bot", "sandwich"})

# LP / market-maker / insider — исключать из top-holder анализа (rugradar-паттерн)
# Иначе пул (addr_type=2, exchange=pump_amm) считается «самым большим холдером».
_LP_MM_TAGS = frozenset(
    {
        "pool",
        "lp",
        "liquidity",
        "liquidity_pool",
        "amm",
        "market_maker",
        "mm",
        "bonding_curve",
        "vault",
        "program",
        "router",
        "dex",
    }
)
_INSIDER_TAGS = frozenset({"creator", "dev_team", "team", "insider", "deployer"})
# addr_type: 0=wallet, 2=pool/contract (наблюдение GMGN BURNIE)
_POOL_ADDR_TYPES = frozenset({2, "2"})


def _cli_path() -> str | None:
    for c in _GMGN_CLI_CANDIDATES:
        if not c:
            continue
        if c == "gmgn-cli" or Path(c).is_file():
            return c
    return None


def _run_cli(args: list[str], timeout: int = TIMEOUT) -> dict[str, Any] | list[Any] | None:
    """Run gmgn-cli with --raw. Returns parsed JSON or None on any failure."""
    cli = _cli_path()
    if not cli:
        logger.debug("gmgn-cli not found — silent skip")
        return None
    try:
        proc = subprocess.run(
            [cli, *args, "--raw"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "PATH": f"/home/hermes-workspace/.hermes/node/bin:{os.environ.get('PATH', '')}"},
        )
    except Exception as e:
        logger.debug("gmgn-cli spawn failed: %s", e)
        return None

    raw = (proc.stdout or "").strip()
    if not raw:
        logger.debug("gmgn-cli empty stdout (exit=%s stderr=%s)", proc.returncode, (proc.stderr or "")[:120])
        return None
    try:
        data: Any = json.loads(raw)
    except json.JSONDecodeError:
        # some versions may wrap / emit mixed output
        try:
            start = raw.index("{")
            data, _ = json.JSONDecoder().raw_decode(raw[start:])
        except Exception as e:
            logger.debug("gmgn-cli JSON parse failed: %s", e)
            return None

    if isinstance(data, dict) and data.get("error"):
        logger.debug("gmgn-cli error payload: %s", str(data.get("error"))[:120])
        return None
    if isinstance(data, (dict, list)):
        return data
    return None


def _as_list(payload: dict[str, Any] | list | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ("list", "data", "holders", "traders", "rank", "items"):
            val = payload.get(key)
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
            if isinstance(val, dict):
                for k2 in ("list", "rank", "items"):
                    v2 = val.get(k2)
                    if isinstance(v2, list):
                        return [x for x in v2 if isinstance(x, dict)]
    return []


def _f(val: Any, default: float = 0.0) -> float:
    try:
        if val is None or val == "":
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _collect_tags(item: dict[str, Any]) -> set[str]:
    tags: set[str] = set()
    for key in ("tags", "maker_token_tags", "wallet_tags"):
        raw = item.get(key)
        if isinstance(raw, list):
            for t in raw:
                if t is not None:
                    tags.add(str(t).lower())
        elif isinstance(raw, str) and raw:
            tags.add(raw.lower())
    wtv = item.get("wallet_tag_v2")
    if isinstance(wtv, str) and wtv:
        tags.add(wtv.lower())
    return tags


def _is_excluded_holder(h: dict[str, Any], exclude_insiders: bool = True) -> bool:
    """True если адрес — LP-пул / MM / (опционально) insider.

    Эвристики (без копирования чужого кода):
      - addr_type in {2} — pool/contract
      - non-empty exchange field (pump_amm, meteora_dlmm, …)
      - tags: pool/lp/mm/…
      - tags: creator/dev_team если exclude_insiders
    """
    if not isinstance(h, dict):
        return True
    if h.get("addr_type") in _POOL_ADDR_TYPES:
        return True
    ex = h.get("exchange")
    if isinstance(ex, str) and ex.strip():
        return True
    tags = _collect_tags(h)
    if tags & _LP_MM_TAGS:
        return True
    if exclude_insiders and (tags & _INSIDER_TAGS):
        return True
    return False


def filter_organic_holders(
    holders: list[dict[str, Any]],
    *,
    exclude_insiders: bool = True,
    top_n: int = 10,
) -> dict[str, Any]:
    """Отфильтровать LP/MM/insider из списка holders.

    Returns:
        organic: list holders (filtered)
        excluded: list of {address, reason, pct}
        top10_organic_pct: float 0–100 (сумма amount_percentage топ-N organic)
        excluded_count: int
    """
    organic: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for h in holders:
        if _is_excluded_holder(h, exclude_insiders=exclude_insiders):
            tags = _collect_tags(h)
            reason = "pool/lp"
            if h.get("addr_type") in _POOL_ADDR_TYPES:
                reason = "addr_type_pool"
            elif isinstance(h.get("exchange"), str) and h.get("exchange").strip():
                reason = f"exchange:{h.get('exchange')}"
            elif tags & _INSIDER_TAGS:
                reason = "insider"
            elif tags & _LP_MM_TAGS:
                reason = "lp_mm_tag"
            pct = _f(h.get("amount_percentage"))
            if pct <= 1:
                pct *= 100
            excluded.append(
                {
                    "address": (h.get("address") or "")[:16],
                    "reason": reason,
                    "pct": round(pct, 2),
                }
            )
        else:
            organic.append(h)

    top_pct = 0.0
    for h in organic[: max(1, top_n)]:
        p = _f(h.get("amount_percentage"))
        if p <= 1:
            p *= 100
        top_pct += p

    return {
        "organic": organic,
        "excluded": excluded,
        "top10_organic_pct": round(top_pct, 2),
        "excluded_count": len(excluded),
        "organic_count": len(organic),
    }


def _score_from_enrichment(
    info: dict[str, Any] | None,
    security: dict[str, Any] | None,
    holders: list[dict[str, Any]],
) -> int:
    """Deterministic 0–15 smart-money / quality score from OpenAPI payloads."""
    score = 5  # neutral base
    security = security or {}
    info = info or {}

    # ── Security adjustments ──
    if security.get("is_honeypot") or security.get("honeypot") in (1, True, "1"):
        return 0
    if security.get("is_show_alert") is True:
        score -= 3

    if security.get("renounced_mint") is True:
        score += 1
    if security.get("renounced_freeze_account") is True:
        score += 1

    top10 = _f(security.get("top_10_holder_rate"))
    # GMGN returns fraction 0–1
    if top10 > 1:
        top10 = top10 / 100.0
    if top10 > 0:
        if top10 < 0.15:
            score += 2
        elif top10 < 0.25:
            score += 1
        elif top10 > 0.50:
            score -= 3
        elif top10 > 0.35:
            score -= 1

    burn = str(security.get("burn_status") or "").lower()
    if burn == "burn":
        score += 1
    lock = security.get("lock_summary") or {}
    if isinstance(lock, dict) and lock.get("is_locked"):
        score += 1

    # ── Holder tag signals (только organic: без LP/пулов) ──
    filtered = filter_organic_holders(holders, exclude_insiders=False, top_n=50)
    organic = filtered["organic"]
    quality_hits = 0
    risk_hits = 0
    suspicious = 0
    for h in organic[:50]:
        tags = _collect_tags(h)
        if tags & _QUALITY_TAGS:
            quality_hits += 1
        if tags & _RISK_TAGS:
            risk_hits += 1
        if h.get("is_suspicious") is True:
            suspicious += 1

    if quality_hits >= 5:
        score += 5
    elif quality_hits >= 3:
        score += 3
    elif quality_hits >= 1:
        score += 1

    if risk_hits >= 10:
        score -= 3
    elif risk_hits >= 5:
        score -= 2
    elif risk_hits >= 2:
        score -= 1

    if suspicious >= 5:
        score -= 2

    # ── Liquidity / holders from info ──
    liq = _f(info.get("liquidity"))
    holders_n = int(_f(info.get("holder_count")))
    if liq >= 100_000:
        score += 1
    if holders_n >= 1000:
        score += 1
    elif holders_n > 0 and holders_n < 50:
        score -= 1

    return max(0, min(15, score))


def enrich_token(mint: str, chain: str = DEFAULT_CHAIN) -> dict[str, Any]:
    """Full read-only enrichment via gmgn-cli.

    Returns dict with ok, smart_money_score, info, security, holders summary.
    Never raises; ok=False on total failure.
    """
    mint = (mint or "").strip()
    if not mint:
        return {"ok": False, "error": "empty_mint", "smart_money_score": None}

    info = _run_cli(["token", "info", "--chain", chain, "--address", mint])
    security = _run_cli(["token", "security", "--chain", chain, "--address", mint])
    holders_raw = _run_cli(["token", "holders", "--chain", chain, "--address", mint])
    holders = _as_list(holders_raw if isinstance(holders_raw, dict) else {"list": holders_raw})

    if not info and not security and not holders:
        return {"ok": False, "error": "no_data", "smart_money_score": None, "source": "gmgn-cli"}

    score = _score_from_enrichment(
        info if isinstance(info, dict) else None,
        security if isinstance(security, dict) else None,
        holders,
    )

    # ── Top-holder filter: LP / MM / insider ──
    # exclude_insiders=True для organic top10; tag_counts считает и insiders из raw
    filtered = filter_organic_holders(holders, exclude_insiders=True, top_n=10)
    organic = filtered["organic"]

    # Compact holder risk summary (organic + помечаем excluded)
    tag_counts: dict[str, int] = {}
    for h in holders[:50]:
        for t in _collect_tags(h):
            if t in _QUALITY_TAGS or t in _RISK_TAGS or t in {"creator", "dev_team", "top_holder"}:
                tag_counts[t] = tag_counts.get(t, 0) + 1

    def _holder_row(h: dict[str, Any]) -> dict[str, Any]:
        pct_raw = _f(h.get("amount_percentage"))
        return {
            "address": (h.get("address") or "")[:12],
            "usd": round(_f(h.get("usd_value")), 0),
            "pct": round(pct_raw * 100, 2) if pct_raw <= 1 else round(pct_raw, 2),
            "tags": sorted(_collect_tags(h))[:6],
        }

    # top_holders = organic only (не пул, не creator)
    top_holders = [_holder_row(h) for h in organic[:5]]
    # raw_top для отладки: первые 5 без фильтра (чтобы видеть пул)
    raw_top_holders = [_holder_row(h) for h in holders[:5]]

    sec = security if isinstance(security, dict) else {}
    inf = info if isinstance(info, dict) else {}

    # Organic top10 override для security.top10 если GMGN rate включает пулы
    top10_raw = _f(sec.get("top_10_holder_rate"))
    top10_organic = filtered["top10_organic_pct"]
    # GMGN rate fraction 0–1 → percent for comparison
    top10_raw_pct = top10_raw * 100 if 0 < top10_raw <= 1 else top10_raw

    return {
        "ok": True,
        "source": "gmgn-openapi",
        "chain": chain,
        "address": mint,
        "smart_money_score": score,
        "symbol": inf.get("symbol") or "?",
        "name": inf.get("name") or "?",
        "holder_count": int(_f(inf.get("holder_count"))),
        "liquidity": _f(inf.get("liquidity")),
        "launchpad": inf.get("launchpad") or inf.get("launchpad_platform"),
        "security": {
            "honeypot": bool(sec.get("is_honeypot") or sec.get("honeypot") in (1, True, "1")),
            "alert": bool(sec.get("is_show_alert")),
            "top10": top10_raw,
            "top10_organic_pct": top10_organic,  # без LP/MM/insider
            "renounced_mint": sec.get("renounced_mint"),
            "renounced_freeze": sec.get("renounced_freeze_account"),
            "burn_status": sec.get("burn_status"),
            "locked": bool((sec.get("lock_summary") or {}).get("is_locked"))
            if isinstance(sec.get("lock_summary"), dict)
            else False,
            "buy_tax": sec.get("buy_tax"),
            "sell_tax": sec.get("sell_tax"),
        },
        "tag_counts": tag_counts,
        "top_holders": top_holders,
        "raw_top_holders": raw_top_holders,
        "holders_filter": {
            "excluded_count": filtered["excluded_count"],
            "organic_count": filtered["organic_count"],
            "top10_organic_pct": top10_organic,
            "top10_raw_pct": round(top10_raw_pct, 2) if top10_raw_pct else None,
            "excluded_sample": filtered["excluded"][:5],
        },
    }


def get_smart_money_score(mint: str, chain: str = DEFAULT_CHAIN) -> int | None:
    """Return 0–15 smart-money/quality score or None if GMGN unavailable.

    Kept for meme_score.score_whale / msf_analysis compatibility.
    """
    report = enrich_token(mint, chain=chain)
    if not report.get("ok"):
        return None
    score = report.get("smart_money_score")
    return int(score) if score is not None else None


def _track_list(kind: str, chain: str = DEFAULT_CHAIN, limit: int = 100) -> list[dict[str, Any]]:
    """Fetch track smartmoney|kol list. kind in {smartmoney, kol}."""
    if kind not in ("smartmoney", "kol"):
        return []
    limit = max(1, min(int(limit), 200))
    payload = _run_cli(["track", kind, "--chain", chain, "--limit", str(limit)], timeout=30)
    return _as_list(payload if isinstance(payload, dict) else {"list": payload})


def track_token_flow(mint: str, chain: str = DEFAULT_CHAIN, limit: int = 100) -> dict[str, Any]:
    """Match mint against recent smartmoney + KOL trade feeds (read-only).

    Returns buys/sells counts, USD volume, sample makers. Fail-open.
    """
    mint = (mint or "").strip()
    if not mint:
        return {"ok": False, "error": "empty_mint"}

    sm_all = _track_list("smartmoney", chain=chain, limit=limit)
    kol_all = _track_list("kol", chain=chain, limit=limit)

    if not sm_all and not kol_all:
        return {"ok": False, "error": "track_empty", "source": "gmgn-cli"}

    def _match(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out = []
        for it in items:
            base = (it.get("base_address") or it.get("token_address") or it.get("address") or "").strip()
            if base.lower() == mint.lower():
                out.append(it)
        return out

    sm_hits = _match(sm_all)
    kol_hits = _match(kol_all)

    def _side_stats(hits: list[dict[str, Any]]) -> dict[str, Any]:
        buys = sells = 0
        usd_buy = usd_sell = 0.0
        makers: list[str] = []
        for h in hits:
            side = str(h.get("side") or "").lower()
            usd = _f(h.get("amount_usd"))
            maker = h.get("maker") or ""
            if maker and maker not in makers:
                makers.append(maker)
            if side == "buy":
                buys += 1
                usd_buy += usd
            elif side == "sell":
                sells += 1
                usd_sell += usd
        return {
            "buys": buys,
            "sells": sells,
            "usd_buy": round(usd_buy, 2),
            "usd_sell": round(usd_sell, 2),
            "makers": makers[:10],
            "hits": len(hits),
        }

    sm_stats = _side_stats(sm_hits)
    kol_stats = _side_stats(kol_hits)
    signal = "none"
    if sm_stats["hits"] or kol_stats["hits"]:
        net = (sm_stats["usd_buy"] + kol_stats["usd_buy"]) - (sm_stats["usd_sell"] + kol_stats["usd_sell"])
        if net > 0 and (sm_stats["buys"] + kol_stats["buys"]) > 0:
            signal = "accumulation"
        elif net < 0 and (sm_stats["sells"] + kol_stats["sells"]) > 0:
            signal = "distribution"
        else:
            signal = "mixed"

    return {
        "ok": True,
        "source": "gmgn-openapi-track",
        "chain": chain,
        "address": mint,
        "smartmoney": sm_stats,
        "kol": kol_stats,
        "signal": signal,
        "window_scanned": {"smartmoney": len(sm_all), "kol": len(kol_all)},
    }


def wallet_stats_score(wallet: str, chain: str = DEFAULT_CHAIN, period: str = "7d") -> dict[str, Any]:
    """Score a wallet via portfolio stats (0–100 proxy for wallet-score skill).

    Supplement only — does NOT classify cabal. Fail-open.
    """
    wallet = (wallet or "").strip()
    if not wallet:
        return {"ok": False, "error": "empty_wallet"}

    period = period if period in ("7d", "30d") else "7d"
    stats = _run_cli(
        ["portfolio", "stats", "--chain", chain, "--wallet", wallet, "--period", period],
        timeout=30,
    )
    if not isinstance(stats, dict) or not stats:
        return {"ok": False, "error": "stats_empty", "wallet": wallet}

    # CLI may return single object or list under data
    if "wallet_address" not in stats and isinstance(stats.get("data"), list) and stats["data"]:
        stats = stats["data"][0] if isinstance(stats["data"][0], dict) else stats
    if "wallet_address" not in stats and isinstance(stats.get("list"), list) and stats["list"]:
        stats = stats["list"][0] if isinstance(stats["list"][0], dict) else stats

    pnl = stats.get("pnl_stat") or {}
    common = stats.get("common") or {}
    tags = common.get("tags") if isinstance(common, dict) else []
    if not isinstance(tags, list):
        tags = []

    winrate = _f(pnl.get("winrate"))
    token_num = int(_f(pnl.get("token_num")))
    realized_pnl = _f(stats.get("realized_profit_pnl"))
    buys = int(_f(stats.get("buy")))
    sells = int(_f(stats.get("sell")))

    # Deterministic 0–100 proxy score
    score = 40
    if winrate >= 0.7:
        score += 25
    elif winrate >= 0.55:
        score += 15
    elif winrate >= 0.45:
        score += 5
    elif winrate > 0 and winrate < 0.35:
        score -= 15

    if realized_pnl >= 1.0:
        score += 20
    elif realized_pnl >= 0.3:
        score += 12
    elif realized_pnl >= 0.0:
        score += 3
    elif realized_pnl < -0.3:
        score -= 15

    if token_num >= 30:
        score += 5
    elif token_num > 0 and token_num < 5:
        score -= 5

    tag_l = {str(t).lower() for t in tags}
    if tag_l & {"smart_degen", "smart", "smart_money", "smartmoney", "kol"}:
        score += 15
    if tag_l & {"bot", "sandwich", "bundler"}:
        score -= 10

    score = max(0, min(100, score))
    tier = "HIGH" if score >= 75 else "MID" if score >= 50 else "LOW"

    return {
        "ok": True,
        "source": "gmgn-portfolio-stats",
        "wallet": wallet,
        "period": period,
        "score": score,
        "tier": tier,
        "winrate": round(winrate, 3),
        "realized_profit_pnl": round(realized_pnl, 3),
        "realized_profit_usd": round(_f(stats.get("realized_profit")), 2),
        "buys": buys,
        "sells": sells,
        "token_num": token_num,
        "tags": [str(t) for t in tags][:10],
        "avg_holding_period": pnl.get("avg_holding_period"),
    }


def score_wallets(wallets: list[str], chain: str = DEFAULT_CHAIN, max_wallets: int = 5) -> dict[str, Any]:
    """Batch wallet_stats_score for top makers. Caps API calls."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for w in wallets:
        addr = (w or "").strip()
        if not addr or addr in seen:
            continue
        seen.add(addr)
        rep = wallet_stats_score(addr, chain=chain)
        if rep.get("ok"):
            out.append(rep)
        if len(out) >= max_wallets:
            break
    return {
        "ok": bool(out),
        "source": "gmgn-wallet-batch",
        "count": len(out),
        "wallets": out,
    }


def format_track_for_grok(track: dict[str, Any] | None) -> str:
    if not track or not track.get("ok"):
        return "GMGN track: no smartmoney/KOL hits for this mint in recent window"

    sm = track.get("smartmoney") or {}
    kol = track.get("kol") or {}
    win = track.get("window_scanned") or {}
    lines = [
        f"GMGN track signal: {track.get('signal')} (scanned SM={win.get('smartmoney')} KOL={win.get('kol')})",
        f"SmartMoney: hits={sm.get('hits')} buys={sm.get('buys')} sells={sm.get('sells')} "
        f"usd_buy=${_f(sm.get('usd_buy')):,.0f} usd_sell=${_f(sm.get('usd_sell')):,.0f}",
        f"KOL: hits={kol.get('hits')} buys={kol.get('buys')} sells={kol.get('sells')} "
        f"usd_buy=${_f(kol.get('usd_buy')):,.0f} usd_sell=${_f(kol.get('usd_sell')):,.0f}",
    ]
    makers = (sm.get("makers") or [])[:3] + (kol.get("makers") or [])[:2]
    if makers:
        lines.append("Sample makers: " + ", ".join(m[:10] + "…" for m in makers[:5]))
    return "\n".join(lines)


def format_wallets_for_grok(batch: dict[str, Any] | None) -> str:
    if not batch or not batch.get("ok") or not batch.get("wallets"):
        return "GMGN wallet-score: no stats"
    lines = ["GMGN wallet-score (portfolio stats proxy, NOT cabal override):"]
    for w in batch.get("wallets") or []:
        lines.append(
            f"  • {str(w.get('wallet',''))[:8]}… score={w.get('score')}/100 ({w.get('tier')}) "
            f"WR={_f(w.get('winrate')):.0%} PnL={_f(w.get('realized_profit_pnl')):.0%} "
            f"b/s={w.get('buys')}/{w.get('sells')} tags={w.get('tags')}"
        )
    lines.append("NOTE: supplement only — cabal P≥80% remains authoritative.")
    return "\n".join(lines)


def format_for_grok(score_or_report: int | dict[str, Any] | None) -> str:
    """Format GMGN result for Grok context. Accepts int score or full report dict."""
    if score_or_report is None:
        return "GMGN: no data"

    if isinstance(score_or_report, int):
        level = "strong" if score_or_report >= 10 else "moderate" if score_or_report >= 5 else "weak"
        return f"GMGN smart-money: {score_or_report}/15 ({level}) [openapi]"

    if not isinstance(score_or_report, dict):
        return "GMGN: no data"

    if not score_or_report.get("ok"):
        return f"GMGN: unavailable ({score_or_report.get('error', '?')})"

    score = int(score_or_report.get("smart_money_score") or 0)
    level = "strong" if score >= 10 else "moderate" if score >= 5 else "weak"
    sec = score_or_report.get("security") or {}
    tags = score_or_report.get("tag_counts") or {}
    tag_str = ", ".join(f"{k}={v}" for k, v in sorted(tags.items(), key=lambda x: -x[1])[:8]) or "none"

    top10 = sec.get("top10")
    top10_pct = None
    if top10 is not None:
        t = _f(top10)
        top10_pct = t * 100 if t <= 1 else t

    lines = [
        f"GMGN OpenAPI score: {score}/15 ({level})",
        f"Token: {score_or_report.get('symbol')} | holders={score_or_report.get('holder_count')} "
        f"| liq=${_f(score_or_report.get('liquidity')):,.0f}"
        + (f" | launchpad={score_or_report.get('launchpad')}" if score_or_report.get("launchpad") else ""),
        "Security: "
        + f"honeypot={sec.get('honeypot')} alert={sec.get('alert')} "
        + (f"top10={top10_pct:.1f}% " if top10_pct is not None else "")
        + f"renounce_mint={sec.get('renounced_mint')} freeze={sec.get('renounced_freeze')} "
        + f"burn={sec.get('burn_status')} locked={sec.get('locked')}",
        f"Holder tags (top50): {tag_str}",
    ]
    tops = score_or_report.get("top_holders") or []
    if tops:
        parts = []
        for t in tops[:3]:
            parts.append(
                f"{t.get('address')}… ${t.get('usd'):,.0f} ({t.get('pct')}%) tags={t.get('tags')}"
            )
        lines.append("Top holders (organic, no LP/MM/insider): " + " | ".join(parts))
    hf = score_or_report.get("holders_filter") or {}
    if hf.get("excluded_count"):
        lines.append(
            f"Holders filter: excluded={hf.get('excluded_count')} "
            f"top10_organic={hf.get('top10_organic_pct')}% "
            f"(raw={hf.get('top10_raw_pct')}%)"
        )
    # organic top10 in security block if present
    if sec.get("top10_organic_pct") is not None:
        lines.append(f"top10 organic (no LP/insider): {sec.get('top10_organic_pct')}%")
    lines.append("NOTE: read-only enrichment. No swap/trade executed.")
    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: gmgn_client.py <mint> [chain]"}))
        sys.exit(1)
    chain = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_CHAIN
    mint = sys.argv[1]
    report = enrich_token(mint, chain=chain)
    track = track_token_flow(mint, chain=chain, limit=50)
    print(json.dumps({"token": report, "track": track}, ensure_ascii=False, indent=2))
    print("---")
    print(format_for_grok(report))
    print(format_track_for_grok(track))
    sys.exit(0 if report.get("ok") else 1)
