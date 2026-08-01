# Circulation Graph — MGT_maccha #7

**Концепт:** информация не хранится — она течёт.
`работа → решение → артефакт → результат → обратно в работу`

## Circulation Edge Types

Поверх существующих структурных рёбер (`mentioned_in`, `occurred_on`, `described_as`) добавляем circulation-рёбра:

| Edge | От | К | Смысл |
|------|----|---|-------|
| **CAUSED** | event | decision | Событие вызвало решение |
| **FIXED_BY** | bug | fix | Баг исправлен фиксом |
| **RESULTED_IN** | action | outcome | Действие привело к результату |
| **LEARNED_FROM** | pattern | event | Паттерн извлечён из события |
| **APPLIED_TO** | pattern | project | Паттерн применён в проекте |
| **BROKE** | change | component | Изменение сломало компонент |
| **PREVENTED_BY** | bug_class | rule | Класс багов предотвращён правилом |

## Замкнутые циклы

### 1. Robot-man: metrics → strategy → content → metrics
```
X metrics (impressions/likes) 
  → CAUSED → strategy adjustment (STRATEGY.md update)
  → APPLIED_TO → content post
  → RESULTED_IN → new metrics
  → LEARNED_FROM → pattern for next cycle
```

### 2. Bug fix circulation (все проекты)
```
bug (CHRONOLOGY.md)
  → CAUSED → fix decision
  → FIXED_BY → code change
  → RESULTED_IN → resolved bug
  → LEARNED_FROM → pattern in AGENTS.md
  → APPLIED_TO → visible to other profiles
```

### 3. Cross-project pattern propagation
```
gulag: keyboard bug on iOS
  → FIXED_BY → contract gate rule
  → LEARNED_FROM → "always check input handlers after layout changes"
  → APPLIED_TO → alikhan (WhatsApp keyboard), rab9 (mobile), robot-man (AGENTS.md)
```

## Pipeline дополнение

После существующего Extract → Resolve → Assemble → Query → Maintain:
6. **Circulate** — замкнуть циклы: найти dangling outcomes, привязать metrics к decisions, пропагатировать patterns между проектами.

## Implementation

- `circulation.py` — новый модуль в knowledge_graph/
- Circulation edges добавляются при rebuild
- Cross-project propagation через Meta Knowledge Graph (`~/knowledge_graph/`)
