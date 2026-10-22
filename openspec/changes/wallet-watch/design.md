# Design: wallet-watch (из спеки v1.0)

## Архитектура

Расширение `pumpportal_listener.py` (та же WS-сессия, один процесс):

1. `WALLET_FILE = BASE/"data"/"wallet_watch.json"` — список адресов (JSON array, перечитывается при реконнекте — без рестарта).
2. `_session()`: после ack `subscribeMigration` → `ws.send(subscribeAccountTrade, keys=wallets)` → await ack второго (message содержит 'Subscribed') → лог.
3. Маршрутизация входящих сообщений:
   - `msg["txType"] in ("buy","sell")` → wallet-событие: адрес из msg["traderPublicKey"] ∈ wallets → `sink.write("wallet", address=mint, token="?", text, ...)`? НЕТ — пишем поля по спеке: `sink.write("wallet", address=mint, token=msg.get("symbol","?"), text=строка-свод, extras через jsonl: wallet/tx_type/token_amount/sol_amount)`.
   - `msg["mint"]` без txType → старый ingest-путь (валидация + POST).
4. sink.write сигнатура не меняется — wallet-специфичные поля дописываются в текст + отдельный `wallet_events.jsonl` в sink-каталоге (maшиночитаемо: {id,ts,type:wallet,wallet,tx_type,token_amount,sol_amount,mint}).

## Поток данных

WS-событие → txType? → wallet_event (journal append) → sink.write("wallet", ...) → дайджест
                       └─ mint без txType → валидация → POST /msf-signal (старый путь)

## Конкурентность

sink.jsonl — O_APPEND (атомарно для строк ≤4К) из двух процессов (analyzer + listener) — безопасно; fsync на каждый append.

## Трассируемость

| Требование | Реализация |
|---|---|
| wallet-subscription | _session() второй subscribe + перечитывание списка при реконнекте |
| wallet-event-to-sink | маршрут txType → sink/journal |
| wallet-no-dedup | wallet-путь не вызывает loop_memory/msf_dedupe |
