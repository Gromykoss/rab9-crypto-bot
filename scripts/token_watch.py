#!/usr/bin/env python3
"""Наблюдение за токенами второго контура (не BURNIE) — мультитокенный вотч.

Зачем: 18.11.2026 владелец (Сергей) попросил взять под наблюдение второй токен
(CLAUDIA, mint 2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM). BURNIE-скрипты
заточены под один минт, поэтому здесь ОТДЕЛЬНЫЙ контур: BURNIE-pipeline
(sentiment, accum-watch, price-watch) не читается и не меняется.

Что делает за один тик (крон, no_agent, тишина в норме):
  1) DexScreener: цена = МЕДИАНА по парам, котируемым в SOL/USDC/USDT; ликвидность
     и объём — сумма по этим же парам, число пар и DEX-ов, изменения 5м/1ч/6ч/24ч,
     покупки/продажи 24ч. Пары с экзотической котировкой в расчёт НЕ входят: их
     USD-оценку DexScreener иногда считает битой (19.11 meteora CLAUDIA/MM отдала
     priceUsd $61.15 и «ликвидность» $9.98 млн при реальных $0.0064 и ~$1 тыс. —
     ошибка ~×9600 в курсе MM, из-за неё ложный «+829 807%» и MC $58 млрд).
     Такие пары выносятся отдельной строкой и один раз сообщаются владельцу.
  2) Solana RPC (публичный, без ключей): живой саплай (getTokenSupply) и один раз
     — права mint/freeze (safety-строка).
  3) Алерты (каждый — только при срабатывании порога):
       • РЕЗКОЕ ДВИЖЕНИЕ ЦЕНЫ  — ±15% за ≤1ч или ±50% за 24ч
       • СЛИВ ЛИКВИДНОСТИ      — ≥15% за сутки (от значения сутки назад или от пика)
       • ВСПЛЕСК ОБЪЁМА        — объём за 1ч ≥ 5× среднего часового за сутки
       • ПЕРЕВЕС ПРОДАЖ        — покупок/продаж 24ч < 0.5 при объёме ≥ $500 тыс.
       • ИЗМЕНЕНИЕ САПЛАЯ      — ±0.5% (сжигание печью / докомпаунд минта)
       • РАЗМНОЖЕНИЕ ПАР       — +3 пары и больше за сутки (в пайплайне RAB9 это
                                 признак кабала: 08.11 по CLAUDIA был CABAL_EXPLOSION)
       • ПАРА ВНЕ РАСЧЁТА     — один раз на адрес пары: экзотическая котировка
                                 с «ликвидностью» ≥ 5× от чистых пар (спуф-витрина)
     Санити-гейт (19.11): скачок цены больше ×10 между тиками — аномалия источника,
     а не рынок: алерт не отправляем, а тики с битой оценкой вычищаем из истории,
     иначе следующие 24 ч сыпались бы ложные «падение цены» и «слив ликвидности».
  4) Раз в сутки (04:00 UTC = 09:00 Бишкек) — короткая сводка по всем токенам.
Повтор одного и того же типа алерта — не чаще 120 мин (антиспам).
Время в сообщениях — Бишкек (UTC+5), как у владельца.

Запуск: python3 scripts/token_watch.py            (крон — тот же файл через шим)
Данные: data/token_watch_state.json
Доставка: печать в stdout → крон (no_agent) отдаёт текст в Telegram-чат профиля.
Ничего не печатается в норме (тишина), сообщения — только при событии.
ВАЖНО: 18.11 прямой вызов Telegram API с токеном из ~/rab9/.env дал 401 —
у проекта токен бота ядра (@rab2610bot), для отчётов он не годится; канонный
путь доставки — stdout + deliver=telegram у крона (как у BURNIE-контура).
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

RAB9_DIR = Path("/home/hermes-workspace/rab9")
STATE_PATH = RAB9_DIR / "data" / "token_watch_state.json"

# ── что наблюдаем ────────────────────────────────────────────────────────────
TOKENS = [
    {
        "symbol": "CLAUDIA",
        "mint": "2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM",
        "note": "мем про поп-звезду (claudia.gallery, X @SolClaudia_), ~6 недель от роду",
        "history": "17.10 в пайплайне RAB9: 98/125 «ХОРОШИЙ» — 8880 холдеров, топ-10 16%, "
                   "права mint/freeze отозваны; 08.11: алерт CABAL_EXPLOSION (30 пар, "
                   "предпочтение Meteora)",
    },
]

# ── пороги и тайминги ────────────────────────────────────────────────────────
PRICE_FAST_PCT = 15.0      # движение за ≤1ч
PRICE_DAY_PCT = 50.0       # движение за 24ч
LIQ_DROP_PCT = 15.0        # слив ликвидности за сутки
VOL_SPIKE_X = 5.0          # объём за час против среднего часового
SELL_RATIO = 0.5           # покупок/продаж за сутки ниже — продажи доминируют
SELL_MIN_VOL = 500_000.0   # ...но сообщаем только при таком объёме за сутки
SUPPLY_CHANGE_PCT = 0.5    # сжигание/допечатка саплая
NEW_PAIRS_24H = 3          # рост числа пар за сутки
ALERT_COOLDOWN_MIN = 120   # антиспам на тип алерта
METRIC_VERSION = 2         # v2 (19.11): цена/ликвидность/объём — только по парам SOL/USDC/USDT
CLEAN_QUOTES = frozenset({"SOL", "USDC", "USDT"})  # котировки, которым верим в USD
SANITY_JUMP_X = 10.0       # расхождение цены/ликвидности больше — битая запись пары
PRICE_SPREAD_X = 3.0       # цена пары дальше этого от медианы — запись не берём
EXOTIC_LIQ_X = 5.0         # экзотическая пара крупнее чистых в столько раз — сообщаем
DIGEST_UTC_HOUR = 4        # 04:00 UTC = 09:00 Бишкек
DIGEST_TREND_PCT = 15.0    # заметное суточное движение для вердикта
BISHKEK = timezone(timedelta(hours=5))
DEX_HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) RAB9/1.0"}
RPC_URL = "https://api.mainnet-beta.solana.com"


# ── окружение и доставка ─────────────────────────────────────────────────────
def now_bk() -> datetime:
    return datetime.now(timezone.utc).astimezone(BISHKEK)


# ── источники данных ─────────────────────────────────────────────────────────
def _get_json(url, timeout=20):
    req = urllib.request.Request(url, headers=DEX_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def rpc(method, params, attempts=4):
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params}).encode()
    for i in range(attempts):
        try:
            req = urllib.request.Request(RPC_URL, data=payload,
                                         headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            if "result" in data:
                return data["result"]
        except Exception:  # noqa: BLE001 — 429/таймауты публичного RPC
            time.sleep(1.5 * (i + 1))
    return None


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _median(values) -> float:
    vals = sorted(v for v in values if v > 0)
    if not vals:
        return 0.0
    n = len(vals)
    mid = n // 2
    return vals[mid] if n % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def _quote(p: dict) -> str:
    return str(((p.get("quoteToken") or {}).get("symbol")) or "").strip().upper()


def _liq_of(p: dict) -> float:
    return _f((p.get("liquidity") or {}).get("usd"))


def split_pairs(pairs):
    """Чистые пары (котировка SOL/USDC/USDT) и прочие — с экзотической котировкой."""
    valid = [p for p in pairs if isinstance(p, dict)]
    clean = [p for p in valid if _quote(p) in CLEAN_QUOTES]
    exotic = [p for p in valid if _quote(p) not in CLEAN_QUOTES]
    return clean, exotic


def pick_pair(pairs):
    """Глубочайшая ДОСТОВЕРНАЯ пара: чистая котировка + цена рядом с медианой.

    Битая USD-запись пары отбрасывается по расхождению с медианой, а не по
    ликвидности: 19.11 meteora CLAUDIA/MM отдала priceUsd $61.15 (ошибка ~×9600
    в курсе MM) при «ликвидности» $9.98 млн — по ликвидности она «побеждала».
    """
    clean, _ = split_pairs(pairs)
    pool = clean or [p for p in pairs if isinstance(p, dict)]
    if not pool:
        return None
    med = _median([_f(p.get("priceUsd")) for p in pool])
    if med:
        ok = [p for p in pool
              if _f(p.get("priceUsd")) > 0
              and max(_f(p.get("priceUsd")), med) / min(_f(p.get("priceUsd")), med) <= PRICE_SPREAD_X]
        if ok:
            pool = ok
    return max(pool, key=_liq_of)


def fetch_dex(mint: str) -> dict:
    """Сводка по токену: цена, ликвидность/объём, сделки, пары.

    Цена — медиана по парам с котировкой SOL/USDC/USDT; ликвидность и объём —
    суммы по ним же. Экзотические пары в расчёт не входят (см. пояснение в шапке).
    """
    out: dict = {"ok": False}
    try:
        data = _get_json("https://api.dexscreener.com/latest/dex/tokens/%s" % mint)
        pairs = [p for p in (data.get("pairs") or []) if isinstance(p, dict)]
        if not pairs:
            return out
        clean, exotic = split_pairs(pairs)
        best = pick_pair(pairs)
        if best is None:
            return out
        base = clean or pairs          # нет ни одной чистой пары — считаем по всем (как раньше)
        base = sorted(base, key=_liq_of, reverse=True)
        price = _median([_f(p.get("priceUsd")) for p in base]) or _f(best.get("priceUsd"))
        best_price = _f(best.get("priceUsd"))
        best_mc = _f(best.get("marketCap"))
        implied_supply = (best_mc / best_price) if best_price else 0.0
        txns = (best.get("txns") or {}).get("h24") or {}
        buys, sells = txns.get("buys"), txns.get("sells")
        ratio = round(_f(buys) / _f(sells), 2) if _f(sells) > 0 else None
        exotic_sorted = sorted(exotic, key=_liq_of, reverse=True)
        top = exotic_sorted[0] if exotic_sorted else None
        out.update({
            "ok": True,
            "price": price or None,
            # MC считаем по той же цене, что показываем: иначе цифры расходятся
            "mc": round(price * implied_supply) if (price and implied_supply) else (best_mc or None),
            "liq": sum(_liq_of(p) for p in base),
            "vol24": sum(_f((p.get("volume") or {}).get("h24")) for p in base),
            "vol1h": sum(_f((p.get("volume") or {}).get("h1")) for p in base),
            "chg_1h": _f((best.get("priceChange") or {}).get("h1")),
            "chg_24h": _f((best.get("priceChange") or {}).get("h24")),
            "buys": buys, "sells": sells, "ratio": ratio,
            "pairs": len(pairs),
            "clean_pairs": len(base),
            "exotic_pairs": len(exotic),
            "exotic_liq": sum(_liq_of(p) for p in exotic),
            "exotic_top": ({
                "pair": top.get("pairAddress") or "",
                "dex": top.get("dexId") or "?",
                "quote": _quote(top) or "?",
                "role": ("base" if str(((top.get("baseToken") or {}).get("address")) or "") == mint else "quote"),
                "price": _f(top.get("priceUsd")),
                "liq": _liq_of(top),
                "vol24": _f((top.get("volume") or {}).get("h24")),
                "url": top.get("url") or "",
            } if top else None),
            "dexes": len({p.get("dexId") for p in pairs}),
            "pool_url": best.get("url") or (base[0].get("url") if base else None),
        })
    except Exception:  # noqa: BLE001 — DexScreener недоступен: тишина, не спамим
        pass
    return out


def fetch_supply(mint: str):
    res = rpc("getTokenSupply", [mint])
    if not res:
        return None
    val = _f((res.get("value") or {}).get("uiAmountString"))
    return val or None


def fetch_authorities(mint: str) -> dict:
    """Один раз на токен: отозваны ли права минта/заморозки (safety-строка)."""
    res = rpc("getAccountInfo", [mint, {"encoding": "jsonParsed"}])
    value = (res or {}).get("value") or {}
    info = (((value.get("data") or {}).get("parsed") or {}).get("info")) or {}
    if not info:
        return {}
    return {"mint_authority": info.get("mintAuthority"),
            "freeze_authority": info.get("freezeAuthority"),
            "decimals": info.get("decimals")}


# ── состояние ────────────────────────────────────────────────────────────────
def load_state() -> dict:
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            backup = STATE_PATH.with_name(
                "%s.corrupt-%s" % (STATE_PATH.name, datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")))
            try:
                STATE_PATH.replace(backup)
                print("повреждённый снапшот сохранён: %s (%s)" % (backup, exc), file=sys.stderr)
            except OSError as backup_exc:
                print("снапшот повреждён и не изолирован: %s" % backup_exc, file=sys.stderr)
        except OSError as exc:
            print("снапшот не прочитан: %s" % exc, file=sys.stderr)
    return {"tokens": {}}


def save_state(state: dict) -> bool:
    """Атомарная запись снапшота (CP-5: tmp → replace)."""
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(STATE_PATH)
        return True
    except OSError as exc:
        print("снапшот не сохранён: %s" % exc, file=sys.stderr)
        return False


# ── форматирование ───────────────────────────────────────────────────────────
def fp(v):
    v = _f(v)
    if not v:
        return "н/д"
    return ("$%.6f" % v) if v >= 0.001 else ("$%.8f" % v)


def fu(v):
    v = _f(v)
    if v >= 1_000_000:
        return "$%.2f млн" % (v / 1_000_000)
    if v >= 1_000:
        return "$%.1f тыс." % (v / 1_000)
    return "$%.0f" % v


def fnum(v):
    try:
        return "{:,}".format(int(float(v))).replace(",", " ")
    except (TypeError, ValueError):
        return "н/д"


def short(mint: str) -> str:
    return mint[:6] + "…" + mint[-4:]


def ratio_tag(r):
    if r is None:
        return "нет данных"
    if r >= 1.3:
        return "покупки доминируют"
    if r < SELL_RATIO:
        return "продажи доминируют ⚠️"
    return "смешанно"


# ── алерты ───────────────────────────────────────────────────────────────────
def can_alert(tstate: dict, kind: str) -> bool:
    last = (tstate.get("last_alert") or {}).get(kind)
    if not last:
        return True
    try:
        ts = datetime.fromisoformat(last)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - ts) >= timedelta(minutes=ALERT_COOLDOWN_MIN)


def mark_alert(tstate: dict, kind: str) -> None:
    tstate.setdefault("last_alert", {})[kind] = datetime.now(timezone.utc).isoformat()


def _snap_ago(snaps, now, hours):
    target = now - timedelta(hours=hours)
    cands = [s for s in snaps if datetime.fromisoformat(s["ts"]) <= target]
    if cands:
        return cands[-1]
    return snaps[0] if snaps else None


def _prune_poisoned(snaps, price, liq):
    """Убирает из истории тики, записанные по битой USD-оценке пары.

    Скачок цены или ликвидности больше SANITY_JUMP_X раз — это не рынок, а
    артефакт источника: такой тик остаётся в серии и потом 24 ч выдаёт ложные
    «падение цены» и «слив ликвидности» на возврате к достоверной цифре.
    """
    keep, dropped = [], 0
    for s in snaps:
        sp, sl = _f(s.get("price")), _f(s.get("liq"))
        bad = False
        if price and sp and max(sp, price) / min(sp, price) > SANITY_JUMP_X:
            bad = True
        if liq and sl and max(sl, liq) / min(sl, liq) > SANITY_JUMP_X:
            bad = True
        if bad:
            dropped += 1
        else:
            keep.append(s)
    return keep, dropped


def handle_token(cfg: dict, state: dict) -> list:
    """Проверяет один токен; возвращает список сообщений к отправке."""
    mint = cfg["mint"]
    ts = state.setdefault("tokens", {}).setdefault(mint, {"snapshots": [], "last_alert": {}})
    msgs = []

    dex = fetch_dex(mint)
    if not dex.get("ok") or dex.get("price") is None:
        return msgs  # источник молчит — тишина, не спамим

    price, liq, vol24 = _f(dex["price"]), _f(dex["liq"]), _f(dex["vol24"])
    now = datetime.now(timezone.utc)
    snaps = ts.get("snapshots") or []
    stamp = now_bk().strftime("%d.%m %H:%M")

    # история: битые тики (USD-оценка пары через экзотическую валюту) не храним
    snaps, dropped = _prune_poisoned(snaps, price, liq)
    if dropped:
        print("%s: из истории убрано %d тиков с битой USD-оценкой пары" % (cfg["symbol"], dropped),
              file=sys.stderr)

    # санити-гейт: скачок больше ×10 за тик — аномалия источника, а не рынок
    prev_price = _f(ts.get("last_price"))
    anomaly = bool(prev_price and price and max(price, prev_price) / min(price, prev_price) > SANITY_JUMP_X)
    if anomaly:
        print("%s: аномалия источника — цена %s против %s предыдущего тика (×%.0f), "
              "алерты по цене подавлены, база пересчитана"
              % (cfg["symbol"], fp(price), fp(prev_price),
                 max(price, prev_price) / min(price, prev_price)), file=sys.stderr)

    # смена методики: цифры старой серии считались по всем парам (включая битые),
    # сравнивать их с новыми нельзя — иначе ложное «ликвидность уходит» на ровном месте
    rebase = ts.get("metric_version") != METRIC_VERSION
    if rebase:
        print("%s: методика расчёта v%s → v%d — старая история несравнима, серия начата заново, "
              "алерты по истории пропущены на один тик"
              % (cfg["symbol"], ts.get("metric_version") or 1, METRIC_VERSION), file=sys.stderr)
        ts["snapshots"] = snaps = []
    ts["metric_version"] = METRIC_VERSION

    auth = ts.get("authorities") or fetch_authorities(mint)
    if auth:
        ts["authorities"] = auth

    # первое касание: база + объявление владельцу, что наблюдение живо
    if not ts.get("announced"):
        sup = fetch_supply(mint)
        ts["announced"] = now_bk().isoformat()
        if sup:
            ts["base_supply"] = sup
        msgs.append(
            "👀 ВЗЯТ ПОД НАБЛЮДЕНИЕ: %s\n"
            "🪙 Минт: %s\n"
            "💵 Цена: %s | Капитализация: %s\n"
            "💧 Ликвидность (по парам SOL/USDC/USDT): %s | Объём 24ч: %s\n"
            "🛠 Пар: %d на %d DEX | Права минта: %s | Права заморозки: %s\n"
            "📦 Саплай: %s токенов\n"
            "ℹ️ Контекст: %s\n"
            "🔔 Дальше молчу и пишу только при аномалии: резкое движение цены, слив "
            "ликвидности, всплеск объёма, перевес продаж, изменение саплая, размножение пар. "
            "Раз в сутки в 09:00 (Бишкек) — короткая сводка."
            % (cfg["symbol"], short(mint), fp(price), fu(dex.get("mc")), fu(liq), fu(vol24),
               dex["pairs"], dex["dexes"],
               "н/д" if not auth else ("отозваны ✅" if auth.get("mint_authority") is None else "АКТИВНЫ ⚠️"),
               "н/д" if not auth else ("отозваны ✅" if auth.get("freeze_authority") is None else "АКТИВНЫ ⚠️"),
               fnum(ts.get("base_supply") or 0), cfg.get("history") or "нет"))

    s1h, s24h = _snap_ago(snaps, now, 1), _snap_ago(snaps, now, 24)

    # 1. резкое движение цены (при аномалии источника не сравниваем — база битая)
    for kind, snap, th, label in (("price_1h", s1h, PRICE_FAST_PCT, "за час"),
                                  ("price_24h", s24h, PRICE_DAY_PCT, "за сутки")):
        if anomaly or not can_alert(ts, kind):
            continue
        ref = _f((snap or {}).get("price"))
        if not ref:
            continue
        delta = (price - ref) / ref * 100.0
        if abs(delta) >= th:
            msgs.append(
                "%s ЦЕНЫ: %s (%s)\n"
                "💵 %s → %s (%+.1f%%)\n"
                "💰 Капитализация: %s | Ликвидность: %s | Объём 24ч: %s\n"
                "📊 Покупок/продаж 24ч: %s/%s — %s\n"
                "⏱ %s Бишкек"
                % ("🚀 РОСТ" if delta > 0 else "📉 ПАДЕНИЕ", cfg["symbol"], label,
                   fp(ref), fp(price), delta, fu(dex.get("mc")), fu(liq), fu(vol24),
                   fnum(dex.get("buys")), fnum(dex.get("sells")), ratio_tag(dex.get("ratio")),
                   stamp))
            mark_alert(ts, kind)
            break

    # 1b. пара вне расчёта — экзотическая котировка с «ликвидностью» больше чистых пар
    top_exotic = dex.get("exotic_top")
    if top_exotic and liq and _f(top_exotic.get("liq")) >= EXOTIC_LIQ_X * liq:
        seen = ts.setdefault("exotic_seen", {})
        if top_exotic.get("pair") and top_exotic["pair"] not in seen:
            seen[top_exotic["pair"]] = now.isoformat()
            if len(seen) > 50:      # держим журнал коротким
                for old in sorted(seen, key=lambda k: seen[k])[:-50]:
                    seen.pop(old, None)
            diverg = (_f(top_exotic.get("price")) / price) if price else 0.0
            role = top_exotic.get("role")
            msgs.append(
                "🧪 ПАРА ВНЕ РАСЧЁТА: %s\n"
                "🛠 %s %s/%s — «ликвидность» %s против %s по парам SOL/USDC/USDT\n"
                "💵 Её priceUsd: %s%s\n"
                "🔎 Что это значит: %s Наша цена — %s (медиана по парам SOL/USDC/USDT),\n"
                "   MC и ликвидность считаются без этой пары — на витрине DexScreener цифры\n"
                "   по токену могут быть в разы больше.\n"
                "🪙 Пара: %s\n"
                "🔗 %s\n"
                "⏱ %s Бишкек"
                % (cfg["symbol"], top_exotic.get("dex"), top_exotic.get("quote"),
                   cfg["symbol"] if role == "base" else "вне расчёта",
                   fu(top_exotic.get("liq")), fu(liq), fp(top_exotic.get("price")),
                   (" — против %s у нас (расхождение ×%.0f)" % (fp(price), diverg)) if (diverg >= SANITY_JUMP_X and role == "base") else "",
                   ("наш токен в этой паре котируемый — её USD-цифры к нашей цене вообще не относятся."
                    if role != "base" else
                    "USD-оценка такой пары у DexScreener считается через курс экзотической "
                    "валюты и бывает битой (19.11 meteora CLAUDIA/MM: priceUsd $61.15 при "
                    "реальных $0.0064, MC $58 млрд против реальных ~$6 млн)."),
                   fp(price), top_exotic.get("pair"), top_exotic.get("url") or "н/д", stamp))

    # 2. слив ликвидности
    if can_alert(ts, "liq"):
        ref_liq = _f((s24h or {}).get("liq"))
        peak = max([_f(s.get("liq")) for s in snaps] + [liq]) if snaps else liq
        d_ref = (liq - ref_liq) / ref_liq * 100.0 if ref_liq else 0.0
        d_peak = (liq - peak) / peak * 100.0 if peak else 0.0
        if ref_liq and (d_ref <= -LIQ_DROP_PCT or d_peak <= -LIQ_DROP_PCT):
            msgs.append(
                "⚠️ ЛИКВИДНОСТЬ УХОДИТ: %s\n"
                "💧 Сейчас: %s | сутки назад: %s (%+.1f%%)\n"
                "📉 От суточного максимума (%s): %+.1f%%\n"
                "💵 Цена: %s | Объём 24ч: %s\n"
                "🔎 Что это значит: ликвидность выводят из пула — падение цены идёт без "
                "сопротивления, вплоть до полного вывода (rug). Проверьте пул вручную.\n"
                "🔗 %s\n"
                "⏱ %s Бишкек"
                % (cfg["symbol"], fu(liq), fu(ref_liq), d_ref, fu(peak), d_peak,
                   fp(price), fu(vol24), dex.get("pool_url") or "н/д", stamp))
            mark_alert(ts, "liq")

    # 3. всплеск объёма
    if can_alert(ts, "vol") and vol24 > 0:
        avg_h = vol24 / 24.0
        if avg_h > 0 and _f(dex.get("vol1h")) >= VOL_SPIKE_X * avg_h:
            msgs.append(
                "🔊 ВСПЛЕСК ОБЪЁМА: %s\n"
                "📊 За последний час: %s | средний час за сутки: %s (в %.1f раза больше)\n"
                "💵 Цена: %s (%+.1f%% за час, %+.1f%% за сутки)\n"
                "🤝 Сделки за сутки: %s покупок / %s продаж\n"
                "🔎 Что это значит: в рынок пришли деньги — либо разгон на новостях, либо "
                "крупный слив в стакан (смотрите сторону по цене).\n"
                "⏱ %s Бишкек"
                % (cfg["symbol"], fu(dex.get("vol1h")), fu(avg_h),
                   _f(dex.get("vol1h")) / avg_h, fp(price), dex.get("chg_1h") or 0,
                   dex.get("chg_24h") or 0, fnum(dex.get("buys")), fnum(dex.get("sells")), stamp))
            mark_alert(ts, "vol")

    # 4. перевес продаж
    ratio = dex.get("ratio")
    if can_alert(ts, "sell") and vol24 >= SELL_MIN_VOL and ratio is not None and ratio < SELL_RATIO:
        msgs.append(
            "🔻 ПЕРЕВЕС ПРОДАЖ: %s\n"
            "🤝 За сутки: %s покупок / %s продаж (соотношение %.2f)\n"
            "💵 Цена: %s (%+.1f%% за сутки) | Объём 24ч: %s\n"
            "🔎 Что это значит: при таком объёме продавцы активно выходят — рост держится "
            "на встречных покупках, риск продолжения вниз.\n"
            "⏱ %s Бишкек"
            % (cfg["symbol"], fnum(dex.get("buys")), fnum(dex.get("sells")), ratio,
               fp(price), dex.get("chg_24h") or 0, fu(vol24), stamp))
        mark_alert(ts, "sell")

    # 5. изменение саплая (сжигание печью / допечатка)
    sup = fetch_supply(mint)
    if sup:
        base = ts.get("base_supply")
        if base:
            d_sup = (sup - _f(base)) / _f(base) * 100.0 if _f(base) else 0.0
            if abs(d_sup) >= SUPPLY_CHANGE_PCT and can_alert(ts, "supply"):
                msgs.append(
                    "%s САПЛАЯ: %s\n"
                    "📦 %s → %s токенов (%+.2f%%)\n"
                    "🔎 Что это значит: сжигание уменьшает число токенов (дефляция, цену "
                    "само по себе не двигает); допечатка возможна только при живых правах "
                    "минта — это угроза размытия доли.\n"
                    "⏱ %s Бишкек"
                    % ("🔥 СЖИГАНИЕ" if d_sup < 0 else "⚠️ ДОПЕЧАТКА", cfg["symbol"],
                       fnum(base), fnum(sup), d_sup, stamp))
                mark_alert(ts, "supply")
        ts["base_supply"] = sup

    # 6. размножение пар (в пайплайне RAB9 — признак кабала)
    if can_alert(ts, "pairs") and len(snaps) >= 4:
        oldest = _snap_ago(snaps, now, 24) or snaps[0]
        grew = dex["pairs"] - int(oldest.get("pairs") or dex["pairs"])
        if grew >= NEW_PAIRS_24H:
            window_h = (now - datetime.fromisoformat(oldest["ts"])).total_seconds() / 3600.0
            msgs.append(
                "🧬 РАЗМНОЖЕНИЕ ПАР: %s\n"
                "🛠 Пар: %d → %d (+%d за %.0f ч), DEX-ов: %d\n"
                "💵 Цена: %s | Ликвидность: %s | Объём 24ч: %s\n"
                "🔎 Что это значит: новые пулы на разных DEX — в нашем пайплайне это "
                "признак кабала (по этому токену 08.11 был алерт CABAL_EXPLOSION). "
                "Проверяем, не размазывают ли объём по пулам.\n"
                "⏱ %s Бишкек"
                % (cfg["symbol"], int(oldest.get("pairs") or 0), dex["pairs"], grew,
                   window_h, dex["dexes"], fp(price), fu(liq), fu(vol24), stamp))
            mark_alert(ts, "pairs")

    ts["last_price"] = price
    ts["last_liq"] = liq
    snaps.append({"ts": now.isoformat(), "price": price, "liq": liq,
                  "vol24": vol24, "pairs": dex["pairs"]})
    ts["snapshots"] = snaps[-120:]  # ~30 ч при тике раз в 15 мин
    return msgs


def maybe_digest(cfg: dict, state: dict) -> list:
    """Короткая суточная сводка в 04:00 UTC (09:00 Бишкек)."""
    mint = cfg["mint"]
    ts = state.setdefault("tokens", {}).setdefault(mint, {})
    now = datetime.now(timezone.utc)
    if now.hour != DIGEST_UTC_HOUR:
        return []
    today = now_bk().strftime("%Y-%m-%d")
    if ts.get("last_digest") == today:
        return []
    dex = fetch_dex(mint)
    if not dex.get("ok") or dex.get("price") is None:
        return []
    ts["last_digest"] = today
    ratio = dex.get("ratio")
    chg = dex.get("chg_24h") or 0
    if chg >= DIGEST_TREND_PCT and _f(ratio) >= 1.0:
        verdict = "🟢 РАЗОГРЕВ — цена растёт на покупках"
    elif chg <= -DIGEST_TREND_PCT:
        verdict = "🔴 ОТКАТ — за сутки заметное падение"
    elif ratio is not None and ratio < SELL_RATIO:
        verdict = "🟡 СЛАБОСТЬ — продажи перевешивают"
    else:
        verdict = "⚪ БОКОВИК — выраженного перевеса нет"
    exotic_line = ""
    exotic_n = _f(dex.get("exotic_pairs"))
    if exotic_n:
        exotic_line = ("🧪 Вне расчёта: %d пар с экзотической котировкой — их «ликвидность» %s "
                       "по данным DexScreener в цену/MC/ликвидность не входит\n"
                       % (int(exotic_n), fu(dex.get("exotic_liq"))))
    return [
        "🗒 СВОДКА ЗА СУТКИ — %s\n"
        "💵 Цена: %s (%+.1f%% за 24ч) | Капитализация: %s\n"
        "💧 Ликвидность: %s | Объём 24ч: %s\n"
        "🤝 Сделки 24ч: %s покупок / %s продаж\n"
        "🛠 Пар: %d на %d DEX\n"
        "%s"
        "📌 Вердикт: %s\n"
        "📎 %s"
        % (cfg["symbol"], fp(dex.get("price")), chg, fu(dex.get("mc")), fu(dex.get("liq")),
           fu(dex.get("vol24")), fnum(dex.get("buys")), fnum(dex.get("sells")),
           dex["pairs"], dex["dexes"], exotic_line, verdict, dex.get("pool_url") or "")
    ]


def main() -> int:
    state = load_state()
    out: list = []
    for cfg in TOKENS:
        try:
            out.extend(handle_token(cfg, state))
            out.extend(maybe_digest(cfg, state))
        except Exception as exc:  # noqa: BLE001 — один токен не должен ломать остальные
            print("%s: %s" % (cfg.get("symbol"), exc), file=sys.stderr)
    if not save_state(state):
        print("сообщения подавлены: состояние не удалось сохранить", file=sys.stderr)
        return 1
    for msg in out:
        print(msg)          # stdout → доставка кроном (deliver=telegram)
    return 0


if __name__ == "__main__":
    sys.exit(main())
