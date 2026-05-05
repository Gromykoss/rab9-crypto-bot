import os
import json
import time
import asyncio
import logging

from telegram.ext import Application

from config import (
    ALERT_STATE_PATH,
    ALERT_INTERVAL_SECONDS,
    ALERT_COOLDOWN_SECONDS,
    TELEGRAM_GROUP_ID,
)
from utils import (
    safe_float,
    format_usd,
    format_percent,
    format_ratio,
    split_text,
)
from dex import get_dex_token_pairs, pick_best_pair
from scoring import analyze_pair_metrics
from watchlist import load_watchlist, watch_key


logger = logging.getLogger("rab9_crypto_intel_bot")


def load_alert_state():
    if not os.path.exists(ALERT_STATE_PATH):
        return {}

    try:
        with open(ALERT_STATE_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)

        if isinstance(data, dict):
            return data

        return {}
    except Exception:
        return {}


def save_alert_state(state):
    with open(ALERT_STATE_PATH, "w", encoding="utf-8") as file:
        json.dump(state, file, ensure_ascii=False, indent=2)


def risk_rank(risk: str) -> int:
    value = (risk or "").lower()

    if "extreme" in value:
        return 4
    if "high" in value:
        return 3
    if "medium" in value:
        return 2
    if "low" in value:
        return 1

    return 0


def get_watch_snapshot(item: dict):
    chain = item.get("chain")
    address = item.get("address")

    result = get_dex_token_pairs(chain, address)

    if not result["ok"]:
        return None, f"Dexscreener error {result['status_code']}"

    pairs = result["data"]

    if not isinstance(pairs, list) or not pairs:
        return None, "no pairs found"

    best_pair = pick_best_pair(pairs)

    if not best_pair:
        return None, "no best pair"

    metrics = analyze_pair_metrics(best_pair)

    base = best_pair.get("baseToken") or {}
    price_change = best_pair.get("priceChange") or {}

    snapshot = {
        "chain": chain,
        "address": address,
        "symbol": base.get("symbol", "N/A"),
        "url": best_pair.get("url"),
        "score": metrics.get("score"),
        "risk": metrics.get("risk"),
        "rating": metrics.get("rating"),
        "marketCap": metrics.get("marketCap"),
        "liquidityUsd": metrics.get("liquidityUsd"),
        "volume24h": metrics.get("volume24h"),
        "volume1h": metrics.get("volume1h"),
        "sellBuyRatio24h": metrics.get("sellBuyRatio24h"),
        "sellBuyRatio1h": metrics.get("sellBuyRatio1h"),
        "priceChange1h": safe_float(price_change.get("h1"), None),
        "priceChange24h": safe_float(price_change.get("h24"), None),
        "checkedTs": int(time.time()),
    }

    return snapshot, None


