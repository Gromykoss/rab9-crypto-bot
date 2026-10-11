# Spec: pumpportal-ingress — v0.3 FROZEN (2026-10-11, кит-прогон 891d0d9b)

> v0.2 → v0.3: по агрегации китов добавлены (1) наблюдаемый критерий живой подписки
> (ack-сообщение сервера + таймаут), (2) WS keepalive-политика. Остальное без изменений.
> Delta: openspec/specs/pumpportal-ingress-delta.md (v0.1→v0.2) + секция v0.2→v0.3 ниже.

Purpose: замена умершего MSF-пуш-входа. PumpPortal WS `subscribeMigration` →
Ingress HTTP `:8089/msf-signal`. Пайплайн анализа этой спекой НЕ затрагивается.
Files: `pumpportal_listener.py` (новый), `pumpportal-listener.service` (новый, ставит владелец).
Update Rule: изменение поведения = v-бамп в openspec/project.md + delta-карточка.
Neighbor Risks: msf_http (ingress-контракт), systemd-юнит (владелец).
Known Traps: миграции редки — отсутствие событий ≠ поломка; вход читает секрет, никогда не логирует его.

### Requirement: migration-ingest
Система SHALL подписываться на `wss://pumpportal.fun/api/data` с методом `subscribeMigration` и для каждого события, содержащего валидный Solana-адрес (`is_msf_solana_address`), отправлять POST `/msf-signal` `{chain:"solana", address}` с заголовком `X-RAB9-SECRET` из `.env`.
#### Scenario: миграция принята
GIVEN живое WS-соединение и событие migration с валидным адресом
WHEN событие обработано
THEN отправлен POST в `/msf-signal` и получен ответ 200 со статусом обработки
#### Scenario: событие без валидного адреса
GIVEN событие migration с пустым/невалидным адресом
WHEN событие обработано
THEN POST не отправляется, событие логируется как отфильтрованное

### Requirement: ingress-failure-handling
Система SHALL при не-200/таймауте ingress повторять POST до конфигурируемого числа попыток (старт 3) с экспоненциальным backoff, и при исчерпании попыток SHALL дописывать событие в персистентный файл `data/ingress_failed.jsonl` (переживает рестарт процесса); отложенные события SHALL быть повторно отправлены после восстановления ingress (проверка по health-check).
#### Scenario: ingress недоступен
GIVEN ingress отвечает таймаутом на 3 попытки
WHEN попытки исчерпаны
THEN событие дописано в `data/ingress_failed.jsonl` и доступно в файле после рестарта процесса
#### Scenario: восстановление ingress
GIVEN файл `data/ingress_failed.jsonl` непуст и ingress снова отвечает 200 на health-check
WHEN цикл повтора выполняется
THEN отложенные события переотправлены, при успехе файл очищается

### Requirement: resilient-connection
Система SHALL автоматически переподключаться к WS при обрыве с экспоненциальным backoff (старт 1с, кап 60с, конфигурируемо) и SHALL NOT завершать процесс; критерий восстановления: не позднее 70с от обрыва при непрерывной доступности PumpPortal.
#### Scenario: обрыв соединения
GIVEN активное соединение
WHEN WS закрывается или падает recv
THEN активная подписка восстановлена не позднее 70с от обрыва, события после реконнекта обрабатываются

### Requirement: subscription-liveness
Система SHALL считать подписку активной ТОЛЬКО после получения ack-сообщения сервера (подтверждение подписки) и SHALL логировать событие «subscription active» при каждом подтверждении; отсутствие ack в течение конфигурируемого таймаута (старт 30с) после коннекта SHALL трактоваться как неудача и вести к reconnect по backoff. Активность подписки SHALL быть наблюдаема по логу без доступа к сетевому трафику.
#### Scenario: ack получен
GIVEN соединение установлено и send subscribeMigration выполнен
WHEN сервер присылает подтверждение подписки
THEN в логе зафиксировано «subscription active» с текущей меткой времени
#### Scenario: ack не пришёл
GIVEN соединение установлено
WHEN ack не получен за PPP_SUB_ACK_TIMEOUT_S
THEN соединение закрыто инициировано reconnect по backoff-политике

### Requirement: ws-keepalive
Система SHALL держать WS keepalive включённым (ping interval и ping timeout — конфигурируемые параметры, старт 20с/20с) и SHALL трактовать истечение ping-таймаута (half-open соединение) как обрыв с переходом к reconnect-политике.
#### Scenario: half-open соединение
GIVEN соединение, у которого peer не отвечает на ping
WHEN ping timeout истёк
THEN соединение закрыто локально и запущен reconnect-цикл

### Requirement: secret-hygiene
Система SHALL читать секрет только из `.env:RAB9_HTTP_SECRET` и SHALL NOT логировать его или писать в файлы данных.
#### Scenario: лог-чистота
GIVEN любой путь выполнения (включая ошибки)
WHEN пишется лог
THEN секрет отсутствует в выводе
