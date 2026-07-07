#!/usr/bin/env python3
"""RAB9 wallet analysis report generator."""
import sqlite3
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import RAB9_DB_PATH

conn = sqlite3.connect(RAB9_DB_PATH)
conn.row_factory = sqlite3.Row

lines = []

def p(text=""):
    lines.append(text)

p("=" * 56)
p("   RAB9 CRYPTO INTEL — WALLET ANALYSIS REPORT")
p("=" * 56)
p(f"   Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
p()

# 1. Overiew
total_makers = conn.execute(
    'SELECT COUNT(DISTINCT maker) as cnt FROM pair_trades WHERE maker != ""'
).fetchone()["cnt"]
total_pairs = conn.execute("SELECT COUNT(*) as cnt FROM pairs").fetchone()["cnt"]
total_trades = conn.execute("SELECT COUNT(*) as cnt FROM pair_trades").fetchone()["cnt"]
stats = conn.execute(
    "SELECT MIN(trade_unix) as oldest, MAX(trade_unix) as newest FROM pair_trades"
).fetchone()

p("OVERVIEW")
p(f"  Wallets tracked:  {total_makers:>6,}")
p(f"  Tokens (pairs):   {total_pairs:>6}")
p(f"  Total trades:     {total_trades:>6,}")
if stats["oldest"]:
    oldest = datetime.utcfromtimestamp(stats["oldest"]).strftime("%Y-%m-%d")
    newest = datetime.utcfromtimestamp(stats["newest"]).strftime("%Y-%m-%d")
    p(f"  Trade period:     {oldest}  →  {newest}")
p()

# 2. Top wallets by volume
p("━" * 55)
p("  TOP 20 WALLETS BY TRADE VOLUME")
p("━" * 55)
top = conn.execute("""
    SELECT maker, COUNT(*) as trades,
           SUM(CASE WHEN side='BUY' THEN 1 ELSE 0 END) as buys,
           SUM(CASE WHEN side='SELL' THEN 1 ELSE 0 END) as sells,
           COUNT(DISTINCT pair_address) as tokens_traded
    FROM pair_trades WHERE maker != ''
    GROUP BY maker ORDER BY trades DESC LIMIT 20
""").fetchall()

p(f"  {'#':>2} {'Wallet':<25} {'Trades':>7} {'Buy%':>5} {'Tokens':>7}")
p(f"  {'-'*2} {'-'*25} {'-'*7} {'-'*5} {'-'*7}")
for i, r in enumerate(top, 1):
    ratio = r["buys"] / max(r["buys"] + r["sells"], 1)
    addr_s = r["maker"][:8] + "..." + r["maker"][-6:]
    p(f"  {i:2d} {addr_s:<25} {r['trades']:>7d} {ratio:>4.0%} {r['tokens_traded']:>7d}")
p()

# 3. Top tokens
p("━" * 55)
p("  TOP TOKENS BY MARKET CAP")
p("━" * 55)
pairs = conn.execute("""
    SELECT pair_address, token_symbol, market_cap_usd, liquidity_usd, trade_count
    FROM pairs WHERE market_cap_usd IS NOT NULL
    ORDER BY market_cap_usd DESC LIMIT 10
""").fetchall()

p(f"  {'#':>2} {'Token':<14} {'Market Cap':>14} {'Liquidity':>12} {'Trades':>8}")
p(f"  {'-'*2} {'-'*14} {'-'*14} {'-'*12} {'-'*8}")
for i, r in enumerate(pairs, 1):
    sym = (r["token_symbol"] or "?")[:12]
    mc = r["market_cap_usd"] or 0
    liq = r["liquidity_usd"] or 0
    tc = r["trade_count"] or 0
    p(f"  {i:2d} {sym:<14} ${mc:>11,.0f} ${liq:>9,.0f} {tc:>8d}")
p()

# 4. Trade side distribution
p("━" * 55)
p("  TRADE DISTRIBUTION")
p("━" * 55)
bs = conn.execute("SELECT side, COUNT(*) as cnt FROM pair_trades GROUP BY side").fetchall()
total_side = sum(r["cnt"] for r in bs)
for r in bs:
    s = r["side"] or "UNKNOWN"
    p(f"  {s:<10s}: {r['cnt']:>7d} ({r['cnt']/total_side*100:5.1f}%)")
p()

# 5. Kabal library
kabal_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "kabal_library.json")
if os.path.exists(kabal_path):
    with open(kabal_path) as f:
        kabal = json.load(f)
    p("━" * 55)
    p(f"  KABAL LIBRARY — Bayesian Wallet Intelligence")
    p(f"  Total scored wallets: {len(kabal)}")
    p("━" * 55)

    kabals = {
        k: v for k, v in kabal.items() if v.get("classification") == "kabal"
    }
    suspicious = {
        k: v for k, v in kabal.items() if v.get("classification") == "suspicious"
    }
    infra = {
        k: v for k, v in kabal.items() if v.get("classification") == "infrastructure"
    }

    p(f"  Kabal (P≥80%):           {len(kabals):>3d}")
    p(f"  Suspicious (P=45-80%):   {len(suspicious):>3d}")
    p(f"  Infrastructure (MEV):    {len(infra):>3d}")
    p()

    if kabals:
        p("━" * 55)
        p("  🎯  KABAL WALLETS  (timing-verified, P ≥ 80%)")
        p("━" * 55)
        sorted_k = sorted(kabals.items(), key=lambda x: x[1]["probability"], reverse=True)
        for addr, info in sorted_k:
            addr_s = addr[:8] + "..." + addr[-6:]
            exit_flag = f" ⚠️exit<6h×{info['exit_6h']}" if info.get("exit_6h", 0) > 0 else ""
            p(f"  {addr_s:<25} P={info['probability']:.0%} | "
              f"W={info['winner_tokens']}W | "
              f"trades={info['winner_trades']} | "
              f"T1×{info['tier1_count']} T2×{info['tier2_count']}{exit_flag}")
        p()

    if suspicious:
        p("━" * 55)
        p("  ⚠️  TOP 15 SUSPICIOUS WALLETS  (P = 45-80%)")
        p("━" * 55)
        sorted_s = sorted(suspicious.items(), key=lambda x: x[1]["probability"], reverse=True)
        for addr, info in sorted_s[:15]:
            addr_s = addr[:8] + "..." + addr[-6:]
            p(f"  {addr_s:<25} P={info['probability']:.0%} | "
              f"W={info['winner_tokens']}W | "
              f"trades={info['winner_trades']} | "
              f"T1×{info['tier1_count']} T2×{info['tier2_count']} | "
              f"cov={info['coverage']:.0%}")
        p()

    if infra:
        p("━" * 55)
        p(f"  🤖  INFRASTRUCTURE WALLETS  (MEV/Bots) — {len(infra)} total")
        p("━" * 55)
        sorted_i = sorted(infra.items(), key=lambda x: x[1]["probability"], reverse=True)
        for addr, info in sorted_i[:10]:
            addr_s = addr[:8] + "..." + addr[-6:]
            p(f"  {addr_s:<25} P={info['probability']:.0%} | "
              f"{info['all_tokens']} tokens | "
              f"trades={info['winner_trades']} | "
              f"cov={info['coverage']:.0%} | "
              f"concentration={info['concentration']:.0%}")
        p()

# 6. System info
p("━" * 55)
p("  SYSTEM STATUS")
p("━" * 55)
p("  MSF HTTP API:       :8089 (active)")
p("  Telegram Bot API:   :8080 (active)")
p("  Telegram Webhook:   :8081")
p("  Database:           rab9_trades.db ({:.1f} MB)".format(
    os.path.getsize(RAB9_DB_PATH) / (1024 * 1024)
))

conn.close()
p()
p("=" * 56)
p("   END OF REPORT")
p("=" * 56)

print("\n".join(lines))
