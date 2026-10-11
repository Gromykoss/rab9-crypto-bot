# Tasks: pumpportal-ingress (спека v0.2 FROZEN, design 6bc6f72)

MUST NOT (из Gates + спеки):
- Не логировать RAB9_HTTP_SECRET ни в каком пути.
- Не менять чужие/существующие systemd-юниты; T5 создаёт ТОЛЬКО новый юнит listener'а.
- Не отправлять ничего в Telegram из listener'а.
- Spec v0.2 заморожена: правки поведения = v-бамп, не тихая правка.

## T1 — WS-скелет с реконнектом [блокирует T2]
- [ ] Модуль pumpportal_listener.py: asyncio-цикл, websockets.connect(PPP_WS_URL),
      отправка subscribeMigration, обработка recv.
- [ ] Реконнект: исключение → backoff PPP_RECONNECT_BACKOFF_S ×2 до капа
      PPP_RECONNECT_CAP_S → reconnect + re-subscribe, процесс не завершается.
- Критерий готовности: интеграционный тест — kill активного соединения → активная
  подписка восстановлена ≤70с (замер в тесте); GWT «обрыв соединения».

## T2 — Ingest-путь [блокирует T3]
- [ ] Валидатор адреса (base58, 32-44, копия логики is_msf_solana_address).
- [ ] POST PPP_INGRESS_URL+/msf-signal {chain,address} + X-RAB9-SECRET из .env,
      строго через asyncio.to_thread, timeout=10.
- [ ] Конфиг PPP_* из .env (все 8 переменных design-таблицы).
- Критерий готовности: юнит-тест — невалидный адрес не порождает сетевой вызов
  (мок на границе сети); GWT «событие без валидного адреса». Интеграционный тест —
  200 + статус от живого ingress; GWT «миграция принята».

## T3 — Retry + персистентный журнал неудач [блокирует T4]
- [ ] Не-200/timeout/исключение → retry PPP_MAX_POST_ATTEMPTS с backoff
      PPP_POST_BACKOFF_S ×2 → append {"ts","address","error"} в PPP_FAILED_FILE.
- [ ] Восстановление: GET /health (timeout=10) перед POST и по таймеру 60с;
      файл непуст + health 200 → переотправка по порядку, per-line ack (перезапись
      файла после каждого ack: tmp + os.replace, chmod 600 tmp).
- [ ] Ротация: файл > 10000 строк → rename в ingress_failed.<ts>.jsonl + лог-алерт.
- Критерий готовности: тесты — «3 таймаута → файл пополнен, переживает рестарт
  процесса»; «частичный успех → ack'нутые строки удалены, неуспешные остались»;
  GWT «ingress недоступен» и «восстановление ingress».

## T4 — Лог-гигиена
- [ ] Аудит всех путей логирования: секрет не попадает в stdout/файлы/исключения.
- Критерий готовности: тест — прогон всех ветвей ошибок, grep секрета в собранном
  логе = 0 вхождений; GWT «лог-чистота».

## T5 — Юнит-файл + приёмка (ручной gate)
- [ ] pumpportal-listener.service в репо: System-scope, ExecStart=venv python,
      Restart=always, WorkingDirectory, After=network-online.target.
- [ ] РУЧНОЙ GATE (владелец): установка юнита, systemctl is-active = active,
      наблюдение живого коннекта в journalctl.
- Критерий готовности: owner-подтверждение active; GWT недоступен автотестом.
