import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class ReuseThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True

from telegram.ext import Application

from address_validation import is_msf_solana_address
from config import RAB9_HTTP_HOST, RAB9_HTTP_PORT, RAB9_HTTP_SECRET, TELEGRAM_GROUP_ID
from msf_analysis import build_compact_analysis_text
from operators import DEFAULT_VERDICT, Verdict, check_destination, check_safety, check_verifier
from utils import split_text


logger = logging.getLogger("rab9_crypto_intel_bot")
SAFETY_INCONCLUSIVE_WARNING = (
    "⚠️ Safety не подтверждена (honeypot/rugcheck недоступны или неоднозначны) — "
    "ручная проверка обязательна."
)


def _verifier_available(verification: dict | None) -> bool:
    if not verification:
        return False

    note = str(verification.get("note") or "").lower()
    unavailable_markers = (
        "verifier unavailable",
        "verifier api error",
        "verifier format error",
        "verifier error",
    )
    return not any(marker in note for marker in unavailable_markers)


async def send_msf_pairresolve(application: Application, address: str):
    logger.info("MSF analysis started for: %s", address)
    destination = check_destination(TELEGRAM_GROUP_ID)
    if destination.verdict != Verdict.ALLOW:
        logger.error("DESTINATION LOCK: send blocked for %s (%s)", TELEGRAM_GROUP_ID, destination.reason)
        return "blocked_destination"

    # ── Cooldown check FIRST — avoid expensive re-analysis ──
    from loop_memory import should_skip, record_analysis
    from msf_dedupe import check_dedupe

    if should_skip(address, cooldown_minutes=15):
        # Prefer rich 24h recap over silent drop
        recap = check_dedupe(address)
        if recap:
            logger.info("COOLDOWN recap sent for %s", address[:12])
            for chunk in split_text(recap):
                await application.bot.send_message(
                    chat_id=TELEGRAM_GROUP_ID,
                    text=chunk,
                    disable_web_page_preview=True,
                )
        else:
            msg = (
                f"🔄 Уже смотрел этот токен <15 мин назад.\n"
                f"Адрес: `{address[:8]}…{address[-4:]}`\n"
                f"🔗 https://dexscreener.com/solana/{address}"
            )
            logger.info("COOLDOWN short notice for %s", address[:12])
            await application.bot.send_message(
                chat_id=TELEGRAM_GROUP_ID,
                text=msg,
                disable_web_page_preview=True,
            )
        return "sent"

    # ── Cabal detection (pre-analysis) ──
    try:
        from cabal_detector import analyze as cabal_check
        cabal = await asyncio.to_thread(cabal_check, address)
        if cabal.get("ok") and cabal.get("phase") in ("CABAL_EXPLOSION", "KOL_ACTIVATION", "PUMPFUN_WHALE_AIRDROP"):
            alert_lines = [
                f"⚠️ КАБАЛ: {cabal.get('token', '?')} (${cabal.get('symbol', '?')})",
                f"Фаза: {cabal['phase']} | Риск: {cabal.get('risk_level', '?')}",
            ]
            for pat in cabal.get("patterns", []):
                for s in pat.get("signals", [])[:3]:
                    alert_lines.append(f"  • {s}")
            alert = "\n".join(alert_lines)
            await application.bot.send_message(
                chat_id=TELEGRAM_GROUP_ID,
                text=alert,
                disable_web_page_preview=True,
            )
            logger.info("CABAL alert sent: %s", cabal["phase"])
    except Exception as e:
        logger.warning("Cabal detector error (continuing): %s", e)

    text, safety_flags = await asyncio.to_thread(build_compact_analysis_text, address, "summary")
    logger.info("MSF analysis complete: %d chars", len(text))

    safety_gate = check_safety(
        safety_flags.get("honeypot"),
        safety_flags.get("rugcheck"),
        safety_flags.get("phase"),
    )
    if safety_gate.verdict == Verdict.DROP:
        logger.warning("SAFETY DROP: suppressing analysis for %s (%s)", address[:12], safety_gate.reason)
        return "dropped_safety"
    safety_inconclusive = safety_gate.verdict == Verdict.INCONCLUSIVE
    if safety_gate.verdict == Verdict.INCONCLUSIVE:
        logger.info("SAFETY INCONCLUSIVE for %s: %s", address[:12], safety_flags)

    # Extract tier / verdict for memory
    tier = ""
    import re
    tier_match = re.search(r"(HIGH CONVICTION|SOLID|SPECULATIVE|AVOID|СИЛЬНЫЙ|СРЕДНИЙ|СЛАБЫЙ|ПРОПУСК)", text)
    if tier_match:
        tier = tier_match.group(1)

    verdict_match = re.search(r"🎯\s*(.+)", text)
    token_match = re.search(r"🔍\s*(\S+)", text)
    verdict = verdict_match.group(1).strip() if verdict_match else "?"
    token_name = token_match.group(1) if token_match else "?"

    mem = record_analysis(address, token_name, verdict, tier)
    if mem["duplicate"]:
        logger.info("DUPLICATE: token %s — %d duplicates total", address[:12], mem["duplicates"])

    try:
        from loop_verifier import verify_analysis

        # AI text: line after 📝 if present
        ai_match = re.search(r"📝\s*(.+?)(?:\n📈|\n🎯|\n📎|\Z)", text, re.DOTALL)
        ai_text = ai_match.group(1).strip() if ai_match else text
        verifier_context_text = text
        context = {"full_report": verifier_context_text}

        verification = verify_analysis(token_name, ai_text, context)
        v = str(verification.get("verdict", DEFAULT_VERDICT)).upper() if verification else DEFAULT_VERDICT
        score = verification.get("score", 0) if verification else 0
        fixed = verification.get("fixed_text", "") if verification else ""
        issues = verification.get("issues", []) if verification else []
        verifier_gate = check_verifier(v, available=_verifier_available(verification), fixed_text=fixed)

        if verifier_gate.verdict == Verdict.REJECT:
            logger.warning("VERIFIER REJECT (score=%d): suppressing analysis for %s (%s)", score, token_name, verifier_gate.reason)
            logger.warning("Issues: %s", issues)
            return "suppressed_verifier"

        if verifier_gate.verdict == Verdict.HOLD:
            logger.warning("VERIFIER HOLD (score=%d): holding analysis for %s (%s)", score, token_name, verifier_gate.reason)
            logger.warning("Issues: %s", issues)
            return "hold_flag"

        if v == "FLAG":
            logger.info("VERIFIER FLAG (score=%d): %s", score, issues)
            if not fixed.strip() or not ai_match:
                logger.warning(
                    "VERIFIER HOLD (score=%d): FLAG fixed_text cannot be applied for %s (fixed=%s ai_marker=%s)",
                    score,
                    token_name,
                    bool(fixed.strip()),
                    bool(ai_match),
                )
                return "hold_flag"
            text = text.replace(ai_match.group(1), fixed)
        else:
            logger.info("VERIFIER PASS (score=%d)", score)
    except Exception as e:
        logger.warning("Verifier error (suppressing): %s", e)
        return "suppressed_verifier"

    if safety_inconclusive:
        text = f"{text}\n{SAFETY_INCONCLUSIVE_WARNING}"

    for line in text.splitlines():
        if any(kw in line for kw in ["Кабал", "Кабалы", "Инфраструктура", "⚠️", "GMGN"]):
            logger.info("INTEL: %s", line.strip())

    # ALWAYS send the report (no silent drop after analysis)
    for chunk in split_text(text):
        await application.bot.send_message(
            chat_id=TELEGRAM_GROUP_ID,
            text=chunk,
            disable_web_page_preview=True,
        )
    logger.info("MSF report delivered to %s (%d chars)", TELEGRAM_GROUP_ID, len(text))
    return "sent"


