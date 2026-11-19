# openspec/project.md — CDD-канон проекта RAB9

CDD-процесс: cdd-suite v1.4.0 (8 шагов, стоп-гейты, фриз спеки v-бампом, обязательная эскалация вне гейтов).

## Версии спек

| Дата | Фича | Версия | Карточка |
|------|------|--------|----------|
| — | llm-fallback | унаследована до CDD-канона | openspec/specs/llm-intel.md |
| 2026-10-11 | pumpportal-ingress | **v0.3** FROZEN (кит-прогон 891d0d9b: +subscription-liveness, +ws-keepalive) | openspec/specs/pumpportal-ingress.md |
| 2026-10-11 | analysis-filters | **v1.1** FROZEN (гармонизация e9293d74: дедуп-семантика, bounded, safety-priority) | openspec/specs/analysis-filters.md |
| 2026-10-11 | standalone-analyzer | **v1.2** FROZEN (ре-чек abab7dc9: 4 конфликта сняты — машина состояний канон, дедуп на ANALYZED, SKIP=дайджест, manual-флаг) | openspec/specs/standalone-analyzer.md |
| 2026-10-22 | wallet-watch | **v1.0** FROZEN (пуш движений watched-кошельков в sink) — в таблице не был зафиксирован, восстановлено 19.11 | openspec/specs/wallet-watch.md |
| 2026-10-22 | accumulation-radar | **v1.0** FROZEN (детектор организованного выкупа на просадке) — в таблице не был зафиксирован, восстановлено 19.11 | openspec/specs/accumulation-radar.md |
| 2026-11-19 | pumpportal-ingress | **v0.4** (GWT-биндинг T6: 9 сценариев → карточки с id + тесты; поведение не менялось) | openspec/specs/pumpportal-ingress.md |
| 2026-11-19 | analysis-filters | **v1.2** (GWT-биндинг T6: 9 сценариев → карточки с id + тесты; 3 сценария без реализации остались prose) | openspec/specs/analysis-filters.md |
| 2026-11-19 | standalone-analyzer | **v1.3** (GWT-биндинг T6: 14 сценариев → карточки с id + тесты; «агент забрал дайджест» остался prose) | openspec/specs/standalone-analyzer.md |
| 2026-11-19 | wallet-watch | **v1.1** (GWT-биндинг T6: 4 сценария → карточки с id + тесты) | openspec/specs/wallet-watch.md |
| 2026-11-19 | accumulation-radar | **v1.1** (GWT-биндинг T6: 6 сценариев → карточки с id + тесты) | openspec/specs/accumulation-radar.md |
| 2026-11-19 | analysis-filters | **v1.3** (T6, закрытие prose реальным поведением: концентрация top-10 ≥50%/<70% и confirmed-scam DROP связаны с verdict/queue-точками — DROP чистит обе очереди и пишет `sink(reject)`) | openspec/specs/analysis-filters.md |
| 2026-11-19 | analysis-filters | **v1.4** (T6 social-weight closure: per-token offline-классификатор негатива по снимку radar_x на rate_gate, ровно один X-вызов на токен, handoff в full analysis без второго search; BURNIE-jsonl не читается) | openspec/specs/analysis-filters.md |
| 2026-11-19 | standalone-analyzer | **v1.4** (T6 prose closure: внешний сценарий доставки помечен `no-ci` по `delivery-reader-contract` — offset принадлежит RAB9-агенту; текст шагов и поведение не менялись) | openspec/specs/standalone-analyzer.md |

## Правила

- Спека (ЧТО) всегда раньше дизайна (КАК).
- Фриз спеки = v-бамп в этой таблице; изменение замороженной спеки = v-бамп + delta-карточка.
- Карточка возможности: Purpose / Files / Neighbor Risks / Known Traps / Update Rule / GWT.
