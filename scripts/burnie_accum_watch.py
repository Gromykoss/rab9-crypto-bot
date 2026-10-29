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
GMGN = "/home/hermes-workspace/.hermes/node/bin/gmgn-cli"
HERE = Path(__file__).resolve().parent
SNAP = HERE.parent / "data" / "burnie_accum_watch.json"

ALERT_NET_USD = 1000      # докупка от $1K
ALERT_SELL_PCT = 0.25     # продал >25% своего net-объёма


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


def enroll_new_wallets(snap: dict, by_addr: dict) -> list[str]:
    """Авто-пополнение watch: новый холдер ≥0.9% + net-buy ≥$10K → в снапшот с tag=new-<date>.

    Решение Сергея 29.10 («осень, горячее время, реагировать быстро»): новое
    накопление не должно месяцами жить вне радара. Возвращает строки-алерты.
    """
    added = []
    known = {w["address"] for w in snap["wallets"]}
    today = time.strftime("%Y%m%d")
    for h in fetch_holders():
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
        snap["wallets"].sort(key=lambda x: -x.get("pct", 0))
    return added


def main():
    snap = json.loads(SNAP.read_text())
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

    # Авто-пополнение новыми китами ДО основного цикла: зачисленные сразу попадают
    # в сверку этого же прогона (baseline = текущие значения, алерт на след. тик).
    new_alerts = enroll_new_wallets(snap, by_addr)

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

    px = f"цена ${p['price']} (24ч {p['chg24h']}%), MC ${p['mc']:,.0f}, liq ${p['liq']:,.0f}" if p else "н/д"

    lines = new_alerts + lines
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
