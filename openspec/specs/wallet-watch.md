# Spec: wallet-watch — v1.0 FROZEN (2026-10-22)

Purpose: пуш движений отслеживаемых кошельков в sink (немедленная видимость китов).
Files: pumpportal_listener.py (расширяется), data/wallet_watch.json (новый).
Update Rule: v-бамп + delta. Neighbor Risks: pumpportal-ingress v0.3 (общая WS-сессия), sink (конкурентный append).
Known Traps: accountTrade-события не имеют полей токен-сигнала — НЕ routed в ingress; дедуп к ним не применяется.

### Requirement: wallet-subscription
Система SHALL подписываться на `subscribeAccountTrade` (keys = адреса из `data/wallet_watch.json`) в той же WS-сессии, что и `subscribeMigration`, и SHALL логировать ack обеих подписок; список кошельков SHALL перечитываться при каждом реконнекте.
#### Scenario: двойная подписка
GIVEN WS-соединение установлено и wallet_watch.json содержит ≥1 адрес
WHEN подписки отправлены
THEN получены ack обоих методов, «subscription active» в логе

### Requirement: wallet-event-to-sink
Система SHALL для каждого события `txType` (buy/sell) watched-кошелька записывать в sink `type=wallet` с полями `wallet`, `tx_type`, `token_amount`, `sol_amount`, `mint`; записи SHALL идти в общий дайджест немедленно.
#### Scenario: продажа кита
GIVEN событие txType=sell watched-кошелька
WHEN событие обработано
THEN sink-запись type=wallet содержит wallet/tx_type=sell/token_amount/sol_amount
#### Scenario: чужой кошелёк
GIVEN событие accountTrade по кошельку, не входящему в wallet_watch.json
WHEN событие обработано
THEN sink-запись НЕ создана

### Requirement: wallet-no-dedup
Система SHALL НЕ применять дедуп 24ч к wallet-событиям (движения одного кошелька — легитимные повторы); инвариант «один токен = один анализ» остаётся только для ingress-сигналов.
#### Scenario: повторное движение
GIVEN два движения одного watched-кошелька за час
WHEN оба обработаны
THEN обе записи в sink, дедуп не срабатывает
