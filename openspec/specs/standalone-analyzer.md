# Spec: standalone-analyzer — v1.4 FROZEN (2026-11-19, T6 prose closure)

> v1.1 → v1.2 (ре-чек Grok FAIL → правки): (1) standalone-process переписан —
> полный прогон только в состоянии ANALYZED (v1.1-формулировка superseded);
> (2) дедуп-ключ пишется на входе в ANALYZED, не на мягком чеке; (3) SKIP =
> строка дайджеста (не «без записи»); (4) type=manual заменён флагом
> manual=true на type=verdict, вердикт-запись несёт outcome-бейзлайн.
> v1.2 → v1.3: GWT-биндинг — 14 сценариев в карточной форме с id, тесты
> `tests/test_standalone_analyzer_gwt.py`.
> v1.3 → v1.4: внешний сценарий доставки отмечен no-ci по
> delivery-reader-contract; анализатор по-прежнему не владеет offset. Текст шагов
> не менялся; поведение доставки не добавлялось.

Purpose: ядро анализа без Telegram-зависимостей: HTTP-ingress + пайплайн + sink для
доставки RAB9-агентом. Демонтаж Telegram-слоя и MSF-входа. ADR-0001.
Files: определяются design'ом (выделение из rab9_bot.py/msf_http.py/handlers.py, новый юнит).
Update Rule: изменение поведения = v-бамп + delta-карточка.
Neighbor Risks: operators/ (не байпасить), analysis-filters v1.0 (вызов фильтров), pumpportal_listener (фича 1 — контракт ingress).
Known Traps: процесс не имеет права слать в Telegram вообще; sink — единственный выход; демонтаж Telegram-модулей не должен задеть логику пайплайна.

### Requirement: standalone-process
Система SHALL выполнять полный аналитический прогон (DexScreener-enrichment → wallet_intel → DeepSeek → loop_verifier) ТОЛЬКО в состоянии ANALYZED единой машины состояний (см. signal-state-routing). Прямой «POST → немедленный полный AI» (формулировка v1.0) — superseded. Мягкие чеки (t0, L1-пороги) — лёгкие DexScreener-замеры без LLM. Юнит — `rab9-analyzer`, без python-telegram-bot и Telegram-вызовов.

Позиции норм на машине состояний:
| Норма | Где живёт |
|---|---|
| L1-пороги ликвидности/MC, honeypot/rugcheck-инфо | переход T0_PENDING → QUEUED (после перепроверки) |
| social-weight | приоритет внутри QUEUED |
| rate cap + KABAL-бакет | переход QUEUED → ANALYZED |
| dedup 24ч | запись ключа на входе в ANALYZED |
| DeepSeek → loop_verifier (PASS/FLAG/REJECT/HOLD) | состояние ANALYZED |
| outcome-loop | по sink-записям verdict старше 24ч |
### GIVEN валидный POST /msf-signal нового адреса — свежий мигрант НЕ анализируется сразу `standalone-analyzer.t0_no_llm_on_arrival`
- WHEN сигнал обработан
- THEN состояние T0_PENDING (мягкий чек, без LLM), DeepSeek не вызван
### GIVEN токен в QUEUED с выполненным rate cap — полный прогон на ANALYZED `standalone-analyzer.full_run_on_analyzed`
- WHEN очередь допускает анализ
- THEN полный прогон выполнен, ключ дедупа записан, вердикт в sink
### GIVEN любой прогон на машине состояний — сигнал обработан без Telegram `standalone-analyzer.no_telegram_calls`
- WHEN запись создана
- THEN вердикт записан в sink, ни один Telegram-вызов не выполнен

### Requirement: signal-state-routing
Система SHALL иметь ЕДИНУЮ машину состояний сигнала с явным роутингом (устраняет конфликт v1.0 ↔ analysis-filters, кит-блокер e9293d74):

`NEW → T0_PENDING (мягкий чек, лог) → [выжил] → QUEUED → ANALYZED → SINK` / `[умер] → SINK(reject)`

- t0-перепроверка — ВНУТРЕННИЙ таймер очереди t0_pending (персистентной); она НЕ является повторным ingress-контактом и НЕ нарушает дедуп 24ч.
- Дедуп 24ч: ключ SHALL записываться ТОЛЬКО на входе в ANALYZED (после прохождения rate cap, перед LLM-вызовом); мягкий чек и t0-каскад ключ НЕ пишут — защита от дублей каскада обеспечивается самой очередью t0_pending. Ручной /analyze SHALL записывать ключ (ручной повторный запрос того же адреса — явное намерение владельца, разрешён с пометкой manual).
- SAFETY_GATES (operators): подтверждённый scam (honeypot=fail / rugcheck=rugged) = hard DROP на ЛЮБОМ этапе и перекрывает все мягкие гейты; мягкие эвристики — только понижение приоритета / INCONCLUSIVE.
- KABAL-эскалация «вне очереди» SHALL иметь собственный потолок (конфиг, старт ≤5/час) и общий bounded-лимит очередей (конфиг, старт 500; переполнение → строка дайджеста).
### GIVEN мигрант на t=0 и дедуп-запись от первичного чека — конфликт разрешён `standalone-analyzer.cascade_conflict_resolved`
- WHEN наступает внутренняя перепроверка
- THEN перепроверка выполняется (дедуп не нарушен — это не ingress-контакт)
### GIVEN токен в очереди t0_pending и rugcheck=rugged — hard DROP перекрывает `standalone-analyzer.hard_drop_overrides`
- WHEN выполняется любой чек
- THEN немедленный DROP → sink(reject), очередь очищена
### GIVEN очередь анализа достигла конфиг-лимита — bounded очередь `standalone-analyzer.bounded_queue_overflow`
- WHEN приходит новый кандидат (включая KABAL)
- THEN кандидат → строка дайджеста, очереди не растут безгранично

