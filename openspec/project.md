# openspec/project.md — CDD-канон проекта RAB9

CDD-процесс: cdd-suite v1.2.0 (8 шагов, стоп-гейты, фриз спеки v-бампом).

## Версии спек

| Дата | Фича | Версия | Карточка |
|------|------|--------|----------|
| — | llm-fallback | унаследована до CDD-канона | openspec/specs/llm-intel.md |
| 2026-10-11 | pumpportal-ingress | **v0.2** FROZEN (сужение по ревью e61ce676; v0.1 → delta) | openspec/specs/pumpportal-ingress.md + -delta.md |
| — | analysis-filters | v0.0 DRAFT (фича 2, НЕ заморожена) | openspec/specs/analysis-filters.md |

## Правила

- Спека (ЧТО) всегда раньше дизайна (КАК).
- Фриз спеки = v-бамп в этой таблице; изменение замороженной спеки = v-бамп + delta-карточка.
- Карточка возможности: Purpose / Files / Neighbor Risks / Known Traps / Update Rule / GWT.
