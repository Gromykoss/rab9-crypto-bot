# Spec Drift Log — <node-name>

> Fail-closed журнал: spec-affecting мутация без записи = нарушение.
> Append-only (старые строки не редактировать). Поля: awk -F'|' → 2=время, 3=что меняю, 4=зачем, 5=что НЕ трогаю, 6=SHA/пусто. `|` в ячейках запрещён (использовать `\|`).

| Время (UTC) | Что меняю | Зачем | Что НЕ трогаю | SHA/пусто |
|---|---|---|---|---|
| 2026-09-05T12:30 | chart_analysis.py, burnie_sentiment_tracker.py | добавить волатильность в TA (дневная σ 14д, тренд, day range) по запросу Сергея; TA=35 главный вес | msf_listener, operators/, .env, systemd | |
