import json
import requests

from config import XAI_API_KEY, XAI_BASE_URL
from dex import get_dex_token_pairs, pick_best_pair
from scoring import analyze_pair_metrics
from utils import (
    safe_float,
    format_usd,
    format_percent,
    format_ratio,
)


def ask_grok(prompt: str) -> str:
    if not XAI_API_KEY:
        return "Grok API key не найден в .env"

    url = f"{XAI_BASE_URL}/v1/chat/completions"

    headers = {
        "Authorization": f"Bearer {XAI_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": "grok-3-mini",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Ты crypto-intel аналитик для Telegram-бота. "
                    "Отвечай кратко, структурно, без финансовых гарантий. "
                    "Не выдумывай значения, которых нет в данных. "
                    "Не используй текущую цену как high/low. "
                    "Фокус: риск, liquidity, market cap, volume, txns, buy/sell pressure. "
                    "ВАЖНО — специфика мемкоинов: "
                    "MC $1M+ для мемкоина = средняя/высокая капитализация (не маленькая). "
                    "Отсутствие GitHub-активности для мемкоина = НОРМА (не red flag). "
                    "X-обсуждения и комьюнити = ключевой фактор для мемкоина (не dev). "
                    "Низкая ликвидность для мемкоина = нормально (не rug-pull признак). "
                    "Rug-pull риск определяй по ON-CHAIN данным (freeze, lock, creator%), а не по отсутствию GitHub."
                ),
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        "temperature": 0.1,
        "max_tokens": 350,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=30)

        if not response.ok:
            return f"Grok API error: {response.status_code} | {response.text[:500]}"

        data = response.json()
        return data["choices"][0]["message"]["content"]

    except Exception as error:
        return f"Grok request failed: {error}"


def build_pair_grok_data(pair: dict, metrics: dict) -> str:
    base = pair.get("baseToken") or {}
    quote = pair.get("quoteToken") or {}

    return json.dumps(
        {
            "chainId": pair.get("chainId"),
            "dexId": pair.get("dexId"),
            "url": pair.get("url"),
            "pairAddress": pair.get("pairAddress"),
            "baseToken": {
                "address": base.get("address"),
                "name": base.get("name"),
                "symbol": base.get("symbol"),
            },
            "quoteToken": {
                "address": quote.get("address"),
                "name": quote.get("name"),
                "symbol": quote.get("symbol"),
            },
            "priceUsd": pair.get("priceUsd"),
            "marketCap": pair.get("marketCap"),
            "fdv": pair.get("fdv"),
            "liquidity": pair.get("liquidity"),
            "volume": pair.get("volume"),
            "txns": pair.get("txns"),
            "priceChange": pair.get("priceChange"),
            "pairCreatedAtUtc": metrics.get("pairCreatedAtUtc"),
            "pairAgeHours": metrics.get("pairAgeHours"),
            "computedMetrics": metrics,
            "missingDataWarnings": [
                "Нет holder distribution",
                "Нет smart money data",
                "Нет contract audit",
                "Нет 24h high/low",
                "Нет social sentiment",
            ],
        },
        ensure_ascii=False,
        indent=2,
    )


