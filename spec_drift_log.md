# Spec Drift Log — <node-name>

> Fail-closed журнал: spec-affecting мутация без записи = нарушение.
> Append-only (старые строки не редактировать). Поля: awk -F'|' → 2=время, 3=что меняю, 4=зачем, 5=что НЕ трогаю, 6=SHA/пусто. `|` в ячейках запрещён (использовать `\|`).

| Время (UTC) | Что меняю | Зачем | Что НЕ трогаю | SHA/пусто |
|---|---|---|---|---|
| 2026-09-05T12:30 | chart_analysis.py, burnie_sentiment_tracker.py | добавить волатильность в TA (дневная σ 14д, тренд, day range) по запросу Сергея; TA=35 главный вес | msf_listener, operators/, .env, systemd | |
| 2026-09-05T13:10 | chart_analysis.py, burnie_sentiment_tracker.py | окна волатильности 7/30/90д (горизонт Сергея: среднесрок), day_range убран (шум), архив дозаполняет до 126 свечей | msf_listener, operators/, .env, systemd | |
| 2026-09-07T03:18 | briefings/, LOG_DUMP_20260821_160833.txt, grok_manipulation_research_20260821_150547.txt | архив брифингов 21.08-06.09 и research-дампов (зачистка рабочего дерева) | .env, systemd, msf_listener |  |
| 2026-09-07T03:19 | burnie_price_watch.py, radar_x.py | коммит работы Alikhan от 21.08: buy_ratio BURNIE + KOL-swarm детект (manipulation research) | .env, systemd, msf_listener |  |
| 2026-09-08T23:20 | briefings/2026-09-07.md, briefings/2026-09-08.md | chrono-запись 08.09 (idle day) + брифинги 07-08.09 (рутинная отчётность) | .env, systemd, msf_listener, operators/ |  |
