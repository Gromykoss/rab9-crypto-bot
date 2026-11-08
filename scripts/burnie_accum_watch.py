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
    for h in holders:
        if h.get("addr_type") == 2 or h.get("exchange"):
            continue
        ti = h.get("token_transfer_in") or {}
        tx = ti.get("tx_hash") or ""
        amount = h.get("history_transfer_in_amount") or 0
        ts = ti.get("timestamp") or 0
        if not tx or not amount or ts < cutoff:
            continue
        events.append({
            "addr": h.get("address") or "",
            "pct": round(amount / supply_ui * 100, 3),
            "src": ti.get("address") or "",
            "ts": ts,
            "tx": tx,
            "bought": h.get("history_bought_cost") or 0,
            "tags": h.get("maker_token_tags") or [],
        })

    out = []
    for e in events:
        if e["pct"] < PACKAGE_MIN_PCT or e["tx"] in seen:
            continue
        seen[e["tx"]] = _now_iso()
        out.append(
            f"📦 ПЕРЕВОД ПАКЕТА: {e['addr']}\n"
            f"   получил {e['pct']}% саплая переводом от {e['src'][:8]}… — покупок на ${e['bought']:,.0f}"
            f"{', тег bundler' if 'bundler' in e['tags'] else ''}. Это распределение пакета, а не накопление."
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
        tot = None
        for attempt in range(4):
            try:
                body = json.dumps({
                    "jsonrpc": "2.0", "id": 1,
                    "method": "getTokenAccountsByOwner",
                    "params": [owner, {"mint": MINT}, {"encoding": "jsonParsed"}],
                }).encode()
                req = urllib.request.Request(
                    "https://api.mainnet-beta.solana.com", body,
                    {"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=25) as r:
                    res = json.load(r)
                if "result" in res:
                    tot = sum(
                        int(i["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
                        for i in (res["result"].get("value") or [])
                    )
                    break
            except Exception:
                pass
            time.sleep(8 * (attempt + 1))
        if tot is None:
            continue
        cur_pct = round(tot / supply * 100, 3)
        base = w.get("pct") or 0
        w["cur_pct"] = cur_pct
        if not base:
            continue
        if cur_pct >= base * 0.5:
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
        w["exit_alerted"] = {"at": _now_iso(), "from": base, "to": cur_pct}
        out.append(
            f"🔴 КИТ ВЫШЕЛ: {w['address']}\n"
            f"   холд {base}% → {cur_pct}% саплая (holding account {owner[:8]}…). "
            f"Накопитель сократил/закрыл позицию — сценарий «тихое накопление» сломан."
        )
    return out


def main():
    snap = json.loads(SNAP.read_text())
    snap.setdefault("supply", 969651601137694)
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
                f"({w['pct']}% саплая), покупок {w['buys']}{_entry_note(cur, price=p['price'] if p else None)}"
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

    lines = new_alerts + pkg_alerts + hold_alerts + lines
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
