# Delta: pumpportal-ingress v0.1 → v0.2 (2026-10-11, ревью e61ce676, решение владельца — вариант «а»)

## Удалено из спеки (перенесено в фичу 2)
Требования R4-R9 меняли поведение пайплайна анализа, что противоречило заголовку
v0.1 «пайплайн не меняется» (major F1) и не имело трассируемости к Files (major F2).

| v0.1 | Куда перенесено |
|------|-----------------|
| R4 t0-cascade | openspec/specs/analysis-filters.md (DRAFT) |
| R5 migrant-risk-profile | openspec/specs/analysis-filters.md (DRAFT) |
| R6 social-weight | openspec/specs/analysis-filters.md (DRAFT) |
| R7 outcome-loop | openspec/specs/analysis-filters.md (DRAFT) |
| R8 delivery-discipline | openspec/specs/analysis-filters.md (DRAFT) |
| R9 rate-cap | openspec/specs/analysis-filters.md (DRAFT) |

Before: спека v0.1 заявляла 9 требований при Files=listener+service.
After: спека v0.2 = 4 требования listener-скоупа, Files полон, R4-R9 — в draft фильтров.

## Исправлены minor'ы в оставшихся требованиях
- F5 (новое): ingress-failure-handling — поведение при не-200/timeout: 3 попытки с
  backoff → персистентный `data/ingress_failed.jsonl` → переотправка после восстановления.
- F6: персистентность очереди определена (файл на диске, переживает рестарт).
- note R2: backoff сделан измеримым (1с старт, 60с кап, критерий 70с до активной подписки).

## Методика (selection-methodology.md) не менялась — остаётся v0.1 FROZEN как продукт-док фильтров.
