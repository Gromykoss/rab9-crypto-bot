import asyncio
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram.ext import Application

from address_validation import is_msf_solana_address
from config import RAB9_HTTP_HOST, RAB9_HTTP_PORT, RAB9_HTTP_SECRET, TELEGRAM_GROUP_ID
from msf_analysis import build_msf_signal_analysis_text, build_compact_analysis_text
from utils import split_text


logger = logging.getLogger("rab9_crypto_intel_bot")


async def send_msf_pairresolve(application: Application, address: str):
    logger.info("MSF analysis started for: %s", address)
    text = await asyncio.to_thread(build_compact_analysis_text, address)
    logger.info("MSF analysis complete: %d chars", len(text))

    # ── Loop Memory: skip duplicates, record results ──
    from loop_memory import should_skip, record_analysis
    if should_skip(address, cooldown_minutes=15):
        logger.info("SKIP: token %s analyzed recently (<15min cooldown)", address[:12])
        return  # Skip duplicate within cooldown
    
    # Extract tier from text for memory
    tier = ""
    import re
    tier_match = re.search(r'(HIGH CONVICTION|SOLID|SPECULATIVE|AVOID)', text)
    if tier_match:
        tier = tier_match.group(1)
    
    verdict_match = re.search(r'→ (\S+)', text)
    token_match = re.search(r'🔍 (\S+)', text)
    verdict = verdict_match.group(1) if verdict_match else "?"
    token_name = token_match.group(1) if token_match else "?"
    
    mem = record_analysis(address, token_name, verdict, tier)
    if mem["duplicate"]:
        logger.info("DUPLICATE: token %s — %d duplicates total", address[:12], mem["duplicates"])
    try:
        from loop_verifier import verify_analysis
        # Extract context for verifier
        import re
        token_match = re.search(r'🔍 (\S+)', text)
        mc_match = re.search(r'MC: (\S+)', text)
        verdict_match = re.search(r'→ (\S+)', text)
        ai_match = re.search(r'📊 (.+)', text)

        token_name = token_match.group(1) if token_match else "?"
        context = {
            "mc": mc_match.group(1) if mc_match else "?",
            "verdict": verdict_match.group(1) if verdict_match else "?",
            "onchain_risk": "LOW" if "LOW" in text else ("HIGH" if "HIGH" in text else "?"),
            "x_followers": "N/A",
        }
        ai_text = ai_match.group(1) if ai_match else text

        verification = verify_analysis(token_name, ai_text, context)
        v = verification.get("verdict", "PASS")
        score = verification.get("score", 0)

        if v == "FAIL":
            logger.warning("VERIFIER FAIL (score=%d): suppressing analysis for %s", score, token_name)
            logger.warning("Issues: %s", verification.get("issues", []))
            return  # Suppress — don't send
        elif v == "FLAG":
            logger.info("VERIFIER FLAG (score=%d): %s", score, verification.get("issues", []))
            fixed = verification.get("fixed_text", "")
            if fixed:
                # Replace AI analysis with corrected version
                if ai_match:
                    text = text.replace(ai_match.group(1), fixed)
        else:
            logger.info("VERIFIER PASS (score=%d)", score)
    except Exception as e:
        logger.warning("Verifier error (passing through): %s", e)
    for line in text.splitlines():
        if any(kw in line for kw in ["Кабалы", "Инфраструктура", "⚠️"]):
            logger.info("INTEL: %s", line.strip())

    for chunk in split_text(text):
        await application.bot.send_message(
            chat_id=TELEGRAM_GROUP_ID,
            text=chunk,
            disable_web_page_preview=True,
        )


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
                future.result(timeout=90)
            except Exception as error:
                logger.exception("MSF signal processing failed: %s", error)
                self.send_json(500, {"ok": False, "error": "processing_failed"})
                return

            self.send_json(200, {"ok": True, "status": "sent"})

    server = ThreadingHTTPServer((RAB9_HTTP_HOST, RAB9_HTTP_PORT), MsfSignalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="rab9-msf-http")
    thread.start()
    logger.info("MSF HTTP endpoint listening on %s:%s", RAB9_HTTP_HOST, RAB9_HTTP_PORT)
    return server