def build_decision_layer(pair: dict, metrics: dict) -> str:
    price_change = pair.get("priceChange") or {}

    score = metrics.get("score") or 0
    risk = metrics.get("risk") or "n/a"
    rating = metrics.get("rating") or "n/a"

    market_cap = metrics.get("marketCap")
    liquidity = metrics.get("liquidityUsd")
    volume24h = metrics.get("volume24h")

    liquidity_to_mc = metrics.get("liquidityToMc")
    volume_to_mc = metrics.get("volumeToMc")
    sell_buy_24h = metrics.get("sellBuyRatio24h")
    sell_buy_1h = metrics.get("sellBuyRatio1h")

    price_1h = safe_float(price_change.get("h1"), None)
    price_24h = safe_float(price_change.get("h24"), None)

    verdict = "WATCH"
    action = "Наблюдать, не входить без подтверждения объёма и нормального buy pressure."
    position = "Watch Only"
    invalidation = "Sell/Buy ухудшается, объём падает, liquidity проседает, цена теряет импульс."

    manual_checks = [
        "Holder distribution",
        "Smart money / whale activity",
        "Contract / mint authority / freeze authority",
        "Соцсети и narrative",
        "Нет ли очевидного rug-паттерна",
    ]

    reasons = []

    if score >= 75:
        verdict = "STRONG WATCH"
        action = "Сильный кандидат для наблюдения. Вход только после ручной проверки и подтверждения импульса."
        position = "Tiny Scout / Watch"
        reasons.append("Score высокий")

    elif score >= 60:
        verdict = "WATCH"
        action = "Хороший кандидат для наблюдения. Не спешить, ждать подтверждения volume и price action."
        position = "Watch Only / Tiny Scout"
        reasons.append("Score выше среднего")

    elif score >= 40:
        verdict = "SPECULATIVE / CAUTION"
        action = "Высокий риск. Лучше ждать улучшения метрик или использовать только минимальный scout-size."
        position = "Tiny Scout max / Usually Wait"
        reasons.append("Score средний, сетап спорный")

    else:
        verdict = "AVOID"
        action = "Не трогать, пока метрики не улучшатся."
        position = "No Trade"
        reasons.append("Score низкий")

    if sell_buy_24h is not None:
        if sell_buy_24h > 1.5:
            verdict = "AVOID / WAIT"
            action = "Продажи доминируют. Ждать улучшения buy pressure."
            position = "No Trade"
            reasons.append("Sell/Buy24h выше 1.5x")
        elif sell_buy_24h < 0.8:
            reasons.append("Покупки сильнее продаж на 24h")

    if sell_buy_1h is not None:
        if sell_buy_1h > 1.5:
            reasons.append("На 1h повышенное давление продаж")
        elif sell_buy_1h < 0.8:
            reasons.append("На 1h buy pressure выглядит лучше")

    if liquidity_to_mc is not None:
        if liquidity_to_mc < 0.02:
            verdict = "AVOID / HIGH SLIPPAGE"
            action = "Ликвидность слишком тонкая относительно MC. Риск плохого выхода."
            position = "No Trade"
            reasons.append("Liquidity/MC ниже 2%")
        elif liquidity_to_mc >= 0.05:
            reasons.append("Liquidity/MC выглядит здоровее")

    if volume_to_mc is not None:
        if volume_to_mc < 0.03:
            reasons.append("Volume/MC слабый")
        elif volume_to_mc >= 0.20:
            reasons.append("Volume/MC сильный")

    if volume24h is not None:
        if volume24h < 10_000:
            if verdict in ["STRONG WATCH", "WATCH"]:
                verdict = "WATCH / LOW VOLUME"
            reasons.append("Volume24h ниже $10K — сигнал слабее")
        elif volume24h < 20_000:
            if verdict == "STRONG WATCH":
                verdict = "WATCH"
            reasons.append("Volume24h ниже $20K — осторожнее")

    if price_1h is not None:
        if price_1h <= -15:
            verdict = "WAIT / DUMP RISK"
            action = "Идёт резкое падение за 1h. Не ловить нож без разворота."
            position = "No Trade"
            reasons.append("Price 1h резко отрицательный")
        elif price_1h >= 20:
            action = "Импульс сильный, но вход после резкого движения опасен. Ждать отката или подтверждения."
            reasons.append("Price 1h резко положительный")

    if price_24h is not None and price_24h > 80:
        reasons.append("Сильный 24h pump — повышен риск позднего входа")

    if not reasons:
        reasons.append("Нет сильных позитивных или негативных сигналов")

    reasons_text = "\n".join([f"- {reason}" for reason in reasons[:7]])
    checks_text = "\n".join([f"- {check}" for check in manual_checks])

    return (
        "🧭 Decision Layer\n\n"
        f"Verdict: {verdict}\n"
        f"Action: {action}\n"
        f"Position: {position}\n"
        f"Invalidation: {invalidation}\n\n"
        f"Why:\n{reasons_text}\n\n"
        f"Manual Checks:\n{checks_text}\n\n"
        f"Core Metrics:\n"
        f"MC: {format_usd(market_cap)}\n"
        f"Liquidity: {format_usd(liquidity)}\n"
        f"Volume24h: {format_usd(volume24h)}\n"
        f"Liquidity/MC: {format_percent((liquidity_to_mc or 0) * 100)}\n"
        f"Volume24h/MC: {format_percent((volume_to_mc or 0) * 100)}\n"
        f"Sell/Buy24h: {format_ratio(sell_buy_24h)}\n"
        f"Sell/Buy1h: {format_ratio(sell_buy_1h)}\n"
        f"Score: {score}/100\n"
        f"Signal: {rating}\n"
        f"Risk: {risk}"
    )


def build_token_intel_text(chain_id: str, token_address: str) -> str:
    result = get_dex_token_pairs(chain_id, token_address)

    if not result["ok"]:
        return f"Ошибка Dexscreener: {result['status_code']}\n{result['text'][:500]}"

    pairs = result["data"]

    if not isinstance(pairs, list) or not pairs:
        return "Пары по этому токену не найдены."

    best_pair = pick_best_pair(pairs)

    if not best_pair:
        return "Не смог выбрать основную пару."

    metrics = analyze_pair_metrics(best_pair)
    decision_layer = build_decision_layer(best_pair, metrics)
    grok_data = build_pair_grok_data(best_pair, metrics)

    prompt = (
        "Проанализируй токен по данным Dexscreener, computed metrics и decision layer. "
        "Отвечай максимально кратко. Не повторяй все цифры, они уже есть выше. "
        "Дай short crypto decision report строго по структуре:\n"
        "1) Verdict: одна строка\n"
        "2) Why: максимум 2 короткие причины\n"
        "3) Entry: одно короткое условие\n"
        "4) Invalidation: одно короткое условие\n"
        "5) Exit: одна короткая логика\n\n"
        "Правила:\n"
        "- Не добавляй пункт 6.\n"
        "- Не перечисляй manual checks.\n"
        "- Не пересказывай все метрики.\n"
        "- Не выдумывай данные, которых нет.\n"
        "- Не давай гарантий прибыли.\n"
        "- Не советуй all-in или агрессивный вход.\n"
        "- Пиши кратко, без длинных объяснений.\n\n"
        f"Decision Layer:\n{decision_layer}\n\n"
        f"Данные:\n{grok_data}"
    )

    analysis = ask_grok(prompt)

    return (
        "🧪 Token Intel v3.4\n\n"
        f"{decision_layer}\n\n"
        "🧠 Grok Brief:\n"
        f"{analysis}\n\n"
        f"URL: {best_pair.get('url', 'n/a')}"
    )
