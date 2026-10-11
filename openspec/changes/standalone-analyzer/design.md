# Design: standalone-analyzer (из замороженных спек v1.0 + ADR-0001)

## Карта выделения (что остаётся / что режется)

**Остаётся без изменений (пайплайн):** msf_analysis.py (build_compact_analysis_text),
cabal_detector, wallet_intel, loop_verifier, msf_dedupe, loop_memory, operators/,
dex/scanner/token_intel/watchlist/chart_analysis/onchain_check/meme_score/radar_x/radar_gh,
alerts.py (логика классификации — delivery меняется).

**Режется (Telegram-слой):** rab9_bot.py (entry), handlers.py, keyboards.py,
msf_listener.py, config.TELEGRAM_BOT_TOKEN/GROUP_ID (заменяются sink-конфигом).
Юниты: `rab9-crypto-hermes` → `rab9-analyzer` (новый файл), `msf-listener.service` — владельцем.

## Конфигурация (N1/N2 ревью рефриза 5d8f5703)

Endpoint health-check = GET `http://127.0.0.1:8089/health` (существующий msf_http.do_GET).
Стартовые значения analysis-filters — явно:

| Переменная (.env) | Старт | Источник |
|---|---|---|
| ANALYZER_T0_INTERVAL_MIN | 20 (методика: 15-30) | t0-cascade |
| ANALYZER_DIGEST_WINDOW_H | 4 | delivery-discipline |
| ANALYZER_DIGEST_THRESHOLD | 3 | delivery-discipline |
| ANALYZER_RATE_CAP_H | 15 | rate-cap |
| ANALYZER_KABAL_CAP_H | 5 | signal-state-routing |
| ANALYZER_QUEUE_MAX | 500 | bounded-очереди |
| ANALYZER_OUTCOME_DEAD_LIQ_USD | 5000 | outcome-loop («умер») |
| ANALYZER_OUTCOME_AFTER_H | 24 | outcome-loop |

## Ядро решения: Sink вместо application.bot

Точка боли: `msf_http.send_msf_pairresolve(application, address)` и
`alerts.alert_loop` — 5+ вызовов `application.bot.send_message`, вшитых в пайплайн.

Вводится класс `sink.py`:

```
class Sink:
    async def write(self, type: str, address: str, token: str, text: str) -> None
    # append в data/analyses_out/analyses.jsonl + отдельный файл
    # data/analyses_out/<ts>_<type>_<addr8>.md (chmod 600, fsync, tmp+rename)
    async def digest_timer(self) -> None   # фоновая корутина: окно 4ч, порог ≥3
```

Машиночитаемость (D-A1, ревью 031351b4): каждая jsonl-строка sink — валидный JSON
со схемой: `{id, ts, type, address, token, text, digest_meta?}`; для type=digest
обязательно `digest_meta = {window_start, window_end, threshold, counts: {verdict,
reject, alert, escalate}, entries: [{id, type, address, token, title}]}` — чтец
(RAB9-агент) парсит jsonl без знания внутренностей анализатора.
Асинхронность (D-A2): все fsync/tmp+rename операции sink — через
`asyncio.to_thread` (унификация с фичей 1, блокировка event loop запрещена).
Ротация jsonl (D-A3): analyses.jsonl > 5MB или > 20К строк → rename в
`analyses.<ts>.jsonl` + лог; пер-вердиктные .md — >500 файлов (как было).

`send_msf_pairresolve(sink, address)` — сигнатура меняется с Application на Sink;
каждый `application.bot.send_message(...)` → `await sink.write("verdict"/"alert"/...)`.
`start_msf_http_server(sink, loop)` — аналогично. ROUTING: `check_destination`
остаётся (ALLOW/BLOCK по конфигу чатов — заглушка-allowlist с теми же двумя id;
фактический получатель — агент, читающий sink).

## Новый entry: analyzer_main.py

