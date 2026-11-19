import importlib.util
from datetime import datetime, timezone
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "token_watch.py"
SPEC = importlib.util.spec_from_file_location("token_watch", MODULE_PATH)
token_watch = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(token_watch)


def dex_data(chg_24h=0.0, ratio=1.0):
    return {
        "ok": True,
        "price": 0.01,
        "mc": 1_000_000,
        "liq": 100_000,
        "vol24": 24_000,
        "vol1h": 0,
        "chg_1h": 0,
        "chg_24h": chg_24h,
        "buys": 10,
        "sells": 10,
        "ratio": ratio,
        "pairs": 1,
        "dexes": 1,
        "pool_url": "https://example.invalid/pool",
    }


def test_rpc_failure_on_first_tick_is_unknown_and_retried(monkeypatch):
    state = {"tokens": {}}
    calls = []
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data())
    monkeypatch.setattr(token_watch, "fetch_supply", lambda mint: 1_000_000)
    monkeypatch.setattr(token_watch, "fetch_authorities", lambda mint: calls.append(mint) or {})

    messages = token_watch.handle_token(token_watch.TOKENS[0], state)
    assert "Права минта: н/д | Права заморозки: н/д" in messages[0]
    assert "отозваны ✅" not in messages[0]
    token_state = state["tokens"][token_watch.TOKENS[0]["mint"]]
    assert "authorities" not in token_state

    token_watch.handle_token(token_watch.TOKENS[0], state)
    assert len(calls) == 2


def test_corrupt_state_is_backed_up_and_second_run_does_not_announce(monkeypatch, tmp_path, capsys):
    state_path = tmp_path / "token_watch_state.json"
    state_path.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(token_watch, "STATE_PATH", state_path)
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data())
    monkeypatch.setattr(token_watch, "fetch_supply", lambda mint: 1_000_000)
    monkeypatch.setattr(token_watch, "fetch_authorities", lambda mint: {
        "mint_authority": None, "freeze_authority": None, "decimals": 6
    })
    monkeypatch.setattr(token_watch, "maybe_digest", lambda cfg, state: [])

    assert token_watch.main() == 0
    first = capsys.readouterr()
    assert "ВЗЯТ ПОД НАБЛЮДЕНИЕ" in first.out
    assert "повреждённый снапшот сохранён" in first.err
    assert list(tmp_path.glob("token_watch_state.json.corrupt-*"))

    assert token_watch.main() == 0
    second = capsys.readouterr()
    assert "ВЗЯТ ПОД НАБЛЮДЕНИЕ" not in second.out
    assert second.out == ""


def test_unwritable_state_suppresses_messages(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(token_watch, "STATE_PATH", tmp_path / "token_watch_state.json")
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data())
    monkeypatch.setattr(token_watch, "fetch_supply", lambda mint: 1_000_000)
    monkeypatch.setattr(token_watch, "fetch_authorities", lambda mint: {})
    monkeypatch.setattr(token_watch, "maybe_digest", lambda cfg, state: [])
    monkeypatch.setattr(token_watch, "save_state", lambda state: False)

    assert token_watch.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "сообщения подавлены" in captured.err


def test_digest_verdict_uses_unchanged_fifteen_percent_threshold(monkeypatch):
    class DigestTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 11, 19, token_watch.DIGEST_UTC_HOUR, tzinfo=timezone.utc)

    monkeypatch.setattr(token_watch, "datetime", DigestTime)
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data(15.0, 1.0))
    state = {"tokens": {}}

    assert token_watch.DIGEST_TREND_PCT == 15.0
    assert "🟢 РАЗОГРЕВ" in token_watch.maybe_digest(token_watch.TOKENS[0], state)[0]

    state = {"tokens": {}}
    monkeypatch.setattr(token_watch, "fetch_dex", lambda mint: dex_data(-15.0, 1.0))
    assert "🔴 ОТКАТ" in token_watch.maybe_digest(token_watch.TOKENS[0], state)[0]


# ── 19.11.2026: битая USD-оценка пары (meteora CLAUDIA/MM) ───────────────────
# Живые цифры того инцидента: DexScreener отдал для пары CLAUDIA/MM priceUsd
# $61.15 и «ликвидность» $9.98 млн, потому что считал USD через курс MM (~$10),
# тогда как сам MM на своих пулах стоил $0.00104. По ликвидности эта запись
# «побеждала» настоящие SOL-пулы ($0.0064) и уводила цену/MC/ликвидность в отчёт.

