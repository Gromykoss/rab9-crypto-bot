# Crypto (ex-RAB9) — рабочая среда Hermes

Проект: MSF-сигналы крипто-трейдинга с AI-анализом.
Бот: Python, Birdeye + DexScreener + xAI/Grok.
Путь: /home/hermes-workspace/rab9/

## Архитектура

Webhook (n8n-msf) → rab9_bot.py → Birdeye/DexScreener → Grok анализ → Telegram-сигнал

## Компоненты

- 5 enrichment модулей: radar_x (API+KB), radar_gh, chart (дневной), onchain, meme_score (100pts)
- Verifier: loop-verifier gate (PASS/FLAG/FAIL), REJECT default
- Loop engineering: trigger → process → verification → stop

## Мемкоины

- MC 1M+ = mid
- GitHub = норма
- X = ключевой сигнал
- BURNIE: 80/100 SOLID

## Быстрые команды

```bash
# Статус бота
ps aux | grep "[r]ab9_bot"

# База трейдов
sqlite3 /home/hermes-workspace/rab9/data/rab9_trades.db ".tables"

# Логи
journalctl -u rab9-crypto-hermes --no-pager -n 30
```

## Cron

- BURNIE sentiment tracker: script-first only (`python3 burnie_sentiment_tracker.py`). Cron prompt не должен писать inline Python/JS/shell бизнес-логику; если нужна правка логики — делегировать в Codex/Grok и менять script-файл.
- Token trim + skill audit (периодически)

## MoA верификация сигналов (v0.18)

При ручном анализе сигнала — использовать Mixture-of-Agents с пресетом `deepseek-xai`:

```
/moa deepseek-xai
```

Grok (reference) — мемкоин-радар, видит тренды X и виральность.
DeepSeek (aggregator) — синтезирует с риск-анализом, проверяет supply, onchain метрики.

Порог: если оба agree → PASS. Если расходятся → FLAG (ручная проверка). REJECT default сохраняется.

Для cron-сигналов MoA включается через prompt: «Use /moa deepseek-xai preset to verify this signal with Grok + DeepSeek consensus.»

## Loop Engineering (v0.18)

Применять паттерны из awesome-loop-engineering:

**Цикл сигнала:**
```
Trigger (n8n webhook) → Discover (Birdeye/DexScreener) → Delegate MAKER (Grok analysis)
→ Verify CHECKER (DeepSeek via MoA) → Persist (log + signal) → Decide (next or STOP)
```

**Стоп-условия (loop brakes):**
- goal met: PASS от обоих моделей в MoA
- budget spent: максимум 3 enrichment-модуля на сигнал
- stalled: один и тот же FLAG дважды → REJECT
- needs human: сигнал с MC > 5M или unknown token → escalate

**LOOP_PROGRESS.md:** каждый сигнал пишет одну строку в `data/loop_progress.md` — время, токен, вердикт, модели. Читать при старте для контекста.

**Maker ≠ Checker:** Grok предлагает (maker), DeepSeek проверяет (checker). Maker не объявляет себя done.

## Правила Сергея

- Self-test до отправки результата (локальный прогон, сравнить с x_search)
- Исправить гэпы перед отправкой
- Не слать сырые результаты
- «rtk примени» = сразу внедрять
- Кратко: Да/Нет/В архив/В работу/Применяй/Используй
- Раздельно с Алиханом (директории, venv, боты, БД, ключи — всё раздельно)
