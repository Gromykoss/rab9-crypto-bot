import re

from address_validation import is_msf_solana_address
from maker_sources import build_pair_makers_text

# Wallet intelligence integration (Hermes T-070)
from wallet_intel import (
    load_cabal_library,
    cross_reference_makers,
    delta_compare,
    auto_escalation_check,
)

# Lazy-loaded cabal library
_cabal_library = None


def _get_cabal():
    global _cabal_library
    if _cabal_library is None:
        _cabal_library = load_cabal_library()
    return _cabal_library


def compact(value, left=6, right=4):
    if not value:
        return "n/a"
    text = str(value)
    if len(text) <= left + right + 3:
        return text
    return f"{text[:left]}...{text[-right:]}"


from pair_sources import build_pair_resolve_text
from maker_sources import get_birdeye_pair_makers, summarize_pair_makers
from token_intel import ask_grok


PAIR_RECOMMENDATION_RE = re.compile(r"Use this address for /makertrades:\s*(?P<pair>\S+)")


def extract_recommended_pair(pair_resolve_text: str):
    match = PAIR_RECOMMENDATION_RE.search(pair_resolve_text or "")
    if not match:
        return None

    pair = match.group("pair").strip()
    if not is_msf_solana_address(pair):
        return None

    return pair


def extract_line(text: str, prefix: str):
    for line in (text or "").splitlines():
        if line.startswith(prefix):
            return line
    return None


def build_msf_signal_analysis_text(address: str):
    pair_resolve_text = build_pair_resolve_text(address)
    pair = extract_recommended_pair(pair_resolve_text)

    if not pair:
        return pair_resolve_text

    # Normal mode scan
    pair_makers_text = build_pair_makers_text(pair, mode="normal", show_full=False)
    unique_makers = extract_line(pair_makers_text, "Unique makers:")
    raw_scanned = extract_line(pair_makers_text, "Raw pair trades scanned:")

    # Structured maker data for intelligence
    result = get_birdeye_pair_makers(pair, mode="normal")
    items = result.get("items") or []
    makers = summarize_pair_makers(items)

    # Wallet cross-reference
    cabal = _get_cabal()
    xref = cross_reference_makers(makers, cabal)

    # Delta vs historical scans
    delta = delta_compare(makers, pair)

    # Auto-escalation check
    buy_heavy = len([m for m in makers if m.get("net_direction") == "buy-heavy"])
    sell_heavy = len([m for m in makers if m.get("net_direction") == "sell-heavy"])
    buy_ratio = buy_heavy / max(sell_heavy, 1)
    concentration = sum(m["trades"] for m in makers[:5]) / max(sum(m["trades"] for m in makers), 1)
    should_escalate, escalate_reason, escalate_level = auto_escalation_check(
        len(makers), xref["cabal_count"], buy_ratio, concentration
    )

    summary_lines = [
        "MSF Signal Analysis",
        f"Input: {compact(address)}",
        f"Resolved best pair: {pair}",
        "Pairmakers mode: normal",
    ]

    if unique_makers:
        summary_lines.append(unique_makers)
    if raw_scanned:
        summary_lines.append(raw_scanned)

    # Wallet Intelligence section
    if xref["summary"]:
        summary_lines.extend(["", "─── Wallet Intelligence ───", xref["summary"]])
    if delta["has_history"]:
        summary_lines.extend(["", delta["summary"]])
    if should_escalate:
        summary_lines.extend(["", f"⚠️ Auto-escalation trigger: {escalate_reason}",
                              f"   Рекомендуется: /makertrades {compact(pair)} 50 deep50"])

    summary_lines.extend(
        [
            "Notes: no PnL calculated; no trading advice.",
            "",
            pair_resolve_text,
            "",
            "---",
            "",
            pair_makers_text,
        ]
    )

    return "\n".join(summary_lines)


