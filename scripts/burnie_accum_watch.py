#!/usr/bin/env python3
"""BURNIE accumulator watch: net-flow + продажи кошельков-аккумуляторов.

Snapshot: data/burnie_accum_watch.json (создан 2026-09-25, 25 кошельков, net +$737K).
Логика: gmgn-cli token traders → по каждому кошельку из снапшота сравнить
net_buy_usd и sells с сохранёнными; DexScreener → цена/MC.
Вывод ТОЛЬКО отклонения (пустой stdout = тихий тик).
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

MINT = "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump"
TOKEN_DECIMALS = 6   # pump.fun: суммы GMGN приходят в UI-единицах, а снапшот supply — в raw
GMGN = "/home/hermes-workspace/.hermes/node/bin/gmgn-cli"
HERE = Path(__file__).resolve().parent
SNAP = HERE.parent / "data" / "burnie_accum_watch.json"

ALERT_NET_USD = 1000      # докупка от $1K
ALERT_SELL_PCT = 0.25     # продал >25% своего net-объёма

# Пакетные переводы (решение Сергея 08.11). Разбор топ-холдеров показал: часть
# «крупных покупателей» покупок не делала вообще — токены пришли переводом
# (history_bought_cost == 0), один помечен bundler. Рост числа холдеров без
# покупок = дробление пакета, т.е. ранний признак подготовки к дампу, а не
# смартмани-накопление. Следим за этим как за отдельным событием.
PACKAGE_MIN_PCT = 0.5      # перевод ≥0.5% саплая = событие
PACKAGE_LOOKBACK_H = 72    # окно поиска (переживает простой крона)
DIST_MIN_WALLETS = 3       # один источник → ≥3 кошелька
DIST_MIN_TOTAL_PCT = 1.0   # при суммарном объёме ≥1% саплая
TRANSFER_SEEN_CAP = 300    # сколько tx_hash держим для дедупа

# Сжигания (решение Сергея 12.11). Кошелёк проекта собирает creator fees
# (инструкция TransferCreatorFeesToPump), выкупает токен с рынка и жжёт его —
# «печь» из их твитов. Подтверждено 12.11 00:11: покупка 8,238,661 BURNIE за
# 97.087 SOL и через минуту BurnChecked на 11,575,437 BURNIE. Без распознавания
# BurnChecked падение холда читается как «КИТ ВЫШЕЛ», хотя токены не ушли в рынок.
BURN_WATCH_WALLETS = ["7YeCaAqhzhtRio1mddqaQzhvWRWXEsm4GSyfm4VwDsvL"]
BURN_SCAN_LIMIT = 40        # сколько последних tx смотреть у кошелька-печи
BURN_SEEN_CAP = 300         # дедуп tx_hash сжиганий
BURN_RESCAN_H = 4           # не чаще раза в 4ч на кошелёк (RPC дорогой)
BURN_ALERT_MIN_PCT = 0.05   # сжигание ≥0.05% саплая = событие
TRANSFER_VERIFY_CAP = 12     # максимум транзакций, проверяемых по цепочке за тик
BURN_LOG_CAP = 200          # журнал сжиганий (для атрибуции просадки)
BURN_ATTR_DAYS = 30         # окно атрибуции «просадка = печь»
BURN_ATTR_MIN_SHARE = 0.5   # ≥50% просадки ушло в сжигание → это печь, не продажа

# Пулы/пара: если они в accountKeys транзакции — токены пришли из свопа (покупка),
# а не переводом от кошелька. Без этой проверки покупка в пуле выдавалась за «раздачу».
AMM_ACCOUNTS = {
    "5tYFviFWQRKV9BJSTHGitbdqEYC1BGUgRUDnSADUXqJP",   # основная пара (DexScreener)
    "EgGACLzNtvTWfjWopkMbbcRsUPAaSCcgPjbNqUCcLUCJ",   # пул Meteora
}

# База pct ставилась под снапшотный supply (25.09) — сравнение долей при
# сожжённом supply некорректно, поэтому базу переводим в токены.
BASE_SUPPLY_UI_AT_BASELINE = 969651601.137694


def fetch_traders():
    # gmgn rate limit — общий на IP VPS (429 RETE_LIMIT_EXCEEDED): ретрай с паузой
    # до сброса окна (лимит в ошибке ~30с; ждём 35с + ретрай до 3 раз).
    for attempt in range(1, 4):
        out = subprocess.run(
            [GMGN, "token", "traders", "--chain", "sol", "--address", MINT],
            capture_output=True, text=True, timeout=90,
        )
        if out.returncode == 0 or "RATE_LIMIT_EXCEEDED" not in (out.stderr or ""):
            break
        wait = 35 * attempt
        print(f"⚠️ gmgn 429 RATE_LIMIT_EXCEEDED (attempt {attempt}) — retry in {wait}s")
        time.sleep(wait)
    if out.returncode != 0:
        print(f"⚠️ gmgn-cli traders fail rc={out.returncode}: {out.stderr[:200]}")
        sys.exit(0)
    return json.loads(out.stdout).get("list") or []


def fetch_price():
    try:
        req = urllib.request.Request(
            f"https://api.dexscreener.com/latest/dex/tokens/{MINT}",
            headers={"User-Agent": "rab9/1.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            pairs = json.load(r).get("pairs") or []
        if not pairs:
            return None
        p = max(pairs, key=lambda x: (x.get("liquidity") or {}).get("usd") or 0)
        return {
            "price": p.get("priceUsd"),
            "mc": p.get("marketCap"),
            "liq": (p.get("liquidity") or {}).get("usd"),
            "chg24h": (p.get("priceChange") or {}).get("h24"),
        }
    except Exception as e:
        print(f"⚠️ DexScreener fail: {e}")
        return None


def fetch_holders():
    # Топ-100 холдеров: для авто-пополнения watch-списка новыми китами (29.10).
    out: subprocess.CompletedProcess | None = None
    for attempt in range(1, 4):
        out = subprocess.run(
            [GMGN, "token", "holders", "--chain", "sol", "--address", MINT],
            capture_output=True, text=True, timeout=90,
        )
        if out.returncode == 0 or "RATE_LIMIT_EXCEEDED" not in (out.stderr or ""):
            break
        wait = 35 * attempt
        print(f"⚠️ gmgn 429 RATE_LIMIT_EXCEEDED (attempt {attempt}) — retry in {wait}s")
        time.sleep(wait)
    if out.returncode != 0:
        print(f"⚠️ gmgn-cli holders fail rc={out.returncode}: {out.stderr[:200]}")
        return []
    return json.loads(out.stdout).get("list") or []


NEW_WALLET_MIN_PCT = 0.9    # ≥0.9% саплая
NEW_WALLET_MIN_NET = 10000  # и net-buy ≥ $10K (не спекулянт-однодневка)


def enroll_new_wallets(snap: dict, by_addr: dict, holders: list | None = None) -> list[str]:
    """Авто-пополнение watch: новый холдер ≥0.9% + net-buy ≥$10K → в снапшот с tag=new-<date>.

    Решение Сергея 29.10 («осень, горячее время, реагировать быстро»): новое
    накопление не должно месяцами жить вне радара. Возвращает строки-алерты.

    Решение Сергея 08.11: НЕ зачисляем bundler-кошельки и адреса без покупок
    (токены пришли переводом) — это распределение пакета, а не накопление;
    такие адреса ведёт detect_package_transfers(), а не список «накопителей».
    """
    added = []
    known = {w["address"] for w in snap["wallets"]}
    today = time.strftime("%Y%m%d")
    for h in (holders if holders is not None else fetch_holders()):
        # GMGN holders: поле address/account_address НЕ консистентно по строкам
        # (то владелец, то токен-аккаунт). Владелец = тот, кто есть в traders-map
        # (by_addr ключи = владельцы); иначе candidate = address.
        cands = [c for c in (h.get("address"), h.get("account_address")) if c]
        a = next((c for c in cands if c in by_addr), None) or h.get("address")
        # Владелец уже в watch (в любом из полей) — не дублируем токен-аккаунтом
        if any(c in known for c in cands):
            continue
        if not a or a == MINT or a in known:
            continue
        if h.get("addr_type") == 2 or h.get("exchange"):
            continue  # пул/биржа — не кит
        if "bundler" in (h.get("maker_token_tags") or []):
            continue  # бандл-кошелёк (08.11): токены розданы пачкой, покупок нет
        if not (h.get("history_bought_cost") or 0) and (h.get("history_transfer_in_amount") or 0) > 0:
            continue  # пришло переводом — не «накопление» (08.11)
        pct = round((h.get("amount_percentage") or 0) * 100, 2)
        cur = by_addr.get(a)
        if pct < NEW_WALLET_MIN_PCT or not cur or cur["net"] < NEW_WALLET_MIN_NET:
            continue
        w = {
            "address": a, "pct": pct, "baseline_pct": pct,
            # База в токенах: проценты при сжигаемом supply несравнимы между тиками.
            "base_tokens": round(pct / 100 * ((snap.get("supply") or 0) / (10 ** TOKEN_DECIMALS)), 2),
            "net_buy_usd": round(cur["net"]), "avg_buy_usd": 0,
            "buys": h.get("accu_tx_count_buy") or 0, "sells": cur["sells"],
            "tag": f"new-{today}",
        }
        snap["wallets"].append(w)
        known.add(a)
        added.append(
            f"🆕 НОВЫЙ КИТ В WATCH: {a}\n"
            f"   {pct}% саплая, накопил ${cur['net']:,.0f} (покупок {w['buys']}, продаж {w['sells']}). "
            f"Вне старого списка 25.09 — раньше был невидим."
        )
    if added:
        snap["wallets"].sort(key=lambda x: -(x.get("pct") or 0))
    return added


def detect_package_transfers(snap: dict, holders: list) -> list[str]:
    """Пакеты, пришедшие ПЕРЕВОДОМ: признак распределения, а не накопления.

    Разбор 08.11: из 7 холдеров ≥0.9% вне watch у трёх покупок на $0 —
    токены пришли transfer_in (один адрес помечен bundler). Рост холдеров
    без покупок = дробление пакета, т.е. подготовка к дампу. Дедуп по tx_hash:
    одно событие = один алерт (иначе повтор каждый тик 4×/день).
    """
    supply = snap.get("supply") or 0
    if not supply or not holders:
        return []
    # Снапшот хранит supply в raw-единицах (его использует measure_holdings с RPC,
    # где amounts тоже raw), а GMGN отдаёт суммы уже в UI-единицах: без приведения
    # доли получаются в 10^6 раз меньше и порог события не срабатывает никогда.
    supply_ui = supply / (10 ** TOKEN_DECIMALS)
    seen = snap.setdefault("transfer_seen", {})
    cutoff = time.time() - PACKAGE_LOOKBACK_H * 3600
    events = []
    checked = 0
    for h in holders:
        if h.get("addr_type") == 2 or h.get("exchange"):
            continue
        ti = h.get("token_transfer_in") or {}
        tx = ti.get("tx_hash") or ""
        ts = ti.get("timestamp") or 0
        if not tx or ts < cutoff or tx in seen:
            continue
        if checked >= TRANSFER_VERIFY_CAP:
            break  # защита от лавины RPC-запросов в горячем рынке
        checked += 1
        addr = h.get("address") or ""
        # GMGN даёт только НАКОПЛЕННУЮ сумму и последнюю транзакцию — сумму и сторону
        # берём из самой транзакции, иначе алерт врёт (см. classify_transfer_tx).
        chain = classify_transfer_tx(tx, addr)
        seen[tx] = _now_iso()  # транзакция неизменна: второй раз не проверяем
        if not chain or (chain.get("delta") or 0) <= 0:
            continue  # прихода по цепочке нет — GMGN-строка не про этот перевод
        if chain.get("market"):
            continue  # токены вышли из пула = покупка в рынке, а не перевод; раздачей не является
        events.append({
            "addr": addr,
            "tokens": chain["delta"],
            "pct": round(chain["delta"] / supply_ui * 100, 3),
            "src": chain.get("src") or (ti.get("address") or ""),
            "ts": chain.get("ts") or ts,
            "tx": tx,
            "bought": h.get("history_bought_cost") or 0,
            "tags": h.get("maker_token_tags") or [],
            "one_hand": chain.get("one_hand"),
        })

    out = []
    for e in events:
        if e["pct"] < PACKAGE_MIN_PCT:
            continue
        out.append(
            f"📦 ПЕРЕВОД ПАКЕТА (по цепочке): {e['tokens']:,.0f} токенов = {e['pct']}% саплая\n"
            f"   от {e['src'][:8]}… → {e['addr'][:12]}…, покупок у получателя на ${e['bought']:,.0f}"
            f"{', тег bundler' if 'bundler' in e['tags'] else ''}"
            f"{', перевод подписан третьим адресом — одна рука/бот' if e['one_hand'] else ''}. "
            f"Это распределение пакета, а не накопление."
        )

    # Групповой признак: один источник раздаёт пачками нескольким кошелькам —
    # так пакет дробят перед сбросом в рынок.
    by_src = {}
    for e in events:
        if not e["src"]:
            continue
        g = by_src.setdefault(e["src"], {"n": 0, "total": 0.0, "ts": e["ts"]})
        g["n"] += 1
        g["total"] = round(g["total"] + e["pct"], 3)
        g["ts"] = min(g["ts"], e["ts"])
    for src, g in by_src.items():
        key = f"dist:{src}:{int(g['ts'])}"
        if g["n"] < DIST_MIN_WALLETS or g["total"] < DIST_MIN_TOTAL_PCT or key in seen:
            continue
        seen[key] = _now_iso()
        out.append(
            f"🔀 РАСПРЕДЕЛЕНИЕ ПАКЕТА: {src} раздал {g['n']} кошелькам суммарно {g['total']}% саплая "
            f"за последние {PACKAGE_LOOKBACK_H}ч — ранний признак подготовки к сбросу."
        )

    # Дедуп-журнал не растёт бесконечно (dict хранит порядок вставки).
    while len(seen) > TRANSFER_SEEN_CAP:
        seen.pop(next(iter(seen)))
    return out


def _rpc(method: str, params: list, tries: int = 4):
    """JSON-RPC с ретраями: публичный RPC периодически отдаёт 429."""
    for attempt in range(tries):
        try:
            body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
            req = urllib.request.Request(
                "https://api.mainnet-beta.solana.com", body, {"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=25) as r:
                res = json.load(r)
            if "result" in res:
                return res
            if "429" in str(res.get("error")):
                time.sleep(3 + 2 * attempt)
                continue
            return res
        except Exception:
            time.sleep(3 + 2 * attempt)
    return {}


def fetch_live_supply():
    """Живой total supply (raw). Снапшот 25.09 устарел: с тех пор сожжено 31.85M.

    Все доли саплая считались от 969.65M, тогда как живая supply 937.81M —
    систематическая ошибка 3.4% во ВСЕХ процентах вотча (найдено 12.11).
    """
    res = _rpc("getTokenSupply", [MINT])
    try:
        return int((res.get("result") or {}).get("value", {}).get("amount"))
    except (TypeError, ValueError):
        return None


def _burn_log_add(snap: dict, wallet: str, burns: list) -> list:
    """Добавить сжигания в журнал, вернуть ТОЛЬКО новые (дедуп по tx_hash)."""
    log = snap.setdefault("burn_log", [])
    seen = {e.get("tx") for e in log}
    fresh = []
    for b in burns:
        if not b.get("tx") or b["tx"] in seen:
            continue
        log.append({"wallet": wallet, "tx": b["tx"], "ts": b.get("ts") or 0, "tokens": b.get("tokens") or 0})
        seen.add(b["tx"])
        fresh.append(b)
    if len(log) > BURN_LOG_CAP:
        del log[: len(log) - BURN_LOG_CAP]
    return fresh


def burn_log_total(snap: dict, wallet: str, days: int = BURN_ATTR_DAYS) -> float:
    """Сколько токенов этот кошелёк сжёг за окно (по журналу)."""
    cutoff = time.time() - days * 86400
    return sum(
        e.get("tokens") or 0
        for e in (snap.get("burn_log") or [])
        if e.get("wallet") == wallet and (e.get("ts") or 0) >= cutoff
    )


def scan_wallet_burns(addr: str, limit: int = BURN_SCAN_LIMIT) -> list:
    """Сжигания (BurnChecked) в последних tx кошелька: [{tx, ts, tokens}]."""
    raw = (_rpc("getSignaturesForAddress", [addr, {"limit": limit}]).get("result") or [])
    sigs = [s for s in raw if isinstance(s, dict) and s.get("signature")]
    out = []
    for s in sigs:
        tx = (_rpc("getTransaction", [s["signature"], {
            "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0,
        }]).get("result"))
        if not tx:
            continue
        meta = tx.get("meta") or {}
        if not any("BurnChecked" in (l or "") for l in (meta.get("logMessages") or [])):
            continue
        pre = {b["accountIndex"]: b for b in (meta.get("preTokenBalances") or [])}
        post = {b["accountIndex"]: b for b in (meta.get("postTokenBalances") or [])}
        delta = 0.0
        for idx in set(list(pre) + list(post)):
            b = post.get(idx) or pre.get(idx)
            if not b or b.get("mint") != MINT or b.get("owner") != addr:
                continue
            a0 = float((pre.get(idx) or {}).get("uiTokenAmount", {}).get("uiAmount") or 0)
            a1 = float((post.get(idx) or {}).get("uiTokenAmount", {}).get("uiAmount") or 0)
            delta += a1 - a0
        if delta < 0:
            out.append({"tx": s["signature"], "ts": s.get("blockTime") or 0, "tokens": -delta})
    return out


def classify_transfer_tx(tx_hash: str, wallet: str) -> dict:
    """Правда о транзакции по цепочке: сколько токенов, откуда и кто подписал.

    GMGN отдаёт НАКОПЛЕННУЮ сумму переводов (`history_transfer_in_amount`) и
    приклеивает её к последней транзакции перевода. Из-за этого алерт 12.11 01:30
    показывал «получил 1.194% саплая переводом», тогда как в той транзакции было
    1 000 токенов (пыль), а пакет 1.157% кошелёк КУПИЛ в пуле за 45.61 SOL
    двумя часами раньше. Поэтому сумму и сторону берём из pre/postTokenBalances
    самой транзакции, а своп (в accountKeys есть пара/пул) отличаем от перевода.
    """
    tx = _rpc("getTransaction", [tx_hash, {
        "encoding": "jsonParsed", "maxSupportedTransactionVersion": 0,
    }]).get("result")
    if not tx:
        return {}
    meta = tx.get("meta") or {}
    keys = [k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
    pre = {b["accountIndex"]: b for b in (meta.get("preTokenBalances") or [])}
    post = {b["accountIndex"]: b for b in (meta.get("postTokenBalances") or [])}
    delta = 0.0
    src = ""
    for idx in set(list(pre) + list(post)):
        b = post.get(idx) or pre.get(idx)
        if not b or b.get("mint") != MINT:
            continue
        acct = keys[idx] if idx < len(keys) else ""
        if b.get("owner") != wallet and acct != wallet:
            continue
        a0 = float((pre.get(idx) or {}).get("uiTokenAmount", {}).get("uiAmount") or 0)
        a1 = float((post.get(idx) or {}).get("uiTokenAmount", {}).get("uiAmount") or 0)
        delta += a1 - a0
    # Кто отдал токены: владелец аккаунта, у которого баланс упал.
    for idx in set(list(pre) + list(post)):
        b = post.get(idx) or pre.get(idx)
        if not b or b.get("mint") != MINT:
            continue
        acct = keys[idx] if idx < len(keys) else ""
        owner = b.get("owner") or ""
        if owner == wallet or acct == wallet:
            continue
        a0 = float((pre.get(idx) or {}).get("uiTokenAmount", {}).get("uiAmount") or 0)
        a1 = float((post.get(idx) or {}).get("uiTokenAmount", {}).get("uiAmount") or 0)
        if a1 - a0 < -1:
            src = owner or acct
            break
    signer = keys[0] if keys else ""
    return {
        "delta": delta,
        "src": src,
        "market": any(k in AMM_ACCOUNTS for k in keys),
        "signer": signer,
        "ts": tx.get("blockTime") or 0,
        "one_hand": bool(signer) and signer not in (wallet, src),
    }


def _classify_drop(snap: dict, owner: str, drop_tokens: float) -> str:
    """Просадка холда: 'burn' (печь проекта) или 'sell' (сброс в рынок).

    Приоритет: если это кошелёк-печь (BURN_WATCH_WALLETS) — просадка НЕ продажа.
    Основание: у 7YeCaAqh за всю историю GMGN продаж $0 (history_sold_income=0),
    а падение холда подтверждено сжиганиями (12.11: 11.58M одним tx). Остальные
    кошельки классифицируем по журналу сжиганий (≥50% просадки ушло в печь).
    """
    if owner in BURN_WATCH_WALLETS:
        return "burn"
    burned = burn_log_total(snap, owner)
    if burned < drop_tokens * BURN_ATTR_MIN_SHARE:
        fresh = _burn_log_add(snap, owner, scan_wallet_burns(owner))
        burned += sum(b.get("tokens") or 0 for b in fresh)
    return "burn" if burned >= drop_tokens * BURN_ATTR_MIN_SHARE else "sell"


def detect_burns(snap: dict, price_usd=None, wallets: list | None = None) -> list[str]:
    """Событие «🔥 СЖИГАНИЕ»: печь проекта уничтожила токены (дедуп по tx_hash).

    Сжигание — не продажа: это выкуп с рынка на creator fees и уничтожение
    (дефляционная поддержка). Считаем отдельным событием, чтобы не путать
    с выходом кита, и не чаще раза в BURN_RESCAN_H часов на кошелёк.
    """
    supply = snap.get("supply") or 0
    if not supply:
        return []
    supply_ui = supply / (10 ** TOKEN_DECIMALS)
    stamp = snap.setdefault("burn_scan_utc", {})
    now = time.time()
    out = []
    for addr in (wallets if wallets is not None else BURN_WATCH_WALLETS):
        last = stamp.get(addr)
        if last:
            try:
                from datetime import datetime, timezone
                if now - datetime.fromisoformat(last).timestamp() < BURN_RESCAN_H * 3600:
                    continue
            except Exception:
                pass
        fresh = _burn_log_add(snap, addr, scan_wallet_burns(addr))
        stamp[addr] = _now_iso()
        if not fresh:
            continue
        tokens = sum(b.get("tokens") or 0 for b in fresh)
        snap["burn_total_tokens"] = round((snap.get("burn_total_tokens") or 0) + tokens, 2)
        pct = tokens / supply_ui * 100
        if pct < BURN_ALERT_MIN_PCT:
            continue
        usd = f" ≈ ${tokens * float(price_usd):,.0f}" if price_usd else ""
        out.append(
            f"🔥 СЖИГАНИЕ (печь проекта): {tokens:,.0f} BURNIE{usd} — {pct:.2f}% саплая, {len(fresh)} tx\n"
            f"   кошелёк {addr[:10]}… (собирает creator fees → выкуп с рынка → в печь). "
            f"Это дефляция, НЕ сброс в рынок; всего сожжено за наблюдение "
            f"{snap['burn_total_tokens']:,.0f} токенов."
        )
    return out


def _burn_note(w: dict) -> str:
    """Пометка для кошелька-печи: его выкуп идёт в сжигание, а не в холд."""
    if (w.get("holding_owner") or w.get("address")) in BURN_WATCH_WALLETS:
        return ", кошелёк проекта (печь): выкуп уходит в сжигание, не в холд"
    return ""


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def measure_holdings(snap: dict) -> list[str]:
    """RPC-фолбэк: текущий холд по известному holding_owner каждого кошелька.

    Нужен потому, что gmgn-cli на VPS упирается в 429 и watch слепнет —
    без этой проверки отчёт продолжает показывать старый «накопление, продаж 0»
    даже после того, как кит слил позицию (кейс 01.11: топ-1 вышел, а отчёты
    ещё неделю писали «держит 6.87%, продаж 0»).

    Меряем только те записи, где holding_owner известен и проверен
    (GMGN-модель: address = кошелёк/плательщик, реальные токены лежат на
    отдельном торговом аккаунте). Иначе честно оставляем cur_pct пустым.
    """
    supply = snap.get("supply") or 0
    if not supply:
        return []
    out = []
    for w in snap.get("wallets", []):
        owner = w.get("holding_owner")
        if not owner:
            continue
        # Единый RPC-хелпер с ретраями (тот же, что у детектора сжиганий:
        # один путь для сети = один путь для тестов).
        res = _rpc("getTokenAccountsByOwner", [owner, {"mint": MINT}, {"encoding": "jsonParsed"}])
        if "result" not in res:
            continue
        tot = sum(
            int(i["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
            for i in (res.get("result", {}).get("value") or [])
        )
        cur_pct = round(tot / supply * 100, 3)
        base = w.get("pct") or 0
        w["cur_pct"] = cur_pct
        w["cur_tokens"] = round(tot / (10 ** TOKEN_DECIMALS), 2)
        base_tokens = w.get("base_tokens")
        if not base_tokens and base:
            # База ставилась под снапшотный supply. Проценты сравнивать нельзя:
            # supply с 25.09 уменьшился сжиганиями (12.11), поэтому базу один раз
            # переводим в токены и дальше решаем по токенам.
            base_tokens = round(base / 100 * BASE_SUPPLY_UI_AT_BASELINE, 2)
            w["base_tokens"] = base_tokens
        if not base_tokens:
            continue
        base_raw = base_tokens * (10 ** TOKEN_DECIMALS)
        if tot >= base_raw * 0.5:
            # Позиция в норме — снимаем флаг выхода, чтобы СЛЕДУЮЩИЙ реальный
            # выход снова дал алерт (кит вернулся и снова ушёл = новость).
            w.pop("exit_alerted", None)
            continue
        # Дедуп: один выход = один алерт. Без флага один и тот же факт
        # повторялся бы каждый тик (4×/день) и превращал отчёт в шум.
        # ВАЖНО: снапшотную базу w["pct"] НЕ трогаем — её читает
        # burnie_sentiment_tracker._accum_watch_note() для строки «ТОП-КОПАТЕЛЬ ВЫШЕЛ».
        if w.get("exit_alerted"):
            continue
        drop_tokens = (base_raw - tot) / (10 ** TOKEN_DECIMALS)
        kind = _classify_drop(snap, owner, drop_tokens)
        w["exit_alerted"] = {"at": _now_iso(), "from": base, "to": cur_pct, "kind": kind}
        if kind == "burn":
            out.append(
                f"🔥 ПЕЧЬ, А НЕ ВЫХОД: {w['address']}\n"
                f"   холд {base}% → {cur_pct}% саплая (holding account {owner[:8]}…), но "
                f"{burn_log_total(snap, owner):,.0f} токенов из просадки сожжены — "
                f"выкуп с рынка и уничтожение, а не сброс. Продажи тут нет."
            )
        else:
            out.append(
                f"🔴 КИТ ВЫШЕЛ: {w['address']}\n"
                f"   холд {base}% → {cur_pct}% саплая (holding account {owner[:8]}…). "
                f"Накопитель сократил/закрыл позицию — сценарий «тихое накопление» сломан."
            )
    return out


def main():
    snap = json.loads(SNAP.read_text())
    snap.setdefault("supply", 969651601137694)
    # Живая supply (12.11): снапшот 25.09 показывал 969.65M, реальная 937.81M —
    # сожжено 31.85M, и все доли саплая в отчётах были занижены на 3.4%.
    live_supply = fetch_live_supply()
    if live_supply:
        snap["supply"] = live_supply
        snap["supply_updated_utc"] = _now_iso()
    # База сравнения для дефляции: сентимент-отчёт считает по ней падение саплая,
    # не дублируя константу у себя (в снапшотном supply — raw-единицы).
    snap["supply_ui_at_baseline"] = round(BASE_SUPPLY_UI_AT_BASELINE, 6)
    by_addr = {}
    for h in fetch_traders():
        if str(h.get("addr_type")) == "2":
            continue
        b = h.get("buy_tx_count_cur") or 0
        bu = h.get("buy_volume_cur") or 0.0
        su = h.get("sell_volume_cur") or 0.0
        ba = h.get("buy_amount_cur") or 0.0
        cur = {"net": bu - su, "sells": h.get("sell_tx_count_cur") or 0,
               "bu": bu, "su": su, "ba": ba}
        # GMGN: address/account_address местами инвертированы по строкам —
        # индексируем ОБА ключа одним cur, чтобы резолв владельца всегда находил.
        for key in filter(None, (h.get("address"), h.get("account_address"))):
            by_addr[key] = cur

    def _avg_entry(cur):
        return cur["bu"] / cur["ba"] if cur["ba"] else None

    def _entry_note(cur, price):
        avg = _avg_entry(cur)
        if not avg or not price:
            return ""
        pnl = (float(price) / avg - 1) * 100
        return f", средняя входа ${avg:.5f} ({'+' if pnl >= 0 else ''}{pnl:.0f}% к рынку)"

    p = fetch_price()

    # Печь проекта: сжигания считаем ДО холдов, чтобы журнал сжиганий уже был
    # заполнен и просадка кошелька классифицировалась как «печь», а не «выход».
    burn_alerts = detect_burns(snap, price_usd=p["price"] if p else None)

    # RPC-фолбэк холдов (gmgn может быть в 429 — watch не должен слепнуть)
    hold_alerts = measure_holdings(snap)

    # Авто-пополнение новыми китами ДО основного цикла: зачисленные сразу попадают
    # в сверку этого же прогона (baseline = текущие значения, алерт на след. тик).
    # holders тянем ОДИН раз на оба блока — меньше обращений к gmgn (лимит по IP).
    holders = fetch_holders()
    new_alerts = enroll_new_wallets(snap, by_addr, holders)
    pkg_alerts = detect_package_transfers(snap, holders)

    lines = []
    for w in snap["wallets"]:
        cur = by_addr.get(w["address"])
        if cur is None:
            continue  # выпал из топ-100 — не алертим
        d_net = cur["net"] - w["net_buy_usd"]
        sold_share = cur["su"] / cur["bu"] if cur["bu"] else 0
        if d_net >= ALERT_NET_USD:
            lines.append(
                f"🟢 ДОКУПКА: {w['address']}\n"
                f"   докупил на ${d_net:,.0f} сверх снапшота; всего накопил ${cur['net']:,.0f} "
                f"({w.get('cur_pct') or w['pct']}% саплая сейчас)"
                f"{_burn_note(w)}{_entry_note(cur, price=p['price'] if p else None)}"
            )
        if sold_share > ALERT_SELL_PCT and w.get("sells", 0) < 3 and cur["sells"] >= 3:
            lines.append(
                f"🔴 НАЧАЛ ПРОДАВАТЬ: {w['address']}\n"
                f"   продал ${cur['su']:,.0f} — это {sold_share:.0%} того, что покупал. "
                f"Раньше продаж не было ({w.get('sells', 0)}). Сигнал выхода накопителя.{_entry_note(cur, price=p['price'] if p else None)}"
            )

    if by_addr:
        from datetime import datetime, timezone
        snap["last_gmgn_data_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    px = f"цена ${p['price']} (24ч {p['chg24h']}%), MC ${p['mc']:,.0f}, liq ${p['liq']:,.0f}" if p else "н/д"

    lines = new_alerts + pkg_alerts + burn_alerts + hold_alerts + lines
    if lines:
        print(f"BURNIE watch ({px})")
        print("\n".join(lines))
    # Обновляем снапшот значениями текущего прогона — след. алерт только
    # по НОВОЙ докупке с последнего тика (без повторов одного и того же).
    for w in snap["wallets"]:
        cur = by_addr.get(w["address"])
        if cur is not None:
            w["net_buy_usd"] = round(cur["net"])
            w["sells"] = cur["sells"]
    try:
        SNAP.write_text(json.dumps(snap, indent=1))
    except Exception as e:
        print(f"⚠️ snapshot update fail: {e}")
    # тишина = без отклонений; cron в no_agent-режиме молчит на пустом stdout


if __name__ == "__main__":
    main()