CLAUDIA_MINT = "2j5SaS7xy776qCBpyPQbZjyQSAtKiFgrwjfErthnW2ZM"
MM_POOL = "62PhjxDxRhoTTQFdz7mbLsd655FFdR7yvu3qJXhjZxKP"
SOL_POOL = "Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr"


def _pair(dex_id, quote, price, liq, mc=None, vol24=0.0, buys=10, sells=10, addr=""):
    return {
        "dexId": dex_id,
        "pairAddress": addr,
        "url": "https://example.invalid/%s" % (addr or dex_id),
        "baseToken": {"address": CLAUDIA_MINT, "symbol": "CLAUDIA"},
        "quoteToken": {"symbol": quote, "address": "quote-%s" % quote},
        "priceUsd": str(price),
        "marketCap": mc,
        "liquidity": {"usd": liq},
        "volume": {"h24": vol24, "h1": 0.0},
        "priceChange": {"h1": 0.0, "h24": 0.0},
        "txns": {"h24": {"buys": buys, "sells": sells}},
    }


def poisoned_pairs_payload():
    return {"pairs": [
        _pair("pumpswap", "SOL", 0.006419, 363274.0, mc=6073749.0, vol24=971423.26,
              buys=100, sells=80, addr="Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr"),
        _pair("meteora", "MM", 61.15, 9981379.17, mc=57866649212.0, vol24=9318479.15,
              buys=54, sells=32, addr=MM_POOL),
        _pair("meteora", "SOL", 0.006335, 206623.0, mc=5995337.0, vol24=318264.89,
              addr="4XtavTkbwQpoTiQWswbyvBF3z4Cj5CjjfGGiDMZFk116"),
        _pair("meteora", "USDC", 0.006411, 7130.0, mc=6066892.0, vol24=3842.86,
              addr="ATe287quS14THv5SjdCbXvBhNaPHepoytjdhHCJJ8Syd"),
    ]}


def test_poisoned_exotic_pair_does_not_move_price_mc_or_liquidity(monkeypatch):
    monkeypatch.setattr(token_watch, "_get_json", lambda url, timeout=20: poisoned_pairs_payload())
    dex = token_watch.fetch_dex(CLAUDIA_MINT)

    assert dex["ok"] is True
    # цена — медиана чистых пар, а не $61.15 из битой записи
    assert 0.0063 < dex["price"] < 0.0065
    # ликвидность и объём считаются без экзотической пары
    assert dex["liq"] == 363274.0 + 206623.0 + 7130.0
    assert dex["vol24"] == 971423.26 + 318264.89 + 3842.86
    # MC согласован с показанной ценой, а не $58 млрд
    assert 5_500_000 < dex["mc"] < 7_000_000
    # битая пара вынесена вне расчёта и видна отдельно
    assert dex["clean_pairs"] == 3 and dex["exotic_pairs"] == 1
    assert dex["exotic_liq"] == 9981379.17
    assert dex["exotic_top"]["pair"] == MM_POOL
    assert dex["exotic_top"]["quote"] == "MM" and dex["exotic_top"]["role"] == "base"
    # глубочайшая достоверная пара — pumpswap CLAUDIA/SOL
    assert dex["pool_url"].endswith("Fe7bpDYCs74GqiCUF14HwgUMToPKV1d9mDYVX5BTohFr")
    assert dex["buys"] == 100 and dex["sells"] == 80


def test_pick_pair_ignores_bogus_price_even_when_liquidity_is_biggest():
    pairs = poisoned_pairs_payload()["pairs"]
    best = token_watch.pick_pair(pairs)
    assert best["pairAddress"] == SOL_POOL  # настоящий SOL-пул, не битая запись на $9.98 млн
    clean, exotic = token_watch.split_pairs(pairs)
    assert len(clean) == 3 and len(exotic) == 1