def build_compact_analysis_text(address: str):
    """Compact analysis for auto-respond: token name, MC, makers, kabals, verdict."""
    import requests
    from config import BIRDEYE_API_KEY

    pair_resolve_text = build_pair_resolve_text(address)
    pair = extract_recommended_pair(pair_resolve_text)

    if not pair:
        return "⚠️ Не удалось определить pair для этого адреса."

    result = get_birdeye_pair_makers(pair, mode="normal")
    items = result.get("items") or []
    makers = summarize_pair_makers(items)

    # ── Token metadata: MC, symbol ──
    token_name = "?"
    token_mc = "?"
    dex = "?"

    if BIRDEYE_API_KEY:
        try:
            meta = requests.get(
                "https://public-api.birdeye.so/defi/token_overview",
                headers={"accept": "application/json", "X-API-KEY": BIRDEYE_API_KEY, "x-chain": "solana"},
                params={"address": address},
                timeout=15,
            )
            if meta.ok:
                data = (meta.json() or {}).get("data") or {}
                token_name = data.get("symbol") or data.get("name") or "?"
                token_mc_raw = data.get("marketCap") or data.get("mc") or data.get("market_cap")
                if token_mc_raw:
                    if token_mc_raw >= 1_000_000:
                        token_mc = f"${token_mc_raw/1_000_000:.1f}M"
                    elif token_mc_raw >= 1_000:
                        token_mc = f"${token_mc_raw/1_000:.0f}K"
                    else:
                        token_mc = f"${token_mc_raw}"
        except Exception:
            pass

    # ── DEX fallback ──
    for line in pair_resolve_text.splitlines():
        if line.startswith("#1") and dex == "?" and "dex:" in line:
            dex_val = line.split("dex:", 1)[1].split("|")[0].strip() if "dex:" in line else "?"
            if dex_val and dex_val != "n/a":
                dex = dex_val

    buy_heavy = len([m for m in makers if m.get("net_direction") == "buy-heavy"])
    sell_heavy = len([m for m in makers if m.get("net_direction") == "sell-heavy"])
    mixed = len([m for m in makers if m.get("net_direction") == "mixed"])

    # ── Wallet intel ──
    cabal = _get_cabal()
    xref = cross_reference_makers(makers, cabal)
    cabal_count = xref.get("cabal_count", 0)

    # ── Kabal per top-5 ──
    cabal_wallets = {addr.lower(): info for addr, info in cabal.items()} if cabal else {}
    top5_kabal_count = sum(
        1 for m in makers[:5] if m["wallet"].lower() in cabal_wallets
    )

    # ── Verdict ──
    buy_ratio = buy_heavy / max(sell_heavy, 1)
    if not makers:
        verdict = "🟡 Нет данных"
    elif token_mc != "?" and token_mc.startswith("$") and float(token_mc.replace("$", "").replace("M", "").replace("K", "")) > 0.5:
        verdict = "🟢 Стоит следить" if cabal_count >= 1 or buy_ratio >= 0.5 else "🟡 Под вопросом"
    elif len(makers) >= 10 and buy_ratio >= 1.5 and cabal_count >= 1:
        verdict = "🟢 Стоит следить"
    elif len(makers) >= 10:
        verdict = "🟡 Стоит следить"
    elif len(makers) >= 5 and buy_ratio >= 1.0:
        verdict = "🟡 Стоит следить"
    else:
        verdict = "⚫ Проходной"

    # ── Fail gracefully if no makers ──
    if not makers:
        header = f"🔍 {token_name} | MC: {token_mc} | DEX: {dex}"
        lines = [
            header,
            f"Pair: {compact(pair)}",
            "",
            "─── Makers ───",
            "⚠️ Мейкеры не найдены — недостаточно данных.",
            "",
            "─── Вердикт ───",
            f"→ {verdict}",
            "_Без PnL, без торговых советов._",
        ]
        return "\n".join(lines)

    # ── Header ──
    lines = [
        f"🔍 {token_name} | MC: {token_mc} | DEX: {dex}",
        f"Pair: {compact(pair)}",
    ]

    # ── Makers section ──
    lines.append("")
    lines.append("─── Makers ───")
    lines.append(f"👥 Всего: {len(makers)} ({buy_heavy} buy / {sell_heavy} sell / {mixed} mix)")

    top5 = makers[:5]
    top5_parts = []
    for i, m in enumerate(top5, 1):
        addr = m["wallet"]
        short = f"{addr[:6]}...{addr[-4:]}" if len(addr) > 10 else addr
        kabal_tag = " Kabal" if addr.lower() in cabal_wallets else ""
        top5_parts.append(f"  {i}. {short} — {m['trades']} trades{kabal_tag}")
    lines.append("Топ-5:")
    lines.extend(top5_parts)

    if top5_kabal_count > 0:
        lines.append(f"⚠️ Kabals в топ-5: {top5_kabal_count}")

    if xref.get("summary"):
        lines.append("")
        lines.append("─── Wallet Intel ───")
        lines.append(xref["summary"])

    # ── Grok analytical summary ──
    grok_summary = ""
    try:
        grok_prompt = (
            f"Токен {token_name}, MC {token_mc}, DEX {dex}. "
            f"Мейкеров: {len(makers)} ({buy_heavy} buy / {sell_heavy} sell / {mixed} mix). "
            f"Buy ratio: {buy_ratio:.1f}. "
            f"Kabals: {cabal_count} (в топ-5: {top5_kabal_count}). "
            f"Вердикт: {verdict}. "
            "Дай ОДНО короткое предложение на русском — аналитический вывод: что происходит с токеном по этим данным, "
            "на что обратить внимание. Без PnL, без «рекомендую», без нумерации."
        )
        raw = ask_grok(grok_prompt).strip()
        if raw and not raw.lower().startswith("grok"):
            grok_summary = raw.lstrip("•-→0123456789. )")
    except Exception:
        pass

    if grok_summary:
        lines.append("")
        lines.append("─── AI-анализ ───")
        lines.append(f"📊 {grok_summary}")

    # ── Auto-escalation ──
    concentration = sum(m["trades"] for m in top5) / max(sum(m["trades"] for m in makers), 1)
    should_escalate, escalate_reason, _ = auto_escalation_check(
        len(makers), cabal_count, buy_ratio, concentration
    )
    if should_escalate:
        lines.append("")
        lines.append(f"⚠️ {escalate_reason}")

    lines.append("")
    lines.append("─── Вердикт ───")
    lines.append(f"→ {verdict}")
    lines.append("_Без PnL, без торговых советов._")

    return "\n".join(lines)
