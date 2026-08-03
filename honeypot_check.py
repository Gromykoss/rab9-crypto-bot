"""Живой honeypot-тест через Jupiter Lite API (keyless, бесплатно).

Паттерн из Golemozan/rugradar (ADOPT, собственная реализация, без копирования кода).
Двусторонний quote: sell (token→SOL) + buy (SOL→token). 2 HTTP-вызова на токен.

Вердикты:
  pass    — sell-роут есть (можно выйти)
  fail    — buy есть, sell нет → honeypot
  unknown — оба нет / ошибка API / нет данных

Usage:
    from honeypot_check import check_honeypot
    r = check_honeypot("CGEDT9...")
    # r["status"] in ("pass", "fail", "unknown")

CLI: python3 honeypot_check.py <mint>
"""

from __future__ import annotations

import json
import sys
from typing import Any

import requests

# lite-api.jup.ag — keyless, подтверждён 02.08.2026 (quote-api.jup.ag DNS недоступен)
JUP_QUOTE_URL = "https://lite-api.jup.ag/swap/v1/quote"
SOL_MINT = "So11111111111111111111111111111111111111112"
# 5% slippage — как в rugradar-паттерне
SLIPPAGE_BPS = 500
TIMEOUT = 8
# Минимальный notional в raw units (для 6 decimals = 0.001 token).
# amount=1 часто даёт NO_ROUTES_FOUND из-за размера; 1000+ стабильнее.
SELL_AMOUNTS = (100_000, 1_000_000, 10_000_000)  # progressive fallback
BUY_AMOUNT_LAMPORTS = 10_000_000  # 0.01 SOL


def _quote_ok(input_mint: str, output_mint: str, amount: int) -> tuple[bool | None, str]:
    """Один quote-запрос к Jupiter Lite.

    Returns:
        (True, detail)  — роут найден
        (False, detail) — роута нет / token not tradable
        (None, detail)  — сетевая/парс ошибка (unknown)
    """
    try:
        r = requests.get(
            JUP_QUOTE_URL,
            params={
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
                "slippageBps": str(SLIPPAGE_BPS),
            },
            timeout=TIMEOUT,
        )
    except Exception as e:
        return None, f"network: {type(e).__name__}"

    # 200 + outAmount/routePlan = pass
    if r.status_code == 200:
        try:
            data = r.json()
        except Exception:
            return None, "bad_json"
        out = data.get("outAmount")
        # outAmount > 0 = tradable route (routePlan обычно non-empty)
        if out is not None and str(out) not in ("", "0"):
            return True, f"out={out}"
        err = data.get("errorCode") or data.get("error") or "no_out"
        return False, str(err)[:80]

    # 4xx: TOKEN_NOT_TRADABLE / NO_ROUTES_FOUND = нет роута
    try:
        data = r.json()
        code = str(data.get("errorCode") or data.get("error") or f"HTTP{r.status_code}")
    except Exception:
        code = f"HTTP{r.status_code}"
    if r.status_code in (400, 404):
        return False, code[:80]
    return None, code[:80]


def _sell_route(mint: str) -> tuple[bool | None, str, int | None]:
    """Sell quote: token → SOL. Пробует несколько amount (progressive)."""
    last_detail = "no_attempt"
    last_ok: bool | None = False
    for amt in SELL_AMOUNTS:
        ok, detail = _quote_ok(mint, SOL_MINT, amt)
        last_detail = detail
        last_ok = ok
        if ok is True:
            return True, detail, amt
        # unknown (сеть) — не крутить дальше
        if ok is None:
            return None, detail, amt
        # False: если amount слишком мал — пробуем больше; TOKEN_NOT_TRADABLE — стоп
        if "NOT_TRADABLE" in detail.upper() or "not tradable" in detail.lower():
            return False, detail, amt
    return last_ok, last_detail, SELL_AMOUNTS[-1]


def _buy_route(mint: str) -> tuple[bool | None, str]:
    """Buy quote: SOL → token (0.01 SOL)."""
    return _quote_ok(SOL_MINT, mint, BUY_AMOUNT_LAMPORTS)


def check_honeypot(mint: str) -> dict[str, Any]:
    """Двусторонний живой honeypot-тест.

    Returns dict:
        ok: bool (API-вызовы выполнены без фатала)
        status: "pass" | "fail" | "unknown"
        sell_ok: bool | None
        buy_ok: bool | None
        sell_detail / buy_detail: str
        source: "jupiter-lite"
    """
    mint = (mint or "").strip()
    if not mint or len(mint) < 32:
        return {
            "ok": False,
            "status": "unknown",
            "sell_ok": None,
            "buy_ok": None,
            "sell_detail": "bad_mint",
            "buy_detail": "",
            "source": "jupiter-lite",
            "error": "invalid_mint",
        }

    sell_ok, sell_detail, sell_amt = _sell_route(mint)
    buy_ok, buy_detail = _buy_route(mint)

    # Вердикт
    if sell_ok is True:
        status = "pass"
    elif sell_ok is False and buy_ok is True:
        status = "fail"  # классический honeypot: купить можно, продать нельзя
    elif sell_ok is False and buy_ok is False:
        status = "unknown"  # оба нет — мёртвый/не торгуется, не обязательно honeypot
    elif sell_ok is False and buy_ok is None:
        status = "unknown"
    else:
        # sell_ok is None (сеть) → unknown
        status = "unknown"

    return {
        "ok": True,
        "status": status,
        "sell_ok": sell_ok,
        "buy_ok": buy_ok,
        "sell_detail": sell_detail,
        "buy_detail": buy_detail,
        "sell_amount": sell_amt,
        "source": "jupiter-lite",
        "is_honeypot": status == "fail",
    }


def format_for_grok(result: dict[str, Any]) -> str:
    """Компактная строка для Grok-контекста."""
    if not result.get("ok") and result.get("error"):
        return f"Honeypot: unknown ({result.get('error')})"
    st = result.get("status", "unknown")
    emoji = {"pass": "✓", "fail": "🔴", "unknown": "⚪"}.get(st, "?")
    sell = result.get("sell_ok")
    buy = result.get("buy_ok")
    return (
        f"Honeypot (Jupiter live): {emoji} {st} "
        f"(sell={'yes' if sell else ('no' if sell is False else '?')}, "
        f"buy={'yes' if buy else ('no' if buy is False else '?')})"
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"ok": False, "error": "Usage: honeypot_check.py <mint>"}))
        sys.exit(1)
    result = check_honeypot(sys.argv[1])
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result.get("status") != "fail" else 2)
