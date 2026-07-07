#!/usr/bin/env python3
"""MSF Listener — event-driven bridge: Мемы → RAB9.

Listens to @msf_rab_bot in the Мемы group.
Triggers ONLY on DexScreener links or raw Solana addresses.
Forwards to RAB9 HTTP :8089/msf-signal.
"""
import os, sys, json, re, time, urllib.request
import logging

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("msf_listener")

BASE_DIR = "/home/hermes-workspace/rab9"
OFFSET_FILE = os.path.join(BASE_DIR, "msf_offset.txt")
TOKEN_FILE = os.path.join(BASE_DIR, "msf_token.txt")
ENV_FILE = os.path.join(BASE_DIR, ".env")
RAB9_URL = "http://localhost:8089/msf-signal"

# ── Load config ──
token = ""
if os.path.exists(TOKEN_FILE):
    with open(TOKEN_FILE) as f:
        token = f.read().strip()

secret = ""
if os.path.exists(ENV_FILE):
    with open(ENV_FILE) as f:
        for line in f:
            if line.startswith("RAB9_HTTP_SECRET="):
                secret = line.split("=", 1)[1].strip().strip("\"'")
                break

if not token:
    log.error("MSF token not found in %s", TOKEN_FILE)
    sys.exit(1)
if not secret:
    log.error("RAB9 secret not found in %s", ENV_FILE)
    sys.exit(1)

# ── Solana address regex ──
SOLANA_RE = re.compile(r'\b[1-9A-HJ-NP-Za-km-z]{32,44}\b')

# ── Read offset ──
offset = 0
if os.path.exists(OFFSET_FILE):
    with open(OFFSET_FILE) as f:
        try:
            offset = int(f.read().strip() or "0")
        except ValueError:
            offset = 0

log.info("MSF Listener started. Offset: %d", offset)

# ── Main loop: long-poll Telegram ──
while True:
    try:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/getUpdates"
            f"?offset={offset + 1}&limit=10&timeout=30"
        )
        resp = urllib.request.urlopen(req, timeout=60)
        data = json.loads(resp.read())

        if not data.get("ok"):
            log.warning("Telegram API error: %s", data.get("description", "?"))
            time.sleep(5)
            continue

        updates = data.get("result", [])

        for u in updates:
            offset = max(offset, u["update_id"])

            msg = u.get("message") or u.get("channel_post") or {}
            text = (msg.get("text") or msg.get("caption") or "").strip()
            if not text:
                continue

            chat_info = msg.get("chat", {})
            chat_title = chat_info.get("title", "DM")
            chat_id = chat_info.get("id", 0)

            # ── Extract Solana address ──
            address = None

            # DexScreener URL
            ds_match = re.search(
                r'dexscreener\.com/solana/([1-9A-HJ-NP-Za-km-z]{32,44})',
                text,
                re.IGNORECASE,
            )
            if ds_match:
                address = ds_match.group(1)
                log.info("[%s] DexScreener: %s...", chat_title, address[:12])

            # Raw address (only if no DexScreener match)
            if not address:
                sol_matches = SOLANA_RE.findall(text)
                if sol_matches:
                    address = sol_matches[0]
                    log.info("[%s] Raw address: %s...", chat_title, address[:12])

            if not address:
                continue

            # ── Forward to RAB9 ──
            body = json.dumps({
                "chain": "solana",
                "address": address,
            }).encode()

            post_req = urllib.request.Request(
                RAB9_URL,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-RAB9-SECRET": secret,
                },
            )
            try:
                post_resp = urllib.request.urlopen(post_req, timeout=90)
                result = json.loads(post_resp.read())
                status = "OK" if result.get("ok") else result.get("error", "?")
                log.info("[%s] → RAB9: %s", chat_title, status)
            except Exception as e:
                log.error("[%s] RAB9 POST failed: %s", chat_title, e)

        # Save offset
        with open(OFFSET_FILE, "w") as f:
            f.write(str(offset))

    except Exception as e:
        log.error("Poll error: %s", e)
        time.sleep(10)