```
main(): создать Sink → start_msf_http_server(sink, loop) → sink.digest_timer() фоном
        → outcome-loop (верификация исходов PASS/FLAG старше 24ч, раз в час) →
        анализ-очередь (analysis-filters: t0-каскад, rate cap)
```
Без python-telegram-bot. Конфиг `ANALYZER_*` в .env (окно/порог дайджеста, rate cap,
t0-интервал, пороги L1).

## /analyze (manual-analyze-endpoint)

В классе MsfSignalHandler: `do_POST` path `/analyze` — те же проверки секрета и
валидации, что `/msf-signal`; вызов того же прогона; HTTP-ответ = вердикт-текст +
статус; sink-запись `type=manual`. Только `127.0.0.1` binding (RAB9_HTTP_HOST
уже localhost — проверить и зафиксировать).

## Analysis-filters (v1.0) вшивание

- t0-каскад: очередь `data/t0_queue.jsonl` (персистентная), перепроверка по
  конфиг-интервалу; выжившие → очередь полного анализа.
- rate cap: семафор-счётчик/час, персистентная очередь `data/analysis_queue.jsonl`.
- концентрация топ-10 + social-weight: внутри build_compact_analysis_text
  (декс-обогащение уже там) — флаги в вердикт.
- outcome-loop: отдельная корутина, раз в час сканирует sink-вердикты старше 24ч →
  data/verdict_outcomes.jsonl.
  Замер исхода (D-A4, ревью 031351b4) — источник: DexScreener (ликвидность + цена,
  бесплатный, уже в стэке); точка отсчёта: цена и ликвидность на момент вердикта
  (фиксируются в sink-записи вердикта); критерии:
  `2x` — цена ≥ 2× отсчётной; `умер` — ликвидность < конфиг-порога (старт $5K) ИЛИ
  цена < 25% отсчётной; `флэт` — всё остальное. Замер неоднозначный (DexScreener
  отдал пусто по токену) = `умер` с пометкой confidence=low.
- digest: НЕ отправляет ничего — только пишет digest-запись в sink (доставку делает
  агент, читающий sink по крону своего профиля).

## Демонтаж (telegram-demolition)

1. git rm rab9_bot.py handlers.py keyboards.py msf_listener.py
2. config.py: удалить TELEGRAM_BOT_TOKEN/GROUP_ID константы (использования
   перепроверить grep'ом — pre-patch gate)
3. alerts.py: bot-путь (send_message) → sink.write("alert"); state-логика остаётся
4. .gitignore: +data/analyses_out/, data/t0_queue.jsonl, data/analysis_queue.jsonl
5. Юниты: старые не удаляю из /etc — вывод из эксплуатации владелец

## Юнит rab9-analyzer.service

System-scope, ExecStart=venv python analyzer_main.py, Restart=always,
WorkingDirectory, After=network-online.target. Ставит владелец;
переключение: остановить rab9-crypto-hermes и msf-listener → старт analyzer.

## Риски

- Рефакторинг send_msf_pairresolve — самая чувствительная точка (operators-гейты
  внутри); фикс: pre-patch grep каждого использования, тест на прогон после рефакторинга.
- Sink-рост: файлы мелкие (текст вердикта), ротация каталога при >500 файлов.
- Окно простоя при переключении юнитов: сигналы pumpportal уйдут в
  ingress_failed.jsonl (фича 1) и будут переотправлены — потери нет.

## Трассируемость требование → дизайн

| Требование | Реализация |
|---|---|
| standalone-process | analyzer_main.py без telegram-ext |
| sink-contract | sink.py + ротация |
| manual-analyze-endpoint | /analyze в MsfSignalHandler |
| digest-composition | sink.digest_timer (окно/порог конфиг) |
| telegram-demolition | раздел «Демонтаж» (тест import-guard — D-A5, см. tasks) |
| analysis-filters v1.0 | раздел «Analysis-filters вшивание» |

D-A5 (ревью 031351b4): spec-сценарий «прогон не импортирует Telegram-модули»
закрывается import-guard тестом:sys.modules-проверка после импорта analyzer_main —
'telegram' отсутствует в sys.modules и в исходниках импортируемых модулей
(grep-guard). Задача фиксируется в tasks.md T-демонтаж.
