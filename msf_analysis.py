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
    """Compact analysis for auto-respond: key metrics + wallet intel only."""
    pair_resolve_text = build_pair_resolve_text(address)
    pair = extract_recommended_pair(pair_resolve_text)

    if not pair:
        # Unresolved — return short message
        return "⚠️ Не удалось определить pair для этого адреса."

    result = get_birdeye_pair_makers(pair, mode="normal")
    items = result.get("items") or []
    makers = summarize_pair_makers(items)

    buy_heavy = len([m for m in makers if m.get("net_direction") == "buy-heavy"])
    sell_heavy = len([m for m in makers if m.get("net_direction") == "sell-heavy"])
    mixed = len([m for m in makers if m.get("net_direction") == "mixed"])
    weak = len([m for m in makers if m.get("trades", 0) < 3])

    # Extract token info from pair_resolve_text
    token_symbol = "?"
    dex = "?"
    liq = "?"
    mc = "?"
    for line in pair_resolve_text.splitlines():
        if line.startswith("Token:") and token_symbol == "?":
            token_symbol = line.split(":", 1)[1].strip() if ":" in line else "?"
        if line.startswith("DEX:") or line.startswith("Dex:"):
            dex = line.split(":", 1)[1].strip() if ":" in line else "?"
        if line.startswith("Liq:") or line.startswith("Liquidity:"):
            liq = line.split(":", 1)[1].strip() if ":" in line else "?"

    # Wallet intel
    cabal = _get_cabal()
    xref = cross_reference_makers(makers, cabal)

    # Auto-escalation
    buy_ratio = buy_heavy / max(sell_heavy, 1)
    concentration = sum(m["trades"] for m in makers[:5]) / max(sum(m["trades"] for m in makers), 1)
    should_escalate, escalate_reason, _ = auto_escalation_check(
        len(makers), xref["cabal_count"], buy_ratio, concentration
    )

    # Fail gracefully if no makers found
    if not makers:
        return f"🔍 `{token_symbol}` | {dex} | liq={liq}\n⚠️ Мейкеры не найдены — недостаточно данных."

    lines = [
        f"🔍 **{token_symbol}** | {dex}",
        f"Pair: `{compact(pair)}`",
        f"👥 Makers: {len(makers)} (buy-heavy: {buy_heavy}, sell-heavy: {sell_heavy}, mixed: {mixed})",
    ]

    top5 = makers[:5]
    top5_str = " • ".join(
        f"`{m['wallet'][:6]}…` {m['trades']}t" for m in top5
    )
    lines.append(f"Топ-5: {top5_str}")

    if xref["summary"]:
        lines.append(xref["summary"])

    if should_escalate:
        lines.append(f"⚠️ {escalate_reason} — `/makertrades {compact(pair)} 50 deep50`")

    lines.append("_Без PnL, без торговых советов._")

    return "\n".join(lines)
