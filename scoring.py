from utils import safe_float, safe_div, ms_to_utc, pair_age_hours


def analyze_pair_metrics(pair: dict) -> dict:
    liquidity = pair.get("liquidity") or {}
    volume = pair.get("volume") or {}
    txns = pair.get("txns") or {}
    price_change = pair.get("priceChange") or {}

    h24_txns = txns.get("h24") or {}
    h1_txns = txns.get("h1") or {}

    market_cap = safe_float(pair.get("marketCap") or pair.get("fdv"))
    liquidity_usd = safe_float(liquidity.get("usd"))
    volume_24h = safe_float(volume.get("h24"))
    volume_1h = safe_float(volume.get("h1"))

    buys_24h = safe_float(h24_txns.get("buys"))
    sells_24h = safe_float(h24_txns.get("sells"))
    buys_1h = safe_float(h1_txns.get("buys"))
    sells_1h = safe_float(h1_txns.get("sells"))

    liquidity_to_mc = safe_div(liquidity_usd, market_cap)
    volume_to_mc = safe_div(volume_24h, market_cap)
    sell_buy_ratio_24h = safe_div(sells_24h, buys_24h)
    sell_buy_ratio_1h = safe_div(sells_1h, buys_1h)

    age_hours = pair_age_hours(pair.get("pairCreatedAt"))

    score = 50
    flags = []

    if market_cap and 1_000_000 <= market_cap <= 5_000_000:
        score += 15
        flags.append("MC в целевой зоне $1M–$5M")
    elif market_cap and market_cap > 20_000_000:
        score -= 10
        flags.append("MC уже выше ранней зоны")

    if liquidity_to_mc is not None:
        if liquidity_to_mc >= 0.05:
            score += 10
            flags.append("Ликвидность/MC выглядит нормально")
        elif liquidity_to_mc < 0.02:
            score -= 15
            flags.append("Низкая ликвидность/MC")

    if volume_to_mc is not None:
        if volume_to_mc >= 0.20:
            score += 10
            flags.append("Высокий объём/MC")
        elif volume_to_mc < 0.03:
            score -= 10
            flags.append("Слабый объём/MC")

    if sell_buy_ratio_24h is not None:
        if sell_buy_ratio_24h > 1.4:
            score -= 10
            flags.append("24h sells заметно выше buys")
        elif sell_buy_ratio_24h < 0.8:
            score += 5
            flags.append("24h buys выше sells")

    if sell_buy_ratio_1h is not None:
        if sell_buy_ratio_1h > 1.5:
            score -= 10
            flags.append("1h sell pressure повышен")
        elif sell_buy_ratio_1h < 0.8:
            score += 5
            flags.append("1h buy pressure выглядит лучше")

    if age_hours is not None:
        if age_hours < 1:
            score -= 15
            flags.append("Пара младше 1 часа")
        elif age_hours < 24:
            score -= 10
            flags.append("Пара младше 24 часов")
        elif age_hours > 24 * 30:
            score += 5
            flags.append("Пара живёт больше 30 дней")

    price_h24 = safe_float(price_change.get("h24"), None)
    price_h1 = safe_float(price_change.get("h1"), None)

    if price_h24 is not None and price_h1 is not None:
        if price_h24 > 50 and price_h1 < 0:
            score -= 10
            flags.append("Сильный 24h pump и 1h охлаждение")
        elif price_h24 > 0 and price_h1 > 0:
            score += 5
            flags.append("Рост подтверждается на 24h и 1h")
        elif price_h24 < -20:
            score -= 10
            flags.append("Сильное падение за 24h")

    score = max(0, min(100, score))

    if score >= 75:
        rating = "Strong Watch"
        risk = "Medium/High"
    elif score >= 60:
        rating = "Watch"
        risk = "High"
    elif score >= 40:
        rating = "Speculative / Caution"
        risk = "High"
    else:
        rating = "Avoid / Extreme Caution"
        risk = "Extreme"

    return {
        "score": score,
        "rating": rating,
        "risk": risk,
        "flags": flags,
        "marketCap": market_cap,
        "liquidityUsd": liquidity_usd,
        "volume24h": volume_24h,
        "volume1h": volume_1h,
        "liquidityToMc": liquidity_to_mc,
        "volumeToMc": volume_to_mc,
        "sellBuyRatio24h": sell_buy_ratio_24h,
        "sellBuyRatio1h": sell_buy_ratio_1h,
        "pairCreatedAtUtc": ms_to_utc(pair.get("pairCreatedAt")),
        "pairAgeHours": age_hours,
    }
