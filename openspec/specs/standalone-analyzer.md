# Spec: standalone-analyzer — v1.1 FROZEN (2026-10-11, гармонизация по кит-прогону e9293d74)

Purpose: ядро анализа без Telegram-зависимостей: HTTP-ingress + пайплайн + sink для
доставки RAB9-агентом. Демонтаж Telegram-слоя и MSF-входа. ADR-0001.
Files: определяются design'ом (выделение из rab9_bot.py/msf_http.py/handlers.py, новый юнит).
Update Rule: изменение поведения = v-бамп + delta-карточка.
Neighbor Risks: operators/ (не байпасить), analysis-filters v1.0 (вызов фильтров), pumpportal_listener (фича 1 — контракт ingress).
Known Traps: процесс не имеет права слать в Telegram вообще; sink — единственный выход; демонтаж Telegram-модулей не должен задеть логику пайплайна.

### Requirement: standalone-process
Система SHALL выполнять полный аналитический прогон (ingress → cabal_detector → DexScreener → wallet_intel → DeepSeek → loop_verifier) в процессе, не содержащем python-telegram-bot и любых Telegram-вызовов, под systemd-юнитом `rab9-analyzer`.
#### Scenario: сигнал обработан без Telegram
GIVEN валидный POST /msf-signal
WHEN прогон завершён
THEN вердикт записан в sink, ни один Telegram-вызов не выполнен

### Requirement: signal-state-routing
Система SHALL иметь ЕДИНУЮ машину состояний сигнала с явным роутингом (устраняет конфликт v1.0 ↔ analysis-filters, кит-блокер e9293d74):

`NEW → T0_PENDING (мягкий чек, лог) → [выжил] → QUEUED → ANALYZED → SINK` / `[умер] → SINK(reject)`

- t0-перепроверка — ВНУТРЕННИЙ таймер очереди t0_pending (персистентной); она НЕ является повторным ingress-контактом и НЕ нарушает дедуп 24ч.
- Дедуп 24ч SHALL блокировать только повторный ПОЛНЫЙ AI-анализ одного адреса (не каскад, не ручной /analyze).
- SAFETY_GATES (operators): подтверждённый scam (honeypot=fail / rugcheck=rugged) = hard DROP на ЛЮБОМ этапе и перекрывает все мягкие гейты; мягкие эвристики — только понижение приоритета / INCONCLUSIVE.
- KABAL-эскалация «вне очереди» SHALL иметь собственный потолок (конфиг, старт ≤5/час) и общий bounded-лимит очередей (конфиг, старт 500; переполнение → строка дайджеста).
#### Scenario: конфликт разрешён
GIVEN мигрант на t=0 и дедуп-запись от первичного чека
WHEN наступает внутренняя перепроверка
THEN перепроверка выполняется (дедуп не нарушен — это не ingress-контакт)
#### Scenario: hard DROP перекрывает
GIVEN токен в очереди t0_pending и rugcheck=rugged
WHEN выполняется любой чек
THEN немедленный DROP → sink(reject), очередь очищена
#### Scenario: bounded очередь
GIVEN очередь анализа достигла конфиг-лимита
WHEN приходит новый кандидат (включая KABAL)
THEN кандидат → строка дайджеста, очереди не растут безгранично

### Requirement: verdict-taxonomy
Система SHALL использовать единую таксономию исходов: PASS (verifier прошёл, полный отчёт в дайджест) / FLAG (сомнение, полный отчёт с пометкой) / REJECT (мягкие гейты/фильтры, строка в дайджесте) / SKIP (дедуп/cooldown, без записи) / DROP (подтверждённый scam, строка в дайджесте) / HOLD (неопределённость verifier, строка). Маппинг type sink: PASS,FLAG,MANUAL → `verdict`; REJECT,SKIP,DROP,HOLD → `reject`; KABAL/KOL → `alert`; свод окна → `digest`.

### Requirement: delivery-reader-contract
Система определяет доставку: RAB9-агент (Hermes-профиль) SHALL читать `data/analyses_out/analyses.jsonl` по крону (окно дайджеста), парсить по схеме D-A1, доставлять владельцу в чат и фиксировать факт доставки offset-файлом `data/analyses_out/delivery_offset.json` (последний прочитанный id); записи до offset = доставлены, после = очередь. Анализатор SHALL NOT реализовывать доставку сам.
#### Scenario: агент забрал дайджест
GIVEN digest-запись в sink и delivery_offset позади неё
WHEN агент выполняет доставку
THEN offset обновлён на id digest-записи, повторной доставки нет

### Requirement: sink-contract
Система SHALL записывать каждый результат в `data/analyses_out/` (jsonl-лог + отдельный файл на запись) с полями `type` (`verdict`/`reject`/`alert`/`digest`/`manual`), `ts`, `token`, `address`, `text`; файлы SHALL переживать рестарт и подлежать ротации при переполнении каталога.
#### Scenario: вердикт в sink
GIVEN прогон завершился вердиктом PASS/FLAG
WHEN запись создана
THEN jsonl-строка и файл вердикта существуют и читаемы после рестарта процесса
#### Scenario: ручной анализ
GIVEN POST /analyze валидного адреса
WHEN прогон завершён
THEN запись с type=`manual` в sink и вердикт-ответ на HTTP-запрос

### Requirement: manual-analyze-endpoint
Система SHALL принимать POST /analyze на том же ingress-сервере (авторизация X-RAB9-SECRET, контракт {chain,address}) и запускать тот же прогон анализа; ответ SHALL содержать вердикт или статус обработки; доступ SHALL быть только с localhost.
#### Scenario: ручной запрос
GIVEN POST /analyze с валидным адресом и секретом
WHEN прогон завершён
THEN HTTP-ответ содержит вердикт, запись в sink с type=`manual`
#### Scenario: неавторизованный
GIVEN POST /analyze без корректного X-RAB9-SECRET
WHEN запрос обработан
THEN 401, прогон не запускается

### Requirement: digest-composition
Система SHALL формировать digest-записи в sink по накопительному правилу analysis-filters (окно/порог конфиг) и включать в digest: полные отчёты выживших PASS/FLAG, строки reject/skip, alert фаз, escalate MC>5M; состав digest SHALL быть достаточен для доставки владельцу без чтения сырых файлов.
#### Scenario: дайджест собран
GIVEN за окно накопились записи разных типов
WHEN окно дайджеста наступило (порог ≥3 выполнен)
THEN digest-запись в sink содержит свод всех записей окна

### Requirement: telegram-demolition
Система SHALL удалить из репо Telegram-слой ядра (handlers, keyboards, bot-инициализация, msf_listener) и SHALL сохранить все модули пайплайна (cabal_detector, wallet_intel, loop_verifier, msf_analysis-логика, operators, msf_dedupe) рабочими; юниты `msf-listener.service` и `rab9-crypto-hermes.service` выводятся из эксплуатации владельцем.
#### Scenario: демонтаж не ломает пайплайн
GIVEN Telegram-модули удалены
WHEN полный прогон и suite тестов выполняются
THEN все тесты зелёные, прогон не импортирует Telegram-модули
#### Scenario: дедуп сохранён
GIVEN повторный адрес в 24ч
WHEN сигнал поступает на ingress
THEN анализ не запускается повторно (msf_dedupe работает как прежде)
