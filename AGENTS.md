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

## Правила Сергея

- Self-test до отправки результата (локальный прогон, сравнить с x_search)
- Исправить гэпы перед отправкой
- Не слать сырые результаты
- «rtk примени» = сразу внедрять
- Кратко: Да/Нет/В архив/В работу/Применяй/Используй
- Раздельно с Алиханом (директории, venv, боты, БД, ключи — всё раздельно)
