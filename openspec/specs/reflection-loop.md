# Domain: reflection-loop

## Purpose
Maker/Judge рефлексия сигнала: Grok builder строит `SignalAnalysis`, DeepSeek judge выдаёт `JudgeVerdict` 4x PASS/FAIL, retry max 2, итог `ReflectionResult`.

## Files
- `structured_reflection.py`
- `tests/test_structured_reflection.py`

## Neighbor Risks
- `llm-intel`
- `msf_analysis`

## Known Traps
- `JudgeVerdict` строго 4 поля `Literal["PASS", "FAIL"]`; `issues` формируются как `key:FAIL` из `model_dump`, НЕ human-readable текст.
- `_call_grok` без `XAI_API_KEY` -> fallback `SignalAnalysis(verdict="pass", confidence=0.8)` — НЕ ошибка.
- `ReflectionResult.confidence` берётся из `signal_analysis.confidence` builder'а, НЕ judge.
- `routing_receipt`: `maker`/`reviewer`/`attempts`/`pattern`/`final`.

## Update Rule
Менял модель, loop или модель-полей -> обнови `tests/test_structured_reflection.py` и эту карточку.

## GWT Scenarios

### GIVEN maker-валидный SignalAnalysis + judge все PASS `reflection-loop.pass_on_first_try`
- WHEN `verify_signal` запускает Maker/Judge loop
- THEN `verdict="pass"`, `attempts=1`, confidence maker-овский, `routing_receipt.pattern="neil_xbt_structured"`

### GIVEN первый judge FAIL, второй PASS `reflection-loop.retry_then_pass`
- WHEN `verify_signal` повторяет проверку после fail-пути
- THEN `verdict="pass"`, `attempts=2`, `issues` накапливаются только в fail-пути

### GIVEN judge всегда FAIL `reflection-loop.fail_after_max_retries`
- WHEN `verify_signal` исчерпывает initial+2 retries
- THEN `verdict="fail"`, `attempts=3`, `issues` содержат `"<поле>:FAIL"`
