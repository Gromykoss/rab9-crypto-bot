import re
import os
import sys
import json

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


def get_token_address_from_dex(address: str) -> str | None:
    """Try DexScreener pair endpoint to extract base token address.
    Handles pair addresses (pumpswap/raydium) that Birdeye can't resolve.
    """
    try:
        import requests
        from config import DEXSCREENER_BASE_URL
        r = requests.get(
            f"{DEXSCREENER_BASE_URL}/latest/dex/pairs/solana/{address}",
            timeout=10,
        )
        if r.ok:
            data = r.json()
            pairs = data.get("pairs") or []
            if isinstance(data, dict) and not pairs:
                pairs = [data] if data.get("pairAddress") else []
            for p in pairs:
                base = p.get("baseToken") or {}
                tok_addr = base.get("address")
                if tok_addr and tok_addr != address and is_msf_solana_address(tok_addr):
                    return tok_addr
    except Exception:
        pass
    return None


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


def build_compact_analysis_text(address: str, mode: str = "full"):
    """Compact analysis for auto-respond.

    Modes:
      - \"full\": all sections (makers, wallet intel, AI, verdict)
      - \"summary\": one-line header + wallet intel + AI summary + verdict (no maker list)
    """
    import requests
    from config import BIRDEYE_API_KEY

    theory_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trading_theory.md")
    try:
        with open(theory_path, "r", encoding="utf-8") as f:
            trading_theory = f.read().strip()
    except OSError:
        trading_theory = ""

    # Initialize enrichment contexts (filled later by radars)
    score_context = ""
    radar_context = ""
    chart_context = ""
    onchain_context = ""
    creator_context = ""

    # Get actual token address from DexScreener (pair → token) FIRST
    token_addr = get_token_address_from_dex(address) or address

    pair_resolve_text = build_pair_resolve_text(address)
    pair = extract_recommended_pair(pair_resolve_text)

    if not pair:
        pair = address  # fallback: use input as pair (may work with Birdeye pair trades)

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
                params={"address": token_addr},
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

    # ── DEX + name fallback (DexScreener for PumpSwap tokens Birdeye misses) ──
    for line in pair_resolve_text.splitlines():
        if line.startswith("#1") and dex == "?" and "dex:" in line:
            dex_val = line.split("dex:", 1)[1].split("|")[0].strip() if "dex:" in line else "?"
            if dex_val and dex_val != "n/a":
                dex = dex_val
        # Extract token name from DexScreener pair resolve: "name: TOKEN"
        if token_name == "?" and "name:" in line and "base " in line:
            name_part = line.split("name:", 1)[1].strip()
            if name_part and name_part != "n/a" and len(name_part) <= 30:
                token_name = name_part

    buy_heavy = len([m for m in makers if m.get("net_direction") == "buy-heavy"])
    sell_heavy = len([m for m in makers if m.get("net_direction") == "sell-heavy"])
    mixed = len([m for m in makers if m.get("net_direction") == "mixed"])

    # ── Wallet intel ──
    cabal = _get_cabal()
    xref = cross_reference_makers(makers, cabal)
    cabal_count = xref.get("cabal_count", 0)
    total_matched = len(xref.get("known", []))
    infra_count = len(xref.get("infrastructure", []))

    # ── Kabal per top-5 ──
    cabal_wallets = {addr.lower(): info for addr, info in cabal.items()} if cabal else {}
    top5_kabal_count = sum(
        1 for m in makers[:5] if m["wallet"].lower() in cabal_wallets
    )

    # ── Build output lines ──
    lines = []

    if mode == "summary":
        # Compact one-line header
        top5 = makers[:5]
        ratio_str = f" ({buy_heavy}b/{sell_heavy}s)"
        kabal_str = f"kabals:{top5_kabal_count}" if top5_kabal_count > 0 else ""
        header_parts = [f"🔍 {token_name} | MC: {token_mc}"]
        if dex != "?":
            header_parts.append(f"DEX: {dex}")
        if ratio_str.strip(" ()"):
            header_parts.append(f"{buy_heavy}b/{sell_heavy}s")
        if kabal_str:
            header_parts.append(kabal_str)
        lines.append(" | ".join(header_parts))

        # Wallet intel — one line
        if xref.get("summary"):
            lines.append(f"💰 Кошельки: {total_matched}/{len(makers)} known ({cabal_count} kabal + {infra_count} infra)")
    else:
        # Full mode — header
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
            lines.append(f"Всего: {total_matched} кошельков найдено ({cabal_count} кабалов + {infra_count} инфраструктура)")

    # ── Token X account lookup (from DexScreener socials) ──
    x_account_info = ""
    try:
        import requests as req
        dr = req.get(
            f"https://api.dexscreener.com/latest/dex/pairs/solana/{address}",
            timeout=10,
        )
        if dr.ok:
            pairs = dr.json().get("pairs", [])
            if pairs:
                socials = pairs[0].get("info", {}).get("socials", [])
                for s in socials:
                    if s.get("type") == "twitter":
                        handle = s.get("url", "").rstrip("/").split("/")[-1].split("?")[0]
                        if handle and handle not in ("?", "twitter.com", ""):
                            from radar_x import _load_oauth, lookup_account
                            acc = lookup_account(handle)
                            if acc:
                                x_account_info = f"X: @{acc['username']} — {acc['followers']:,} подписчиков, {acc['tweets']:,} твитов"
                                # Check community sentiment file
                                sentiment_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "community_sentiment.jsonl")
                                if os.path.exists(sentiment_file):
                                    with open(sentiment_file) as sf:
                                        sf_lines = sf.readlines()
                                        if sf_lines:
                                            last = json.loads(sf_lines[-1])
                                            x_account_info += f" | sentiment: {last.get('sentiment','?')}"
                        break
    except Exception:
        pass
    try:
        import os, subprocess
        rab9_dir = os.path.dirname(os.path.abspath(__file__))
        venv_python = os.path.join(rab9_dir, "venv", "bin", "python3")

        # Build search query: token name + address
        radar_query = f"{token_name} {address}" if token_name != "?" else address
        # X search: use lowercase for meme coins (Toly tweets "burnie" not "BURNIE")
        x_query = token_name.lower() if token_name != "?" else address[:12]

        # Run radars + chart in parallel
        def _run_radar(script, query):
            try:
                r = subprocess.run(
                    [venv_python, os.path.join(rab9_dir, script), query],
                    capture_output=True, text=True, timeout=15,
                )
                if r.returncode == 0 and r.stdout.strip():
                    return r.stdout.strip()
            except Exception as e:
                print(f"[ENRICH] {script} failed: {e}", file=sys.stderr)
                pass
            return ""

        from concurrent.futures import ThreadPoolExecutor, as_completed
        x_raw = ""
        gh_raw = ""
        chart_raw = ""
        onchain_raw = ""
        creator_raw = ""
        with ThreadPoolExecutor(max_workers=6) as ex:
            futures = {
                ex.submit(_run_radar, "radar_x.py", x_query): "x",
                ex.submit(_run_radar, "radar_gh.py", token_name if token_name != "?" else address): "gh",
                ex.submit(_run_radar, "chart_analysis.py", token_addr): "chart",
                ex.submit(_run_radar, "onchain_check.py", token_addr): "onchain",
                ex.submit(_run_radar, "creator_monitor.py", token_addr): "creator",
            }
            for f in as_completed(futures, timeout=20):
                kind = futures[f]
                try:
                    raw = f.result()
                except Exception as e:
                    print(f"[ENRICH] {kind} future failed: {e}", file=sys.stderr)
                    raw = ""
                if kind == "x":
                    x_raw = raw
                elif kind == "gh":
                    gh_raw = raw
                elif kind == "chart":
                    chart_raw = raw
                elif kind == "onchain":
                    onchain_raw = raw
                elif kind == "creator":
                    creator_raw = raw

        # Run meme_score in-process with chart data already available (avoids subprocess timeout)
        score_raw = ""
        try:
            chart_data_for_score = None
            if chart_raw:
                chart_data_for_score = json.loads(chart_raw)
            from meme_score import compute_score, format_for_grok as fmt_score
            score_result = compute_score(token_addr, chart_data_for_score)
            score_raw = json.dumps(score_result, ensure_ascii=False)
        except Exception as e:
            print(f"[ENRICH] meme_score in-process failed: {e}", file=sys.stderr)

        # Format for Grok
        if x_raw:
            try:
                x_data = json.loads(x_raw)
                from radar_x import format_for_grok as fmt_x
                radar_context += fmt_x(x_data) + "\n"
            except Exception as e:
                print(f"[ENRICH] radar_x format failed: {e}", file=sys.stderr)
                pass
        if gh_raw:
            try:
                gh_data = json.loads(gh_raw)
                from radar_gh import format_for_grok as fmt_gh
                radar_context += fmt_gh(gh_data) + "\n"
            except Exception as e:
                print(f"[ENRICH] radar_gh format failed: {e}", file=sys.stderr)
                pass
        if chart_raw:
            try:
                chart_data = json.loads(chart_raw)
                from chart_analysis import format_for_grok as fmt_chart
                chart_context = fmt_chart(chart_data)
            except Exception as e:
                print(f"[ENRICH] chart_analysis format failed: {e}", file=sys.stderr)
                pass
        if onchain_raw:
            try:
                onchain_data = json.loads(onchain_raw)
                from onchain_check import format_for_grok as fmt_onchain
                onchain_context = fmt_onchain(onchain_data)
            except Exception as e:
                print(f"[ENRICH] onchain_check format failed: {e}", file=sys.stderr)
                pass
        if score_raw:
            try:
                score_data = json.loads(score_raw)
                from meme_score import format_for_grok as fmt_score
                score_context = fmt_score(score_data)
            except Exception as e:
                print(f"[ENRICH] meme_score format failed: {e}", file=sys.stderr)
                pass
        if creator_raw:
            try:
                creator_data = json.loads(creator_raw)
                from creator_monitor import format_for_grok as fmt_creator
                creator_context = fmt_creator(creator_data)
            except Exception as e:
                print(f"[ENRICH] creator_monitor format failed: {e}", file=sys.stderr)
                pass
    except Exception as e:
        print(f"[ENRICH] enrichment block failed: {e}", file=sys.stderr)
        pass

    # ── Verdict (scoring-based for meme coins) ──
    buy_ratio = buy_heavy / max(sell_heavy, 1)
    # Use meme_score tier if available, fall back to old logic
    meme_tier = ""
    if score_context:
        # Extract tier from score_context
        if "HIGH CONVICTION" in score_context:
            meme_tier = "HIGH CONVICTION"
        elif "SOLID" in score_context:
            meme_tier = "SOLID"
        elif "SPECULATIVE" in score_context:
            meme_tier = "SPECULATIVE"
        elif "AVOID" in score_context:
            meme_tier = "AVOID"

    if not makers:
        verdict = "🟡 Нет данных"
    elif meme_tier == "HIGH CONVICTION":
        verdict = "🟢 HIGH CONVICTION"
    elif meme_tier == "SOLID":
        if buy_ratio < 0.3:
            verdict = "🟢 SOLID (pressure watch)"
        else:
            verdict = "🟢 SOLID"
    elif meme_tier == "SPECULATIVE":
        verdict = "🟡 SPECULATIVE"
    elif meme_tier == "AVOID":
        verdict = "⚫ AVOID"
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

    # ── Kabal dump override: if sell >> buy and kabals present, force AVOID ──
    if buy_ratio < 0.5 and top5_kabal_count >= 1:
        verdict = "⚠️ HIGH SELL PRESSURE — WAIT"

    # ── Chart phase adjustment: accumulation=upgrade, markup/decay=penalty ──
    if chart_context:
        chart_lower = chart_context.lower()
        # Accumulation + rising volume = best entry — upgrade
        if "накопление" in chart_lower and "vol ▲" in chart_lower:
            upgrades = {
                "🟡 SPECULATIVE": "🟢 SPECULATIVE (накопление ▲)",
                "🟡 Стоит следить": "🟢 Стоит следить (накопление ▲)",
                "🟡 Под вопросом": "🟡 Стоит следить (накопление ▲)",
                "⚫ Проходной": "🟡 Под вопросом (накопление ▲)",
                "⚫ AVOID": "🟡 SPECULATIVE (накопление ▲)",
            }
            if verdict in upgrades:
                verdict = upgrades[verdict]
        # Markup = already pumped, downgrade
        elif "разгон" in chart_lower or "markup" in chart_lower:
            downgrades = {
                "🟢 HIGH CONVICTION": "🟡 HIGH CONVICTION (markup — поздно)",
                "🟢 SOLID (pressure watch)": "🟡 SOLID (markup — поздно)",
                "🟢 SOLID": "🟡 SOLID (markup — поздно)",
                "🟢 Стоит следить": "🟡 Стоит следить (markup — поздно)",
                "🟡 SPECULATIVE": "⚫ SPECULATIVE (markup — поздно)",
            }
            if verdict in downgrades:
                verdict = downgrades[verdict]
        # Decay = dying, hard avoid
        elif "decay" in chart_lower or "затухание" in chart_lower:
            downgrades = {
                "🟢 HIGH CONVICTION": "🟡 SOLID (chart: decay)",
                "🟢 SOLID (pressure watch)": "🟡 SPECULATIVE (chart: decay)",
                "🟢 SOLID": "🟡 SPECULATIVE (chart: decay)",
                "🟡 SPECULATIVE": "⚫ AVOID (chart: decay)",
                "🟡 Стоит следить": "⚫ Проходной (chart: decay)",
                "🟡 Под вопросом": "⚫ Проходной (chart: decay)",
            }
            if verdict in downgrades:
                verdict = downgrades[verdict]
        # Distribution = selling, downgrade (but don't kill SPECULATIVE — it's a timing signal, not terminal)
        elif "distribution" in chart_lower or "раздача" in chart_lower:
            downgrades = {
                "🟢 HIGH CONVICTION": "🟡 SOLID (chart: distribution)",
                "🟢 SOLID (pressure watch)": "🟡 SPECULATIVE (chart: distribution)",
                "🟢 SOLID": "🟡 SPECULATIVE (chart: distribution)",
                "🟡 SPECULATIVE": "🟡 SPECULATIVE (chart: distribution — wait)",  # Skill: "Wait" pattern, not AVOID
            }
            if verdict in downgrades:
                verdict = downgrades[verdict]

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

    # ── Grok analytical summary ──
    grok_summary = ""
    try:
        # Fable 5 style: goal + why + effort before data
        grok_prompt = (
            "GOAL: Быстрый анализ мемкоина для трейдера — решение вход/выход/ждать. "
            "EFFORT: High. Используй trading theory как аналитическую рамку, не как чеклист. "
            "Контекст: трейдеру нужно понять манипуляции кабалов, стадию жизненного цикла, "
            "риски on-chain и реальный ли интерес сообщества.\n\n"
            f"ДАННЫЕ: Токен {token_name}, MC {token_mc}, DEX {dex}. "
            f"Мейкеров: {len(makers)} ({buy_heavy} buy / {sell_heavy} sell / {mixed} mix). "
            f"Buy ratio: {buy_ratio:.1f}. "
            f"Kabals: {total_matched} (в топ-5: {top5_kabal_count}). "
            f"Вердикт системы: {verdict}."
        )
        if x_account_info:
            grok_prompt += f"\n\nАККАУНТ ТОКЕНА: {x_account_info}"
        if radar_context:
            grok_prompt += (
                f"\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ (радар):\n{radar_context}"
                "\n\nИспользуй эти данные чтобы уточнить вывод: есть ли негативные сигналы (rug-pull, scam), "
                "есть ли реальная dev-активность, обсуждается ли токен позитивно или негативно."
            )
        if onchain_context:
            grok_prompt += (
                f"\n\nON-CHAIN АНАЛИЗ:\n{onchain_context}"
            )
        if chart_context:
            grok_prompt += (
                f"\n\nДОЛГОСРОЧНЫЙ ТРЕНД:\n{chart_context}"
            )
        if score_context:
            grok_prompt += (
                f"\n\nСКОРИНГ МЕМКОИНА:\n{score_context}"
                "\n\nИспользуй скор для калибровки вывода: HIGH CONVICTION/SOLID/SPECULATIVE/AVOID."
            )
        if creator_context and "too early" not in creator_context.lower():
            grok_prompt += (
                f"\n\nКОШЕЛЁК СОЗДАТЕЛЯ:\n{creator_context}"
                "\n\nУчти поведение создателя: conviction = НЕ продаёт >7 дней (BULLISH), "
                "selling/dumped = продаёт (BEARISH). Упомяни это в выводе."
            )
        # Wallet intelligence: pass cross-referenced cabal data
        wallet_intel = xref.get("summary", "")
        if wallet_intel:
            grok_prompt += (
                f"\n\nWALLET INTELLIGENCE (кошельки-кабалы):\n{wallet_intel}"
                "\n\nЭто кошельки которые ранее торговали на winner-токенах (MC > $500K). "
                "Если они сейчас SELL-heavy — это кабал сбрасывает. Если BUY-heavy — накапливают."
            )
        if trading_theory:
            grok_prompt += (
                f"\n\nTRADING THEORY RULES:\n{trading_theory}"
                "\n\nИспользуй эти правила как аналитическую рамку для оценки lifecycle, kabal behavior, "
                "on-chain risk и sentiment-price correlation."
            )
        grok_prompt += (
            "\n\nФОРМАТ: 3 предложения на русском, ≤300 символов. Без маркдауна, без нумерации. "
            "1) X/комьюнити — реальный интерес или манипуляция. "
            "2) On-chain + чарт — тренд и риски. "
            "3) Интегрированный вердикт по trading theory. "
            "ПРАВИЛА: buy ratio <0.5 + kabals в топ-5 = coordinated dump. "
            "Не уточняй, не спрашивай — действуй по теории и дай готовый вывод."
        )
        raw = ask_grok(grok_prompt).strip()
        if raw and not raw.lower().startswith("grok"):
            grok_summary = raw.lstrip("•-→0123456789. )")
    except Exception:
        pass

    if grok_summary:
        if mode == "summary":
            lines.append(f"📊 {grok_summary}")
        else:
            lines.append("")
            lines.append("─── AI-анализ ───")
            lines.append(f"📊 {grok_summary}")

    # ── Auto-escalation ──
    concentration = sum(m["trades"] for m in top5) / max(sum(m["trades"] for m in makers), 1)
    should_escalate, escalate_reason, _ = auto_escalation_check(
        len(makers), cabal_count, buy_ratio, concentration
    )
    if should_escalate:
        lines.append(f"⚠️ {escalate_reason}")

    if mode == "summary":
        lines.append(f"{verdict}")
    else:
        lines.append("")
        lines.append("─── Вердикт ───")
        lines.append(f"→ {verdict}")
        lines.append("_Без PnL, без торговых советов._")

    return "\n".join(lines)
