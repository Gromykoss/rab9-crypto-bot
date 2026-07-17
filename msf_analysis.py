import re
import os
import sys
import json
import datetime

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
    # Initialize enrichment outputs (filled by radars, may stay empty)
    chart_raw = ""
    onchain_raw = ""
    score_raw = ""
    creator_raw = ""

    try:
        import subprocess
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

    # ── Phase Detector (4-signal model: BUY/ACCUMULATE/SELL/DEAD) ──
    buy_ratio = buy_heavy / max(sell_heavy, 1)

    # Extract meme_score tier
    meme_tier = ""
    if score_context:
        if "HIGH CONVICTION" in score_context:
            meme_tier = "HIGH CONVICTION"
        elif "SOLID" in score_context:
            meme_tier = "SOLID"
        elif "SPECULATIVE" in score_context:
            meme_tier = "SPECULATIVE"
        elif "AVOID" in score_context:
            meme_tier = "AVOID"

    # Prepare phase detector inputs
    chart_data = None
    try:
        if chart_raw:
            chart_data = json.loads(chart_raw)
    except Exception:
        pass

    makers_data = {
        "buy_heavy": buy_heavy,
        "sell_heavy": sell_heavy,
        "count": len(makers),
        "buy_ratio": buy_ratio,
        "kabals_top5": top5_kabal_count,
        "kabals_sell_heavy": sum(
            1 for m in makers[:5]
            if m.get("net_direction") == "sell-heavy" and m["wallet"].lower() in cabal_wallets
        ),
    }

    onchain_data = None
    try:
        if onchain_raw:
            onchain_data = json.loads(onchain_raw)
    except Exception:
        pass

    score_data = None
    try:
        if score_raw:
            score_data = json.loads(score_raw)
    except Exception:
        pass

    # Community sentiment — only for BURNIE
    community_sentiment = "neutral"
    try:
        sentiment_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "community_sentiment.jsonl")
        if os.path.exists(sentiment_path) and token_name.upper() == "BURNIE":
            with open(sentiment_path) as sf:
                sf_lines = sf.readlines()
            if sf_lines:
                last_sentiment = json.loads(sf_lines[-1])
                community_sentiment = last_sentiment.get("sentiment", "neutral")
    except Exception:
        pass

    # Run phase detector
    phase_signal = None
    phase_context = ""
    try:
        from phase_detector import detect as detect_phase, format_for_grok as fmt_phase
        phase_signal = detect_phase(
            chart_data or {},
            makers_data,
            onchain_data or {},
            score_data or {},
            community_sentiment,
        )
    except Exception as e:
        print(f"[PHASE] detector failed: {e}", file=sys.stderr)

    # Verdict from phase detector
    if phase_signal:
        verdict = f"{phase_signal['signal_emoji']} {phase_signal['signal']}"
        if phase_signal.get("phase_label"):
            verdict += f" | {phase_signal['phase_label']}"
        phase_context = fmt_phase(phase_signal) if phase_signal else ""
    else:
        # Fallback: old verdict logic
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

        # Kabal dump override
        if buy_ratio < 0.5 and top5_kabal_count >= 1:
            verdict = "⚠️ HIGH SELL PRESSURE — WAIT"

        # Chart phase adjustments (fallback)
        if chart_context:
            chart_lower = chart_context.lower()
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
            elif "decay" in chart_lower or "затухание" in chart_lower:
                downgrades = {
                    "🟢 HIGH CONVICTION": "🟡 SOLID (chart: decay)",
                    "🟢 SOLID": "🟡 SPECULATIVE (chart: decay)",
                    "🟡 SPECULATIVE": "⚫ AVOID (chart: decay)",
                    "🟡 Стоит следить": "⚫ Проходной (chart: decay)",
                }
                if verdict in downgrades:
                    verdict = downgrades[verdict]
            elif "distribution" in chart_lower or "раздача" in chart_lower:
                downgrades = {
                    "🟢 HIGH CONVICTION": "🟡 SOLID (chart: distribution)",
                    "🟢 SOLID": "🟡 SPECULATIVE (chart: distribution)",
                    "🟡 SPECULATIVE": "🟡 SPECULATIVE (chart: distribution — wait)",
                }
                if verdict in downgrades:
                    verdict = downgrades[verdict]

    # ── Proceed even without makers (Birdeye may be down) ──
    if not makers:
        lines.append("")
        lines.append("─── Makers ───")
        lines.append("⚠️ Мейкеры не найдены (нет данных от источников).")
        # Don't return early — continue to radars + Grok analysis
        # Set safe defaults for maker-dependent variables
        cabal_count = 0
        total_matched = 0
        infra_count = 0
        buy_ratio = buy_heavy / max(sell_heavy, 1) if sell_heavy > 0 else 1.0
        top5_kabal_count = 0

    # ── Grok analytical summary ──
    grok_summary = ""
    try:
        # Fable 5 + STORM: goal + multi-perspective framework
        grok_prompt = (
            "GOAL: Быстрый STORM-анализ мемкоина для трейдера — решение вход/выход/ждать. "
            "EFFORT: High. Используй trading theory как аналитическую рамку, не как чеклист. "
            "Контекст: трейдеру нужно понять манипуляции кабалов, стадию жизненного цикла, "
            "риски on-chain и реальный ли интерес сообщества. "
            "Внутренне применяй Stanford STORM: много перспектив → карта противоречий → синтез.\n\n"
            "STORM STEP 0 — VERIFICATION GATE (ВЫПОЛНИ ДО ОСТАЛЬНЫХ ШАГОВ). "
            "Проверь данные X-аккаунта токена ( АККАУНТ ТОКЕНА ниже). "
            "ЕСЛИ у токена есть X-аккаунт с >1000 followers И живые посты имеют лайки/репосты → комьюнити РЕАЛЬНОЕ. "
            "Vote-spam в Moonshot/FOMO — СТАНДАРТНОЕ поведение мемкоинов, НЕ признак фейка. "
            "НЕ называй комьюнити «фейковым» если у аккаунта живой engagement. "
            "НЕ утверждай про «посты без лайков» не проверив фактические метрики. "
            "Если нет данных об аккаунте — так и напиши: «недостаточно данных о комьюнити».\n\n"
            "STORM STEP 1 — MULTI-PERSPECTIVE SCAN. Проанализируй данные независимо от лица 5 экспертов:\n"
            "PRACTITIONER: рыночная реальность на земле, что не видно в метриках, микро-динамика входа/выхода.\n"
            "SKEPTIC: самые сильные контраргументы, скрытые риски, почему сигнал может быть фейком.\n"
            "ECONOMIST: стимулы, power dynamics, кто зарабатывает, вторичные эффекты.\n"
            "ON-CHAIN SPECIALIST: LP risk, концентрация supply, conviction создателя, metadata/контрактные риски.\n"
            "SENTIMENT ANALYST: реальное комьюнити против манипуляции, fake buzz, инфлюенсерские паттерны. "
            "НО: используй VERIFICATION GATE выше — не называй комьюнити фейковым без проверки аккаунта.\n\n"
            "STORM STEP 2 — CONTRADICTION MAP. Найди, где эксперты расходятся: bullish vs bearish, "
            "сильные vs слабые доказательства, missing data. Ранжируй evidence strength внутренне.\n\n"
            "STORM STEP 3 — SYNTHESIS. Сожми вывод в 3 русских предложения для Telegram; внутренний STORM-анализ не показывай.\n\n"
            f"ДАННЫЕ: Токен {token_name}, MC {token_mc}, DEX {dex}. "
            f"Мейкеров: {len(makers)} ({buy_heavy} buy / {sell_heavy} sell / {mixed} mix). "
            f"Buy ratio: {buy_ratio:.1f}. "
            f"Kabals: {total_matched} (в топ-5: {top5_kabal_count}). "
            f"Вердикт системы: {verdict}."
        )
        if x_account_info:
            grok_prompt = (
                f"АККАУНТ ТОКЕНА (проверь ДО выводов о комьюнити): {x_account_info}\n\n"
                + grok_prompt
            )
        if radar_context:
            grok_prompt += (
                f"\n\nДОПОЛНИТЕЛЬНЫЙ КОНТЕКСТ (радар):\n{radar_context}"
                "\n\nИспользуй эти данные в STORM-перспективах PRACTITIONER, SKEPTIC и SENTIMENT ANALYST: "
                "есть ли негативные сигналы (rug-pull, scam), реальная dev-активность, позитивное/негативное обсуждение."
                "\n\nВАЖНО: 'LISTING CAMPAIGN' и vote-spam в Moonshot/FOMO — НЕ признак фейкового комьюнити, "
                "это стандартная механика листинга мемкоинов. Оценивай комьюнити по X-аккаунту токена, не по vote-spam."
            )
        # Community sentiment history — only for BURNIE (file is BURNIE-specific)
        sentiment_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "community_sentiment.jsonl")
        try:
            if os.path.exists(sentiment_path) and token_name.upper() == "BURNIE":
                with open(sentiment_path) as sf:
                    sf_lines = sf.readlines()
                if sf_lines:
                    last_sentiment = json.loads(sf_lines[-1])
                    sent_ts = last_sentiment.get("ts", "?")
                    sent_label = last_sentiment.get("sentiment", "?")
                    sent_notes = last_sentiment.get("notes", "")[:500]
                    grok_prompt += (
                        f"\n\nCOMMUNITY SENTIMENT TRACKER (последний снимок {sent_ts}):"
                        f"\nsentiment={sent_label}"
                        f"\n{ sent_notes}"
                        "\n\nИспользуй это в SENTIMENT ANALYST: sentiment='pos' = bullish комьюнити, 'neg' = bearish, 'neutral' = без явного тренда."
                    )
        except Exception:
            pass
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
                "\n\nИспользуй скор для калибровки synthesis: HIGH CONVICTION/SOLID/SPECULATIVE/AVOID."
            )
        if phase_context:
            grok_prompt += (
                f"\n\nPHASE DETECTOR (основной торговый сигнал):\n{phase_context}"
                "\n\nЭто definitive trading signal. Согласуй свой synthesis с этим сигналом. "
                "Если сигнал BUY — synthesis bullish. Если SELL — bearish. Если WAIT/ACCUMULATE — neutral/cautious."
            )
        if creator_context and "too early" not in creator_context.lower():
            grok_prompt += (
                f"\n\nКОШЕЛЁК СОЗДАТЕЛЯ:\n{creator_context}"
                "\n\nУчти в ON-CHAIN SPECIALIST: conviction = НЕ продаёт >7 дней (BULLISH), "
                "selling/dumped = продаёт (BEARISH)."
            )
        # Wallet intelligence: pass cross-referenced cabal data
        wallet_intel = xref.get("summary", "")
        if wallet_intel:
            grok_prompt += (
                f"\n\nWALLET INTELLIGENCE (кошельки-кабалы):\n{wallet_intel}"
                "\n\nУчти в PRACTITIONER/SKEPTIC: это кошельки, которые ранее торговали winner-токенами (MC > $500K). "
                "SELL-heavy = кабал сбрасывает; BUY-heavy = накапливают."
            )
        if trading_theory:
            grok_prompt += (
                f"\n\nTRADING THEORY RULES:\n{trading_theory}"
                "\n\nИспользуй эти правила как аналитическую рамку для оценки lifecycle, kabal behavior, "
                "on-chain risk и sentiment-price correlation."
            )
        grok_prompt += (
            "\n\nФОРМАТ ФИНАЛА: строго 3 предложения на русском, общий лимит ≤300 символов. "
            "Без маркдауна, без нумерации, без заголовков, без упоминания STORM или экспертов. "
            "1) X/комьюнити — реальный интерес или манипуляция. "
            "2) On-chain + чарт — тренд и риски. "
            "3) Интегрированный вердикт по trading theory. "
            "ПРАВИЛА: buy ratio <0.5 + kabals в топ-5 = coordinated dump. "
            "Если перспективы конфликтуют, финальный вердикт должен отражать самый сильный риск. "
            "Не уточняй, не спрашивай — действуй по теории и дай готовый вывод."
        )
        raw = ask_grok(grok_prompt).strip()
        if raw and not raw.lower().startswith("grok"):
            grok_summary = raw.lstrip("•-→0123456789. )")
            try:
                grok_log_path = os.path.join(
                    os.path.dirname(__file__),
                    "data",
                    "grok_analyses.jsonl",
                )
                grok_log_entry = {
                    "timestamp": datetime.datetime.now().isoformat(),
                    "token": token_name,
                    "mc": token_mc,
                    "dex": dex,
                    "verdict": verdict,
                    "buy_heavy": buy_heavy,
                    "sell_heavy": sell_heavy,
                    "buy_ratio": buy_ratio,
                    "kabals_top5": top5_kabal_count,
                    "analysis": grok_summary,
                }
                with open(grok_log_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(grok_log_entry, ensure_ascii=False) + "\n")
            except Exception:
                pass
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