def classify_alerts(old: dict | None, new: dict):
    if not old:
        return None, []

    events = []

    old_score = safe_float(old.get("score"), None)
    new_score = safe_float(new.get("score"), None)

    if old_score is not None and new_score is not None:
        delta = new_score - old_score

        if delta <= -20:
            events.append(("danger", f"Score резко упал: {old_score:.0f} → {new_score:.0f}"))
        elif delta <= -15:
            events.append(("warning", f"Score упал: {old_score:.0f} → {new_score:.0f}"))
        elif delta >= 20:
            events.append(("positive", f"Score сильно вырос: {old_score:.0f} → {new_score:.0f}"))
        elif delta >= 15:
            events.append(("positive", f"Score вырос: {old_score:.0f} → {new_score:.0f}"))

    old_sell_24 = safe_float(old.get("sellBuyRatio24h"), None)
    new_sell_24 = safe_float(new.get("sellBuyRatio24h"), None)

    if old_sell_24 is not None and new_sell_24 is not None:
        delta = new_sell_24 - old_sell_24

        if new_sell_24 >= 2.0 and delta >= 0.5:
            events.append(("danger", f"Sell/Buy24h резко ухудшился: {old_sell_24:.2f}x → {new_sell_24:.2f}x"))
        elif new_sell_24 >= 1.5 and delta >= 0.5:
            events.append(("warning", f"Sell/Buy24h ухудшился: {old_sell_24:.2f}x → {new_sell_24:.2f}x"))
        elif old_sell_24 >= 1.3 and new_sell_24 <= 0.9:
            events.append(("positive", f"Sell/Buy24h улучшился: {old_sell_24:.2f}x → {new_sell_24:.2f}x"))

    old_sell_1h = safe_float(old.get("sellBuyRatio1h"), None)
    new_sell_1h = safe_float(new.get("sellBuyRatio1h"), None)

    if old_sell_1h is not None and new_sell_1h is not None:
        if new_sell_1h >= 2.0:
            events.append(("warning", f"1h sell pressure высокий: {new_sell_1h:.2f}x"))
        elif old_sell_1h >= 1.3 and new_sell_1h <= 0.8:
            events.append(("positive", f"1h buy pressure улучшился: {old_sell_1h:.2f}x → {new_sell_1h:.2f}x"))

    old_liq = safe_float(old.get("liquidityUsd"), None)
    new_liq = safe_float(new.get("liquidityUsd"), None)

    if old_liq is not None and new_liq is not None and old_liq > 0:
        liq_delta = (new_liq - old_liq) / old_liq

        if liq_delta <= -0.30:
            events.append(("danger", f"Liquidity резко просела: {format_usd(old_liq)} → {format_usd(new_liq)} ({liq_delta * 100:.1f}%)"))
        elif liq_delta <= -0.20:
            events.append(("warning", f"Liquidity просела: {format_usd(old_liq)} → {format_usd(new_liq)} ({liq_delta * 100:.1f}%)"))
        elif liq_delta >= 0.30:
            events.append(("positive", f"Liquidity выросла: {format_usd(old_liq)} → {format_usd(new_liq)} (+{liq_delta * 100:.1f}%)"))

    price_1h = safe_float(new.get("priceChange1h"), None)

    if price_1h is not None:
        if price_1h <= -25:
            events.append(("danger", f"Price 1h сильный дамп: {price_1h:.2f}%"))
        elif price_1h <= -15:
            events.append(("warning", f"Price 1h дамп: {price_1h:.2f}%"))
        elif price_1h >= 30:
            events.append(("positive", f"Price 1h сильный памп: +{price_1h:.2f}%"))
        elif price_1h >= 20:
            events.append(("positive", f"Price 1h памп: +{price_1h:.2f}%"))

    old_risk = old.get("risk")
    new_risk = new.get("risk")

    if old_risk and new_risk and old_risk != new_risk:
        old_rank = risk_rank(old_risk)
        new_rank = risk_rank(new_risk)

        if new_rank >= old_rank + 2:
            events.append(("danger", f"Risk резко ухудшился: {old_risk} → {new_risk}"))
        elif new_rank > old_rank and new_risk == "Extreme":
            events.append(("danger", f"Risk стал Extreme: {old_risk} → {new_risk}"))
        elif old_rank >= new_rank + 1:
            events.append(("positive", f"Risk улучшился: {old_risk} → {new_risk}"))

    if not events:
        return None, []

    severity_rank = {
        "positive": 1,
        "warning": 2,
        "danger": 3,
    }

    top_severity = max(events, key=lambda item: severity_rank[item[0]])[0]
    messages = [message for _, message in events]

    return top_severity, messages


def severity_title(severity: str) -> str:
    if severity == "danger":
        return "🚨 Danger Alert"
    if severity == "warning":
        return "⚠️ Warning Alert"
    if severity == "positive":
        return "🚀 Positive Alert"
    return "🔔 Watchlist Alert"


def should_send_alert(old_snapshot: dict | None, severity: str, messages: list[str]) -> bool:
    if not old_snapshot:
        return False

    now = int(time.time())
    last_alert_ts = int(old_snapshot.get("_lastAlertTs") or 0)
    last_fingerprint = old_snapshot.get("_lastAlertFingerprint")

    fingerprint = severity + "|" + "|".join(messages[:3])

    if last_fingerprint == fingerprint and now - last_alert_ts < ALERT_COOLDOWN_SECONDS:
        return False

    if now - last_alert_ts < ALERT_COOLDOWN_SECONDS and severity != "danger":
        return False

    return True


