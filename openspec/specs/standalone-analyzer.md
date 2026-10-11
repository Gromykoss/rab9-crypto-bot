# Spec: standalone-analyzer — v1.0 FROZEN (2026-10-11)

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
