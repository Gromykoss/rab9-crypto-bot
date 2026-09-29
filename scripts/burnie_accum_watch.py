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
import urllib.request
from pathlib import Path

MINT = "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump"
GMGN = "/home/hermes-workspace/.hermes/node/bin/gmgn-cli"
HERE = Path(__file__).resolve().parent
SNAP = HERE / "data" / "burnie_accum_watch.json"

ALERT_NET_USD = 1000      # докупка от $1K
ALERT_SELL_PCT = 0.25     # продал >25% своего net-объёма


def fetch_traders():
    out = subprocess.run(
        [GMGN, "token", "traders", "--chain", "sol", "--address", MINT],
        capture_output=True, text=True, timeout=90,
    )
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
        by_addr[h.get("account_address", "")] = {
            "net": bu - su, "sells": h.get("sell_tx_count_cur") or 0,
            "bu": bu, "su": su, "ba": ba,
        }

    def _avg_entry(cur):
        return cur["bu"] / cur["ba"] if cur["ba"] else None

    def _entry_note(cur, price):
        avg = _avg_entry(cur)
        if not avg or not price:
            return ""
        pnl = (float(price) / avg - 1) * 100
        return f", средняя входа ${avg:.5f} ({'+' if pnl >= 0 else ''}{pnl:.0f}% к рынку)"

    p = fetch_price()

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