def attach_alert_meta(snapshot: dict, severity: str | None = None, messages: list[str] | None = None):
    new_snapshot = dict(snapshot)

    if severity and messages:
        new_snapshot["_lastAlertTs"] = int(time.time())
        new_snapshot["_lastAlertSeverity"] = severity
        new_snapshot["_lastAlertFingerprint"] = severity + "|" + "|".join(messages[:3])

    return new_snapshot


def build_alert_block(item: dict, snapshot: dict, severity: str, messages: list[str]) -> str:
    note = item.get("note") or "без заметки"

    return (
        f"{severity_title(severity)}\n\n"
        f"Token: {snapshot.get('symbol')}\n"
        f"Chain: {snapshot.get('chain')}\n"
        f"Address: {snapshot.get('address')}\n"
        f"Note: {note}\n\n"
        f"MC: {format_usd(snapshot.get('marketCap'))}\n"
        f"Liquidity: {format_usd(snapshot.get('liquidityUsd'))}\n"
        f"Volume1h: {format_usd(snapshot.get('volume1h'))}\n"
        f"Volume24h: {format_usd(snapshot.get('volume24h'))}\n"
        f"Score: {snapshot.get('score')}/100\n"
        f"Signal: {snapshot.get('rating')}\n"
        f"Risk: {snapshot.get('risk')}\n"
        f"Sell/Buy1h: {format_ratio(snapshot.get('sellBuyRatio1h'))}\n"
        f"Sell/Buy24h: {format_ratio(snapshot.get('sellBuyRatio24h'))}\n"
        f"Price 1h: {format_percent(snapshot.get('priceChange1h'))}\n"
        f"Price 24h: {format_percent(snapshot.get('priceChange24h'))}\n\n"
        "Triggers:\n"
        + "\n".join([f"- {message}" for message in messages])
        + f"\n\nAnalyze: /token {snapshot.get('chain')} {snapshot.get('address')}\n"
        + f"{snapshot.get('url')}"
    )


def build_watch_alerts_text():
    items = load_watchlist()

    if not items:
        return None

    state = load_alert_state()
    new_state = dict(state)
    alert_blocks = []

    for item in items:
        key = watch_key(item.get("chain", ""), item.get("address", ""))
        old_snapshot = state.get(key)

        snapshot, error = get_watch_snapshot(item)

        if error:
            continue

        severity, messages = classify_alerts(old_snapshot, snapshot)

        if severity and messages and should_send_alert(old_snapshot, severity, messages):
            alert_blocks.append(build_alert_block(item, snapshot, severity, messages))
            new_state[key] = attach_alert_meta(snapshot, severity, messages)
        else:
            old_meta = {}

            if old_snapshot:
                for meta_key in ["_lastAlertTs", "_lastAlertSeverity", "_lastAlertFingerprint"]:
                    if meta_key in old_snapshot:
                        old_meta[meta_key] = old_snapshot[meta_key]

            merged = dict(snapshot)
            merged.update(old_meta)
            new_state[key] = merged

    save_alert_state(new_state)

    if not alert_blocks:
        return None

    return "\n\n---\n\n".join(alert_blocks)


async def alert_loop(application: Application):
    logger.info(
        f"Alert loop started. Interval: {ALERT_INTERVAL_SECONDS}s. Cooldown: {ALERT_COOLDOWN_SECONDS}s"
    )

    await asyncio.sleep(30)

    while True:
        try:
            text = await asyncio.to_thread(build_watch_alerts_text)

            if text:
                for chunk in split_text(text):
                    await application.bot.send_message(
                        chat_id=TELEGRAM_GROUP_ID,
                        text=chunk,
                        disable_web_page_preview=True,
                    )

        except Exception as error:
            logger.exception(f"Alert loop error: {error}")

        await asyncio.sleep(ALERT_INTERVAL_SECONDS)


async def post_init(application: Application):
    application.create_task(alert_loop(application))