def start_msf_http_server(application: Application, loop: asyncio.AbstractEventLoop):
    class MsfSignalHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            logger.info("MSF HTTP: " + format, *args)

        def send_json(self, status: int, payload: dict):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/health":
                self.send_json(200, {"ok": True, "status": "healthy", "service": "rab9-msf-http"})
            else:
                self.send_json(404, {"ok": False, "error": "not_found"})

        def do_POST(self):
            if self.path != "/msf-signal":
                self.send_json(404, {"ok": False, "error": "not_found"})
                return

            if not RAB9_HTTP_SECRET or self.headers.get("X-RAB9-SECRET") != RAB9_HTTP_SECRET:
                self.send_json(401, {"ok": False, "error": "unauthorized"})
                return

            try:
                length = int(self.headers.get("Content-Length") or "0")
            except ValueError:
                self.send_json(400, {"ok": False, "error": "invalid_content_length"})
                return

            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except Exception:
                self.send_json(400, {"ok": False, "error": "invalid_json"})
                return

            chain = str(payload.get("chain") or "").lower()
            address = str(payload.get("address") or "").strip()

            if chain != "solana":
                self.send_json(400, {"ok": False, "error": "unsupported_chain"})
                return

            if not is_msf_solana_address(address):
                self.send_json(400, {"ok": False, "error": "invalid_address"})
                return

            future = asyncio.run_coroutine_threadsafe(
                send_msf_pairresolve(application, address),
                loop,
            )

            try:
                status = future.result(timeout=90)
            except Exception as error:
                logger.exception("MSF signal processing failed: %s", error)
                self.send_json(500, {"ok": False, "error": "processing_failed"})
                return

            status = status or "error"
            self.send_json(200, {"ok": status == "sent", "status": status})

    server = ReuseThreadingHTTPServer((RAB9_HTTP_HOST, RAB9_HTTP_PORT), MsfSignalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="rab9-msf-http")
    thread.start()
    logger.info("MSF HTTP endpoint listening on %s:%s", RAB9_HTTP_HOST, RAB9_HTTP_PORT)
    return server