def test_poisoned_history_is_pruned_and_previous_tick_does_not_fire_alert(monkeypatch, capsys):
    """Отравленные тики (накопленные до фикса) не должны выдать «падение цены»
    на возврате к достоверной цифре; история чистится, база пересчитывается."""
    mint = CLAUDIA_MINT
    dex_clean = {
        "ok": True, "price": 0.006411, "mc": 6_066_892, "liq": 577_027.0,
        "vol24": 1_293_531.0, "vol1h": 0.0, "chg_1h": 0.0, "chg_24h": 0.0,
        "buys": 100, "sells": 80, "ratio": 1.25, "pairs": 4, "clean_pairs": 3,
        "exotic_pairs": 1, "exotic_liq": 9_981_379.17, "exotic_top": None,
        "dexes": 2, "pool_url": "https://example.invalid/sol",
    }
    snapshots = [
        {"ts": "2026-11-18T15:15:00+00:00", "price": 0.007443, "liq": 620_000.0,
         "vol24": 2436052.46, "pairs": 30},
        {"ts": "2026-11-19T13:00:00+00:00", "price": 59.58, "liq": 10445970.46,
         "vol24": 3835146.48, "pairs": 30},
        {"ts": "2026-11-19T15:00:00+00:00", "price": 60.55, "liq": 10557378.10,
         "vol24": 10203483.17, "pairs": 30},
    ]
    state = {"tokens": {mint: {
        "snapshots": snapshots,
        "last_alert": {},
        "metric_version": token_watch.METRIC_VERSION,
        "announced": "2026-11-18T06:43:56+05:00",
        "authorities": {"mint_authority": None, "freeze_authority": None, "decimals": 6},
        "last_price": 60.55,
        "last_liq": 10557378.10,
    }}}
    monkeypatch.setattr(token_watch, "fetch_dex", lambda m: dex_clean)
    monkeypatch.setattr(token_watch, "fetch_supply", lambda m: 946_213_969.889905)

    messages = token_watch.handle_token(token_watch.TOKENS[0], state)
    err = capsys.readouterr().err

    assert not any("ЦЕНЫ" in m for m in messages), messages
    assert not any("ЛИКВИДНОСТЬ УХОДИТ" in m for m in messages), messages
    assert "аномалия источника" in err and "убрано 2 тиков" in err
    token_state = state["tokens"][mint]
    assert [s["price"] for s in token_state["snapshots"]] == [0.007443, 0.006411]
    assert token_state["last_price"] == 0.006411


def test_legacy_state_without_metric_version_restarts_series(monkeypatch, capsys):
    """Состояние до фикса: ликвидность считалась по всем парам (включая битую),
    её нельзя сравнивать с новой — серия начинается заново, истории-алертов нет."""
    mint = CLAUDIA_MINT
    dex_clean = {
        "ok": True, "price": 0.006411, "mc": 6_066_892, "liq": 577_027.0,
        "vol24": 1_293_531.0, "vol1h": 0.0, "chg_1h": 0.0, "chg_24h": 0.0,
        "buys": 100, "sells": 80, "ratio": 1.25, "pairs": 4, "clean_pairs": 3,
        "exotic_pairs": 0, "exotic_liq": 0.0, "exotic_top": None,
        "dexes": 2, "pool_url": "https://example.invalid/sol",
    }
    state = {"tokens": {mint: {
        "snapshots": [
            {"ts": "2026-11-18T15:15:00+00:00", "price": 0.007443, "liq": 706952.28,
             "vol24": 2436052.46, "pairs": 30},
            {"ts": "2026-11-19T15:00:00+00:00", "price": 60.55, "liq": 10557378.10,
             "vol24": 10203483.17, "pairs": 30},
        ],
        "last_alert": {},
        "announced": "2026-11-18T06:43:56+05:00",
        "authorities": {"mint_authority": None, "freeze_authority": None, "decimals": 6},
        "last_price": 60.55, "last_liq": 10557378.10,
    }}}
    monkeypatch.setattr(token_watch, "fetch_dex", lambda m: dex_clean)
    monkeypatch.setattr(token_watch, "fetch_supply", lambda m: 946_213_969.889905)

    messages = token_watch.handle_token(token_watch.TOKENS[0], state)
    err = capsys.readouterr().err

    assert "методика расчёта" in err and "серия начата заново" in err
    assert not any("ЛИКВИДНОСТЬ УХОДИТ" in m or "ЦЕНЫ" in m for m in messages), messages
    token_state = state["tokens"][mint]
    assert [s["price"] for s in token_state["snapshots"]] == [0.006411]
    assert token_state["metric_version"] == token_watch.METRIC_VERSION
    # повторный тик уже на новой методике — серия не сбрасывается
    again = token_watch.handle_token(token_watch.TOKENS[0], state)
    assert "серия начата заново" not in capsys.readouterr().err
    assert len(state["tokens"][mint]["snapshots"]) == 2
    assert isinstance(again, list)


