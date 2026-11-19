# Spec: wallet-watch — v1.1 FROZEN (2026-11-19, GWT-биндинг T6)> v1.0 → v1.1: GWT-биндинг — 4 сценария в карточной форме с id, тесты
> `tests/test_wallet_watch_gwt.py`. Текст шагов не менялся; поведение не менялось.


Purpose: пуш движений отслеживаемых кошельков в sink (немедленная видимость китов).
Files: pumpportal_listener.py (расширяется), data/wallet_watch.json (новый).
Update Rule: v-бамп + delta. Neighbor Risks: pumpportal-ingress v0.3 (общая WS-сессия), sink (конкурентный append).
Known Traps: accountTrade-события не имеют полей токен-сигнала — НЕ routed в ingress; дедуп к ним не применяется.

### Requirement: wallet-subscription
Система SHALL подписываться на `subscribeAccountTrade` (keys = адреса из `data/wallet_watch.json`) в той же WS-сессии, что и `subscribeMigration`, и SHALL логировать ack обеих подписок; список кошельков SHALL перечитываться при каждом реконнекте.
### GIVEN WS-соединение установлено и wallet_watch.json содержит ≥1 адрес — двойная подписка `wallet-watch.double_subscription_ack`
- WHEN подписки отправлены
- THEN получены ack обоих методов, «subscription active» в логе

### Requirement: wallet-event-to-sink
Система SHALL для каждого события `txType` (buy/sell) watched-кошелька записывать в sink `type=wallet` с полями `wallet`, `tx_type`, `token_amount`, `sol_amount`, `mint`; записи SHALL идти в общий дайджест немедленно.
### GIVEN событие txType=sell watched-кошелька — продажа кита `wallet-watch.whale_sell_to_sink`
- WHEN событие обработано
- THEN sink-запись type=wallet содержит wallet/tx_type=sell/token_amount/sol_amount
### GIVEN событие accountTrade по кошельку, не входящему в wallet_watch.json — чужой кошелёк `wallet-watch.foreign_wallet_ignored`
- WHEN событие обработано
- THEN sink-запись НЕ создана

### Requirement: wallet-no-dedup
Система SHALL НЕ применять дедуп 24ч к wallet-событиям (движения одного кошелька — легитимные повторы); инвариант «один токен = один анализ» остаётся только для ingress-сигналов.
### GIVEN два движения одного watched-кошелька за час — повторное движение `wallet-watch.no_dedup_repeat_move`
- WHEN оба обработаны
- THEN обе записи в sink, дедуп не срабатывает
