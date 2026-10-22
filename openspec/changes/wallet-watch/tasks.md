# Tasks: wallet-watch (спека v1.0 FROZEN, design 22.10)

MUST NOT: не routed wallet-события в ingress; дедуп к wallet-движениям не применять; не ломать WS-сессию migration.

## T1 — подписка + список кошельков
- [ ] data/wallet_watch.json (старт: 4EMfevH3...); перечитывание при реконнекте
- [ ] Второй subscribe в _session + ack-лог
- Критерий: тест — обе подписки отправлены, ack обоих логированы. GWT «двойная подписка».

## T2 — маршрут wallet-событий
- [ ] txType-события → wallet_events.jsonl + sink.write(type=wallet)
- [ ] НЕГАТИВ: чужой кошелёк → записи нет; wallet-путь не вызывает дедуп
- Критерий: тесты GWT «продажа кита»/«чужой кошелёк»/«повторное движение».

## T3 — приёмка (ручной gate)
- [ ] Рестарт pumpportal-listener (владелец/я), live ack обоих подписок в journalctl.
- Критерий: systemctl active + 'subscription active' ×2 в журнале.
