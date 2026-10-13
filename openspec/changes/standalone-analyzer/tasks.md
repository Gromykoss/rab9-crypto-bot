# Tasks: standalone-analyzer (спеки standalone-analyzer v1.0 + analysis-filters v1.0 FROZEN, design 037310f)

MUST NOT (из Gates + спек):
- Не логировать секреты; sink — единственный выход результатов.
- Не менять operators/, cabal_detector, wallet_intel, loop_verifier (только вызовы).
- Не менять существующие/чужие systemd-юниты; создаётся ТОЛЬКО rab9-analyzer.service.
- Не слать в Telegram из анализатора ни при каком пути.
- Спеки v1.0 заморожены: правки поведения = v-бамп + delta, не тихая правка.

## T1 — Sink [блокирует T2]
- [ ] sink.py: write(type,address,token,text) — jsonl-схема D-A1
      {id,ts,type,address,token,text,digest_meta?} + отдельный .md файл
      (chmod 600, tmp+rename, fsync — всё через asyncio.to_thread, D-A2).
- [ ] Ротация: analyses.jsonl >5MB/>20К строк → analyses.<ts>.jsonl (D-A3);
      каталог >500 .md → ротация.
- Критерий готовности: тесты — запись/чтение после «рестарта», ротация по размеру,
  jsonl-строка валидна по схеме D-A1. GWT «вердикт в sink».

## T2 — Рефакторинг ядра на Sink [блокирует T3]
> N1 (ревью 7f997f9a): самая рискованная задача — промежуточные коммиты поэтапно
> внутри окна, pre-patch grep воспроизводится на каждом шаге.
> N2 (ревью 7f997f9a): outcome-loop ходит в DexScreener — учитывать rate-лимиты
> бесплатного тира (кэш ответов, паузы между замерами; часовой цикл это допускает).
- [ ] Pre-patch grep: все application.bot.send_message в msf_http.py/handlers-путях
      пайплайна — каждая точка показана и заменена на sink.write с корректным type.
- [ ] Сигнатура send_msf_pairresolve(application,address) → (sink,address);
      start_msf_http_server(sink,loop); check_destination остаётся (allowlist).
- [ ] alerts.py: bot-путь → sink.write("alert"); state-логика без изменений.
- Критерий готовности: интеграционный тест — POST /msf-signal валидного адреса →
  вердикт в sink, ноль Telegram-вызовов; grep send_message в изменённых файлах = 0.
  GWT «сигнал обработан без Telegram».

## T3 — analyzer_main + digest + outcome [после T2, параллельно T4]
> N1 (ре-чек v1.2 9795826c): негатив-тест «каскад не пишет ключ дедупа» — обязателен.
> N2 (ре-чек v1.2): rate-cap/KABAL — на ПЕРЕХОДЕ QUEUED→ANALYZED, не на входе в QUEUED.
> Машина состояний канон (v1.2): полный прогон только в ANALYZED; дедуп-ключ на
> входе в ANALYZED; SKIP=строка дайджеста; type=manual упразднён (manual=true флаг);
> verdict-запись несёт outcome-бейзлайн (price_usd, liquidity_usd, manual).
- [ ] analyzer_main.py: Sink → start_msf_http_server → digest_timer (окно/порог
      ANALYZER_* из .env) → outcome-loop (раз в час).
- [ ] digest_timer: накопление по окну, порог ≥3, digest-запись с digest_meta
      (схема D-A1); пустое окно — тишина.
- [ ] outcome-loop: замер исхода по D-A4 (DexScreener отсчёт ИЗ sink-записи вердикта
      — price_usd/liquidity_usd бейзлайн v1.2; 2x / умер [liq<конфиг или цена<25%] /
      флэт; пусто = умер confidence=low) → data/verdict_outcomes.jsonl.
- [ ] НЕГАТИВ-ТЕСТ N1: полный каскад мигранта (T0→перепроверка) не создаёт записи
      в дедупе (msf_dedupe state не изменён каскадом); ключ появляется только на ANALYZED.
- Критерий готовности: тесты digest-сборки (порог, пустое окно) и outcome-замера
  на моках DexScreener (2x/умер/флэт/confidence=low). GWT «дайджест собран»,
  «исход зафиксирован», «пустое окно».

## T4 — /analyze [после T2, параллельно T3]
- [ ] do_POST path /analyze: секрет (401), валидация адреса, тот же прогон,
      sink type=manual, вердикт в HTTP-ответе.
- Критерий готовности: тесты — валидный адрес → 200+вердикт+sink manual;
      без секрета → 401. GWT «ручной запрос», «неавторизованный».

## T5 — Analysis-filters вшивание [после T3]
- [ ] t0-каскад: очередь data/t0_queue.jsonl (персистентная, переживает рестарт),
      перепроверка по ANALYZER_T0_INTERVAL_MIN; выжившие (L1-пороги на переходе
      T0_PENDING→QUEUED) → очередь анализа.
- [ ] rate cap + KABAL-бакет: НА ПЕРЕХОДЕ QUEUED→ANALYZED (N2, не на входе в
      QUEUED); персистентная очередь data/analysis_queue.jsonl; dedup-ключ пишется
      на входе в ANALYZED (v1.2).
- [ ] social-weight: приоритет по живому X-аккаунту (из декс-обогащения).
- Критерий готовности: тесты каскада (выжил/умер/рестарт очереди — GWT), rate cap
  (переполнение не теряется, переживает рестарт), digest-строка умершего токена.
  GWT «токен выжил/умер/рестарт процесса», «переполнение очереди».

## T6 — Демонтаж + import-guard [после T5]
- [ ] git rm rab9_bot.py handlers.py keyboards.py msf_listener.py; config.py без
      TELEGRAM_* (pre-patch grep каждого использования).
- [ ] Import-guard тест: import analyzer_main → 'telegram' отсутствует в
      sys.modules; grep-guard по исходникам импортируемых модулей (D-A5).
- [ ] .gitignore: +data/analyses_out/, data/t0_queue.jsonl, data/analysis_queue.jsonl.
- Критерий готовности: полный suite зелёный, import-guard тест проходит,
  дедуп работает (тест повторного адреса). GWT «демонтаж не ломает пайплайн»,
  «дедуп сохранён».

## T7 — Юнит + переключение (ручной gate владельца)
- [ ] rab9-analyzer.service в репо (System-scope, Restart=always).
- [ ] ВЛАДЕЛЕЦ: остановить rab9-crypto-hermes и msf-listener; установить/запустить
      rab9-analyzer; is-active = active; delivery-reader (RAB9-профиль) — проверить
      существование и парсинг sink-схемы D-A1 (needs_validation).
- Критерий готовности: owner-подтверждение active + первый digest доставлен агентом.
