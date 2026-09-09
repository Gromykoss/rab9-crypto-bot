# Domain: llm-intel

## Purpose
LLM-анализ токена с graceful degradation: deepseek -> grok -> template -> live.
Цепочка должна отдавать полезный текст без сырого API-error, когда провайдеры падают.

## Files
- `token_intel.py`
- `msf_template.py`
- `meme_score.py`
- `tests/test_llm_fallback.py`

## Neighbor Risks
- `msf_analysis`
- `structured_reflection`

## Known Traps
- OpenRouter API key error считается LLM-error даже при provider=`deepseek`: это историческая дыра и регресс-тест.
- Template fallback не выдумывает данные, а собирает карточку только из live/template kwargs.
- `ask_llm` не вызывает второго провайдера, если первичный ответ валидный.

## Update Rule
Менял LLM-цепочку, шаблон или anti-rug штрафы -> обнови `tests/test_llm_fallback.py` и эту карточку.

## GWT Scenarios

### GIVEN LLM-ответы разных провайдеров `llm-intel.is_llm_error_matrix`
- WHEN `_is_llm_error(text, provider)` проверяет ответы
- THEN паттерн-матрица: ключи/429/timeout/conn -> error, валидный анализ -> not error, OpenRouter-дыра закрыта

### GIVEN explicit/env RAB9_LLM `llm-intel.llm_order_resolution`
- WHEN `_resolve_llm_order(explicit)` выбирает порядок
- THEN порядок `[primary, fallback]`, `hy3` -> deepseek-алиас

### GIVEN ответы провайдеров `llm-intel.ask_llm_chain`
- WHEN `ask_llm(prompt)` проходит цепочку провайдеров
- THEN primary-ok -> без второго вызова; primary-error -> fallback; оба-error -> `""`

### GIVEN оба LLM упали `llm-intel.template_fallback`
- WHEN `ask_llm_with_template(...)` строит запасной ответ
- THEN template-текст с данными kwargs или `live_fallback_text`, src=`"template"`/`"live"`, не сырой error

### GIVEN score/liq/vol/mc/rugcheck `llm-intel.template_card_no_invent`
- WHEN `build_template_card(...)` строит карточку
- THEN карточка содержит name/score/dexscreener.com, без выдуманных значений

### GIVEN market-снапшоты `llm-intel.anti_rug_penalty_matrix`
- WHEN `anti_rug_penalty(...)` считает штраф
- THEN 30% buy_ratio -> >=3 note buy_ratio; liq 100 -> >=5 note liq; пустой market -> 0; старый high-mcap -> без sniper-note
