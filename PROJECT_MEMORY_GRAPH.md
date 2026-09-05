# PROJECT_MEMORY_GRAPH.md — единый вход сессии rab9

> Назначение: компактная контрактная карта проекта; стартовая точка после обязательного `context_loader.py`.
> Обновляется: при изменении доменов / инвариантов / маршрутов чтения (Spec Drift Gate).

## Purpose
RAB9 — Python-бот крипто-сигналов MSF: Telegram-мемы -> адрес токена -> DexScreener enrichment -> cabal/wallet safety -> DeepSeek/Grok анализ -> loop_verifier -> Telegram-сигнал в allowlist-чаты.

## Boot Rule
1. Сначала обязательно выполнить `python3 ~/.hermes/scripts/context_loader.py rab9 <trigger> [--max-tokens 500]` (AGENTS rule 0).
2. На старте читать только этот граф + `AGENTS.md` Critical Gates; большие доки открывать по маршруту из Change Routing.
3. Доменные детали читать точечно: `INDEX.md` для карты файлов, `PROJECT.md` для назначения, `CHRONOLOGY.md` только последние 3 записи или нужный инцидент.

## Global Invariants (нарушение = стоп + эскалация)
- **Русский язык обязателен** для reasoning, ответов и обсуждений.
- **Buzz 5 шагов:** отвечать только при прямом адресате, читать последние сообщения, не лезть в чужую зону, проверять претензии, при сомнении писать «нужно проверить».
- **Возврат из Buzz в Telegram обязателен:** Buzz только временное уточнение, итог Сергею — в исходной Telegram-группе.
- **Destination lock:** автосигналы только в Cryptanalyst `-1004425561477` и Песочницу `-1003979753733`; вне allowlist = BLOCK.
- **No production without approval:** мутации конфига/деплой/systemd только через approval; systemd unit не менять без команды.
- **REJECT default:** MoA оба agree -> PASS, расходятся -> FLAG, иначе REJECT; loop_verifier fail-closed.
- **Safety gates не байпасить:** cabal_detector, wallet_intel, loop_verifier, operators обязательны.
- **Секреты не раскрывать:** `msf_token.txt`, `.env`, `TELEGRAM_BOT_TOKEN`, DexScreener/DeepSeek/xAI/API-ключи не логировать и не коммитить.
- **X/Twitter write запрещён:** Rab9 допускает только read-only X-радар; постинг/лайки/ответы не зона проекта.
- **Раздельно с Алиханом:** директории, venv, боты, БД и ключи не смешивать.

## Domain Map

| Домен | Источник правды | Код / данные | Тесты |
|-------|-----------------|--------------|-------|
| session-contract | `AGENTS.md`, `PROJECT_MEMORY_GRAPH.md` | `INDEX.md`, `PROJECT.md`, `CHRONOLOGY.md` | - |
| telegram-ingest | `AGENTS.md`, `PROJECT.md` | `msf_listener.py`, `msf_http.py`, `rab9_bot.py`, `handlers.py` | `tests` |
| signal-analysis | `PROJECT.md`, `CHRONOLOGY.md` | `msf_analysis.py`, `dex.py`, `chart_analysis.py`, `onchain_check.py`, `meme_score.py` | `tests` |
| safety-gates | `AGENTS.md` Enforced-законы | `cabal_detector.py`, `wallet_intel.py`, `honeypot_check.py`, `rugcheck_client.py`, `operators`, `msf_dedupe.py` | `tests` |
| llm-verification | `AGENTS.md`, `PROJECT.md` | `loop_verifier.py`, `loop_stops.py`, `radar_x.py`, `radar_gh.py` | `tests` |
| delivery-alerts | `AGENTS.md` Destination lock | `alerts.py`, `alert_state.json`, `handlers.py`, `msf_http.py` | `tests` |
| burnie-monitoring | `CHRONOLOGY.md`, `PROJECT.md` | `burnie_sentiment_tracker.py`, `burnie_price_watch.py`, `kpi_report.py` | `tests` |
| persistence-config | `AGENTS.md`, `INDEX.md` | `data`, `data/rab9_trades.db`, `trade_db.py`, `config.py`, `.env.example`, `requirements.txt` | `tests` |

## Change Routing (задача про X -> читать Y)
- **Правила сессии / контрактный индекс** -> `PROJECT_MEMORY_GRAPH.md` + `AGENTS.md` Critical Gates.
- **Telegram ingest / HTTP webhook / handlers** -> `msf_listener.py` + `msf_http.py` + `handlers.py` + последние 3 записи `CHRONOLOGY.md`.
- **DexScreener / анализ токена / chart/onchain/meme-score** -> `msf_analysis.py` + `dex.py` + нужный enrichment-модуль.
- **Cabal / wallet / honeypot / rugcheck / operators** -> `AGENTS.md` Enforced-законы + соответствующий модуль safety-gates.
- **DeepSeek/Grok/MoA/loop verifier/X radar** -> `loop_verifier.py` + `radar_x.py` + `radar_gh.py` + `PROJECT.md`.
- **Telegram доставка / allowlist / alerts** -> `alerts.py` + `msf_http.py` + `handlers.py` + Destination lock в `AGENTS.md`.
- **BURNIE cron / sentiment / price-watch / KPI** -> `burnie_sentiment_tracker.py` + `burnie_price_watch.py` + `kpi_report.py` + свежая `CHRONOLOGY.md`.
- **БД / конфиг / зависимости** -> `trade_db.py` + `config.py` + `data/rab9_trades.db` + `requirements.txt` без чтения секретов из `.env`.

## Spec Drift Gate
Изменил домен / инвариант / маршрут чтения -> обнови `PROJECT_MEMORY_GRAPH.md` + `CHRONOLOGY.md`. Если изменение не затрагивает контрактный индекс -> записать в `CHRONOLOGY.md`: `Contract index update: not needed`.
