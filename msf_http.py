import asyncio
import json
import logging
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from telegram.ext import Application

from config import RAB9_HTTP_HOST, RAB9_HTTP_PORT, RAB9_HTTP_SECRET, TELEGRAM_GROUP_ID
from pair_sources import build_pair_resolve_text
from utils import split_text


logger = logging.getLogger("rab9_crypto_intel_bot")

SOLANA_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


async def send_msf_pairresolve(application: Application, address: str):
    text = await asyncio.to_thread(build_pair_resolve_text, address)

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

            if not SOLANA_ADDRESS_RE.match(address):
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