def test_exotic_pair_is_reported_once_per_pair(monkeypatch):
    mint = CLAUDIA_MINT
    top = {"pair": MM_POOL, "dex": "meteora", "quote": "MM", "role": "base",
           "price": 61.15, "liq": 9_981_379.17, "vol24": 9_318_479.15,
           "url": "https://example.invalid/mm"}
    dex = {
        "ok": True, "price": 0.006411, "mc": 6_066_892, "liq": 577_027.0,
        "vol24": 1_293_531.0, "vol1h": 0.0, "chg_1h": 0.0, "chg_24h": 0.0,
        "buys": 100, "sells": 80, "ratio": 1.25, "pairs": 4, "clean_pairs": 3,
        "exotic_pairs": 1, "exotic_liq": 9_981_379.17, "exotic_top": top,
        "dexes": 2, "pool_url": "https://example.invalid/sol",
    }
    state = {"tokens": {mint: {
        "snapshots": [], "last_alert": {},
        "announced": "2026-11-18T06:43:56+05:00",
        "authorities": {"mint_authority": None, "freeze_authority": None, "decimals": 6},
    }}}
    monkeypatch.setattr(token_watch, "fetch_dex", lambda m: dex)
    monkeypatch.setattr(token_watch, "fetch_supply", lambda m: 946_213_969.889905)

    first = [m for m in token_watch.handle_token(token_watch.TOKENS[0], state) if "ПАРА ВНЕ РАСЧЁТА" in m]
    assert len(first) == 1
    assert MM_POOL in first[0] and "$61.15" in first[0] and "расхождение ×" in first[0]

    second = [m for m in token_watch.handle_token(token_watch.TOKENS[0], state) if "ПАРА ВНЕ РАСЧЁТА" in m]
    assert second == []


def test_burnie_best_pair_skips_bogus_usd_record():
    """Тот же отбор в BURNIE-контуре: `_best_pair` читается из источника без импорта
    тяжёлых зависимостей скрипта."""
    import ast
    import typing

    src = (Path(__file__).parents[1] / "burnie_sentiment_tracker.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    consts = [n for n in tree.body
              if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") in
              ("VALID_QUOTE_SYMBOLS", "PAIR_PRICE_SPREAD_X")]
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_best_pair"]
    assert consts and funcs, "не найдены VALID_QUOTE_SYMBOLS/PAIR_PRICE_SPREAD_X/_best_pair"
    ns = {"Any": typing.Any}
    exec(compile(ast.Module(body=consts + funcs, type_ignores=[]), "<best_pair>", "exec"), ns)

    pairs = [
        {"dexId": "pumpswap", "pairAddress": "Fe7bpDYCs", "priceUsd": "0.0004619",
         "liquidity": {"usd": 121116.0},
         "baseToken": {"address": "CGEDT9QZ"}, "quoteToken": {"symbol": "SOL"}},
        {"dexId": "meteora", "pairAddress": MM_POOL, "priceUsd": "61.15",
         "liquidity": {"usd": 9981379.17},
         "baseToken": {"address": "CGEDT9QZ"}, "quoteToken": {"symbol": "MM"}},
        {"dexId": "meteora", "pairAddress": "4XtavTkb", "priceUsd": "0.0004623",
         "liquidity": {"usd": 20000.0},
         "baseToken": {"address": "CGEDT9QZ"}, "quoteToken": {"symbol": "USDC"}},
    ]
    assert ns["_best_pair"](pairs)["pairAddress"] == "Fe7bpDYCs"
    # если чистых пар нет вовсе — ведём себя как раньше (самая ликвидная из всех)
    exotic_only = [p for p in pairs if p["quoteToken"]["symbol"] == "MM"]
    assert ns["_best_pair"](exotic_only)["pairAddress"] == MM_POOL