### Requirement: verdict-taxonomy
Система SHALL использовать единую таксономию исходов: PASS (verifier прошёл, полный отчёт в дайджест) / FLAG (сомнение, полный отчёт с пометкой) / REJECT (мягкие гейты/фильтры, строка в дайджесте) / SKIP (дедуп/cooldown — СТРОКА в дайджесте, без полного отчёта) / DROP (подтверждённый scam, строка в дайджесте) / HOLD (неопределённость verifier, строка). Маппинг type sink: PASS,FLAG → `verdict`; REJECT,SKIP,DROP,HOLD → строка `reject`-категории в дайджесте (без отдельного вердикт-файла); KABAL/KOL → `alert`; свод окна → `digest`.

### Requirement: sink-outcome-baseline
Каждая sink-запись типа `verdict` SHALL содержать outcome-бейзлайн: `price_usd`, `liquidity_usd` на момент вердикта и флаг `manual` (true для ручного /analyze); отдельного type=`manual` нет. outcome-loop использует бейзлайн как точку отсчёта замера.
### GIVEN прогон завершился вердиктом PASS — бейзлайн в записи `standalone-analyzer.baseline_in_verdict_record`
- WHEN sink-запись создана
- THEN в jsonl присутствуют price_usd, liquidity_usd, manual

### Requirement: delivery-reader-contract
Система определяет доставку: RAB9-агент (Hermes-профиль) SHALL читать `data/analyses_out/analyses.jsonl` по крону (окно дайджеста), парсить по схеме D-A1, доставлять владельцу в чат и фиксировать факт доставки offset-файлом `data/analyses_out/delivery_offset.json` (последний прочитанный id); записи до offset = доставлены, после = очередь. Анализатор SHALL NOT реализовывать доставку сам.
#### Scenario: агент забрал дайджест
<!-- no-ci -->
Причина: delivery-reader-contract относит доставку и offset к внешнему RAB9-агенту.
GIVEN digest-запись в sink и delivery_offset позади неё
WHEN агент выполняет доставку
THEN offset обновлён на id digest-записи, повторной доставки нет

### Requirement: sink-contract
Система SHALL записывать каждый результат в `data/analyses_out/` (jsonl-лог + отдельный файл на запись) с полями `type` (`verdict`/`reject`/`alert`/`digest`/`manual`), `ts`, `token`, `address`, `text`; файлы SHALL переживать рестарт и подлежать ротации при переполнении каталога.
### GIVEN прогон завершился вердиктом PASS/FLAG — вердикт в sink `standalone-analyzer.verdict_written_to_sink`
- WHEN запись создана
- THEN jsonl-строка и файл вердикта существуют и читаемы после рестарта процесса
### GIVEN POST /analyze валидного адреса — ручной анализ `standalone-analyzer.manual_analyze_run`
- WHEN прогон завершён
- THEN запись type=verdict c manual=true в sink и вердикт-ответ на HTTP-запрос

### Requirement: manual-analyze-endpoint
Система SHALL принимать POST /analyze на том же ingress-сервере (авторизация X-RAB9-SECRET, контракт {chain,address}) и запускать прогон через ту же машину состояний (ручной запрос минует t0-каскад — явное намерение владельца); ответ SHALL содержать вердикт или статус обработки; sink-запись — type=`verdict` c флагом `manual=true`; доступ SHALL быть только с localhost.
### GIVEN POST /analyze с валидным адресом и секретом — ручной запрос `standalone-analyzer.manual_endpoint_authorized`
- WHEN прогон завершён
- THEN HTTP-ответ содержит вердикт, sink-запись type=verdict c manual=true, ключ дедупа записан
### GIVEN POST /analyze без корректного X-RAB9-SECRET — неавторизованный `standalone-analyzer.manual_endpoint_unauthorized`
- WHEN запрос обработан
- THEN 401, прогон не запускается

### Requirement: digest-composition
Система SHALL формировать digest-записи в sink по накопительному правилу analysis-filters (окно/порог конфиг) и включать в digest: полные отчёты выживших PASS/FLAG, строки reject/skip, alert фаз, escalate MC>5M; состав digest SHALL быть достаточен для доставки владельцу без чтения сырых файлов.
### GIVEN за окно накопились записи разных типов — дайджест собран `standalone-analyzer.digest_composition`
- WHEN окно дайджеста наступило (порог ≥3 выполнен)
- THEN digest-запись в sink содержит свод всех записей окна

### Requirement: telegram-demolition
Система SHALL удалить из репо Telegram-слой ядра (handlers, keyboards, bot-инициализация, msf_listener) и SHALL сохранить все модули пайплайна (cabal_detector, wallet_intel, loop_verifier, msf_analysis-логика, operators, msf_dedupe) рабочими; юниты `msf-listener.service` и `rab9-crypto-hermes.service` выводятся из эксплуатации владельцем.
### GIVEN Telegram-модули удалены — демонтаж не ломает пайплайн `standalone-analyzer.telegram_demolition_intact`
- WHEN полный прогон и suite тестов выполняются
- THEN все тесты зелёные, прогон не импортирует Telegram-модули
### GIVEN повторный адрес в 24ч — дедуп сохранён `standalone-analyzer.dedup_preserved_24h`
- WHEN сигнал поступает на ingress
- THEN анализ не запускается повторно (msf_dedupe работает как прежде)
