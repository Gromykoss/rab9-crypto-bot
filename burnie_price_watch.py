#!/usr/bin/env python3
"""BURNIE price watch — аномалии цены (DexScreener, бесплатно, без X-кредитов).

Паттерн: no_agent cron каждые 10 мин. В норме — тишина (пустой stdout).

Двухфазная логика:
- Резкий скачок цены ≥ ±20% за короткое окно (~10 мин) → короткий цена-алерт.
- На следующем тике аномалия удержалась (не откатилась за порог) → полный отчёт
  (запускает burnie_sentiment_tracker.py, тратит X-кредиты).

Время в алертах — московское (UTC+3, фиксированно, без перехода на летнее).
"""

import json
import os
import subprocess
import urllib.request
from datetime import datetime, timedelta, timezone

RAB9_DIR = "/home/hermes-workspace/rab9"
ENV = os.path.join(RAB9_DIR, ".env")
SCRIPTS_DIR = "/home/hermes-workspace/.hermes/profiles/rab9/scripts"
STATE = os.path.join(SCRIPTS_DIR, "burnie_price_state.json")

BURNIE_MINT = "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump"
THRESHOLD_PCT = 20.0          # порог аномалии (решение Сергея 21.08.2026)
MSK_OFFSET = timedelta(hours=3)  # Москва UTC+3, фиксированно

DEX_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) RAB9/1.0"}


def read_env():
    tok = grp = ""
    try:
        with open(ENV) as f:
            for line in f:
                line = line.strip()
                if line.startswith("TELEGRAM_BOT_TOKEN="):
                    tok = line.split("=", 1)[1].strip().strip("\"'")
                elif line.startswith("TELEGRAM_GROUP_ID="):
                    grp = line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return tok, grp


def send_tg(tok, grp, text):
    url = "https://api.telegram.org/bot%s/sendMessage" % tok
    body = json.dumps({
        "chat_id": grp,
        "text": text[:3500],
        "disable_web_page_preview": True,
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=15).read()
        return True
    except Exception:
        return False


def msk_now():
    return datetime.now(timezone.utc) + MSK_OFFSET


def fetch_price():
    """Текущая цена BURNIE через DexScreener (бесплатно). {ok, price, mc, vol, chg}."""
    out = {"ok": False}
    try:
        url = "https://api.dexscreener.com/latest/dex/tokens/%s" % BURNIE_MINT
        req = urllib.request.Request(url, headers=DEX_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        pairs = data.get("pairs") or []
        best = None
        for p in pairs:
            if not isinstance(p, dict):
                continue
            liq = float((p.get("liquidity") or {}).get("usd") or 0)
            if best is None or liq > float((best.get("liquidity") or {}).get("usd") or 0):
                best = p
        if not best:
            return out
        price = best.get("priceUsd")
        out.update({
            "ok": True,
            "price": float(price) if price else None,
            "mc": best.get("marketCap"),
            "vol": (best.get("volume") or {}).get("h24"),
            "chg": (best.get("priceChange") or {}).get("h24"),
        })
    except Exception:
        pass
    return out


def load_state():
    if os.path.exists(STATE):
        try:
            with open(STATE) as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            pass
    return {"baseline_price": None, "baseline_ts": None, "anomaly_ref": None}


def save_state(st):
    try:
        with open(STATE, "w") as f:
            json.dump(st, f, ensure_ascii=False)
    except OSError:
        pass


def _fmt_usd(v):
    try:
        return "${:,.2f}".format(float(v))
    except (TypeError, ValueError):
        return "N/A"


def _fmt_price(v):
    try:
        return "${:.6f}".format(float(v))
    except (TypeError, ValueError):
        return "N/A"


def run_full_tracker():
    """Запуск полного BURNIE-трекера; возвращает stdout (готовый отчёт)."""
    try:
        proc = subprocess.run(
            ["python3", "burnie_sentiment_tracker.py"],
            cwd=RAB9_DIR, capture_output=True, text=True, timeout=240,
        )
        out = (proc.stdout or "").strip()
        return out if out and out != "[SILENT]" else ""
    except Exception:
        return ""


def main():
    st = load_state()
    dex = fetch_price()
    if not dex.get("ok") or dex.get("price") is None:
        return  # сбой DexScreener — не спамим, тишина

    curr = dex["price"]
    now = msk_now()

    # Первый запуск — фиксируем baseline, молчим.
    if st["baseline_price"] is None:
        st["baseline_price"] = curr
        st["baseline_ts"] = now.isoformat()
        save_state(st)
        return

    baseline = float(st["baseline_price"])
    delta = (curr - baseline) / baseline * 100.0 if baseline else 0.0

    tok, grp = read_env()
    if not tok or not grp:
        save_state(st)
        return

    anomaly_ref = st.get("anomaly_ref")

    if anomaly_ref is None:
        # Фаза 1: нет активной аномалии.
        if abs(delta) >= THRESHOLD_PCT:
            direction = "↑ рост" if delta > 0 else "↓ падение"
            st["anomaly_ref"] = {"price": baseline, "ts": now.isoformat()}
            st["baseline_price"] = curr
            st["baseline_ts"] = now.isoformat()
            save_state(st)
            msg = (
                "🚨 BURNIE — аномалия цены\n"
                "💵 Цена: %s (было %s, %+.1f%% за ~10 мин)\n"
                "💰 Капитализация: %s | Объём 24ч: %s | За 24ч: %+.1f%%\n"
                "⏱ %s МСК\n"
                "🔍 Проверю удержание через ~10 мин — если подтвердится, пришлю полный отчёт."
            ) % (
                _fmt_price(curr),
                _fmt_price(baseline),
                delta,
                _fmt_usd(dex.get("mc")),
                _fmt_usd(dex.get("vol")),
                float(dex.get("chg") or 0),
                now.strftime("%d.%m %H:%M"),
            )
            send_tg(tok, grp, msg)
        else:
            # Норма — плавный дрейф baseline.
            st["baseline_price"] = curr
            st["baseline_ts"] = now.isoformat()
            save_state(st)
        return

    # Фаза 2: аномалия в ожидании подтверждения.
    ref_price = float(anomaly_ref["price"])
    delta_conf = (curr - ref_price) / ref_price * 100.0 if ref_price else 0.0

    if abs(delta_conf) >= THRESHOLD_PCT:
        # Подтверждено — полный отчёт.
        full = run_full_tracker()
        if full:
            send_tg(tok, grp, "✅ BURNIE — аномалия цены подтверждена. Полный отчёт:\n\n" + full)
        else:
            send_tg(tok, grp, "✅ BURNIE — аномалия цены подтверждена, но полный трекер не отработал.")
        st["anomaly_ref"] = None
    else:
        # Откатилось — ложная тревога, тишина.
        st["anomaly_ref"] = None

    st["baseline_price"] = curr
    st["baseline_ts"] = now.isoformat()
    save_state(st)


if __name__ == "__main__":
    main()
