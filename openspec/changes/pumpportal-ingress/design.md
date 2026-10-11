# Design: pumpportal-ingress (из замороженной спеки v0.2, sha256 455df5f9…)

## Архитектура и границы

Один автономный процесс `pumpportal_listener.py` (stdlib + `websockets==16.0`).
Без импортов из ядра (ядро и Telegram-слой уходят в фиче 2) — модуль самодостаточен:

- `pumpportal_listener.py` — WS-клиент, валидатор адреса, POST-клиент, retry, персистентный журнал неудач.
- `pumpportal-listener.service` — systemd-юнит (System, не user; ставит владелец).

Валидатор адреса: копия логики `is_msf_solana_address` (base58, 32-44) внутри модуля.
Обоснование: msf_listener.py подлежит демонтажу в фиче 2 — общий импорт создал бы
ложную связность с мёртвым модулем. Дубликат 10 строк, расхождение маловероятно
(контракт ingress зафиксирован в msf_http).

## Конфигурация (только .env, без новых секретов)

| Переменная | Стартовое значение | Требование спеки |
|---|---|---|
| RAB9_HTTP_SECRET | уже в .env | secret-hygiene |
| PPP_WS_URL | wss://pumpportal.fun/api/data | migration-ingest |
| PPP_MAX_POST_ATTEMPTS | 3 | ingress-failure-handling |
| PPP_POST_BACKOFF_S | 2 (×2 на попытку) | ingress-failure-handling |
| PPP_RECONNECT_BACKOFF_S | 1 | resilient-connection |
| PPP_RECONNECT_CAP_S | 60 | resilient-connection |
| PPP_FAILED_FILE | data/ingress_failed.jsonl | ingress-failure-handling |
| PPP_INGRESS_URL | http://127.0.0.1:8089 (база для /msf-signal и /health) | migration-ingest |
| PPP_SUB_ACK_TIMEOUT_S | 30 | subscription-liveness (v0.3) |
| PPP_WS_PING_INTERVAL_S | 20 | ws-keepalive (v0.3) |
| PPP_WS_PING_TIMEOUT_S | 20 | ws-keepalive (v0.3) |
| PPP_REPLAY_DELAY_S | 1 | ingress-failure-handling (кит-фикс) |

## Потоки данных

1. **Основной:** WS-событие → извлечь `mint` → валидация → POST `/msf-signal`
   `{chain:"solana", address}` + `X-RAB9-SECRET` → 200: событие закрыто.
2. **Неудача POST:** не-200/timeout/исключение → retry до 3 с backoff 2/4/8с →
   append `{"ts","address","error"}` в `data/ingress_failed.jsonl` (open-append,
   однострочная запись, flock не нужен — один процесс).
3. **Восстановление (D3, per-line ack):** перед каждым новым POST (и по таймеру 60с) — GET `/health`;
   если 200 и файл неудач непуст → переотправка строк по порядку; строка удаляется
   ИНДИВИДУАЛЬНО после её успешного POST (переписывание файла после каждого ack,
   атомарно: tmp+rename, chmod 600 tmp) — частичный успех не даёт ни потери, ни дублей
   (дубли съест дедуп, но per-line ack их исключает); файл > 10К строк (аномалия) →
   ротация в ingress_failed.<ts>.jsonl с лог-алертом.
   КИТ-ФИКСЫ (агрегация 891d0d9b): (a) каждая строка журнала несёт уникальный `id`
   (uuid4) + `ts` — трассировка при ротации/переотправке; (b) append/ack-перезапись
   завершается fsync — персистентность переживает не только рестарт, но и crash; (c)
   replay-backoff: пауза PPP_REPLAY_DELAY_S (старт 1с) между переотправками — не
   долбить recovering ingress очередью.
4. **WS-обрыв:** исключение recv/connect → backoff 1с×2 до капа 60с → reconnect →
   re-subscribe (подписка не персистентна на стороне сервера).

## Инструмент POST/GET

`requests` (уже в requirements), вызовы ТОЛЬКО через `await asyncio.to_thread(...)`
(D1, ревью 58e960f8: блокирующий POST в event loop замораживает keepalive ping/pong
websockets → reconnect-чурн во время ретраев, подрыв R3). Явный `timeout=10` на все
HTTP-вызовы (requests default = бесконечный — запрещён). Блокировка recv на время
POST допустима — миграции редки, WS-буфер сервера держит сообщения.

## Влияние на существующий код

- Ноль изменений в ядре/пайплайне/operators — ingress-контракт уже существует.
- requirements.txt: +`websockets==16.0` (сделано, dc8ec47).
- Юнит: `ExecStart=venv python pumpportal_listener.py`, `Restart=always`,
  `WorkingDirectory=/home/hermes-workspace/rab9`, `After=network-online.target`.
  Установку делает владелец (`msf-listener.service` остаётся до фичи 2).

## Риски

- Anon-тир PumpPortal: лимиты при потоке — миграции редки, риск низкий; при блокировке
  WS-соединения процесс падает в reconnect-цикл (не крашится), аномалия видна в логе.
- `data/ingress_failed.jsonl` — новый файл в gitignored `data/` (ок).
- Health-check перед восстановлением очереди: `/health` подтверждает живость процесса
  rab9-crypto-hermes (единый endpoint — замечание Ревьюэра учтено: endpoint = GET /health).

## Трассируемость требование → дизайн

| Требование v0.2 | Реализация |
|---|---|
| migration-ingest | поток 1 + валидатор |
| ingress-failure-handling | потоки 2-3 + конфиг PPP_* |
| resilient-connection | поток 4 + конфиг PPP_RECONNECT_* |
| secret-hygiene | секрет только из .env, никогда в лог |
