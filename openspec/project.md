# openspec/project.md — CDD-канон проекта RAB9

CDD-процесс: cdd-suite v1.2.0 (8 шагов, стоп-гейты, фриз спеки v-бампом).

## Версии спек

| Дата | Фича | Версия | Карточка |
|------|------|--------|----------|
| — | llm-fallback | унаследована до CDD-канона | openspec/specs/llm-intel.md |
| 2026-10-11 | pumpportal-ingress | **v0.3** FROZEN (кит-прогон 891d0d9b: +subscription-liveness, +ws-keepalive) | openspec/specs/pumpportal-ingress.md |
| 2026-10-11 | analysis-filters | **v1.0** FROZEN (дайджест-дисциплина владельца) | openspec/specs/analysis-filters.md |
| 2026-10-11 | standalone-analyzer | **v1.0** FROZEN (ADR-0001) | openspec/specs/standalone-analyzer.md |

## Правила

- Спека (ЧТО) всегда раньше дизайна (КАК).
- Фриз спеки = v-бамп в этой таблице; изменение замороженной спеки = v-бамп + delta-карточка.
- Карточка возможности: Purpose / Files / Neighbor Risks / Known Traps / Update Rule / GWT.
