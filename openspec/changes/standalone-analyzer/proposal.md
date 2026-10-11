# Proposal: standalone-analyzer

## Проблема

Ядро (rab9_bot.py) — python-telegram-bot приложение: без валидного токена не стартует, а оба бота (@msf_rab_bot, @rab2610bot) удалены владельцем 11.10. Процесс ещё жив (поднят 26.09), Telegram-доставка внутри мертва — анализ сигналов идёт, вердикты теряются. Пуш-вход (PumpPortal) уже работает в ingress, но его результаты никуда не доходят. Песочница удалена, интерактивные команды бота мертвы.

## Зачем сейчас

Анализ выполняется и выбрасывается. Каждый сигнал миграции — потерянная работа LLM. Фича 1 закрыта, доставочный слой — единственный разрыв пайплайна.

## Скоуп

- **Standalone-анализатор**: выделение HTTP :8089 + пайплайна (cabal_detector → DexScreener → wallet_intel → DeepSeek → loop_verifier) из Telegram-приложения в самостоятельный процесс; новый systemd-юнит `rab9-analyzer` (ставит владелец, старый `rab9-crypto-hermes` гасит владелец).
- **Sink** `data/analyses_out/`: типы записей `verdict` (PASS/FLAG, полный отчёт), `reject`, `alert` (CABAL_EXPLOSION/KOL_ACTIVATION), `digest`. Формат — машиночитаемый jsonl + человекочитаемый текст вердикта.
- **Analysis-filters** (draft v0.0 → заморозка в этой фиче): каскад t=0 с персистентной очередью перепроверки, концентрация топ-10 холдеров, social-weight, outcome-loop 24ч (`data/verdict_outcomes.jsonl`), rate cap.
- **Ручной анализ**: эндпоинт POST `/analyze` на :8089 (тот же ingress-класс) — владелец присылает адрес в чат, RAB9-агент дёргает эндпоинт и доставляет вердикт.
- **Дайджест**: накопительный, окно 4ч (конфиг), порог ≥3 записей; ВЕСЬ вывод (reject, alert, вердикты) — через дайджест; полный отчёт — только для токенов, прошедших каскад выживания t0. Философия владельца: качество выше количества.
- **Демонтаж**: `msf_listener.py`, Telegram-модули ядра (handlers, keyboards, bot-инициализация), `alerts.py`-бот-пути (алерты фаз → sink); юниты `msf-listener.service` и `rab9-crypto-hermes.service` выключает владелец.

## Вне скоупа

- Возврат Telegram-ботов/токенов — отвергнуто владельцем.
- Доставка напрямую в Telegram из анализатора — нет: sink + RAB9-агент.
- GMGN-фильтр входа, hazard-rate модель — отдельные будущие фичи.
- BURNIE-кроны (accumulator/sentiment/price watch) — не затрагиваются.

## Критерий готовности

1. `rab9-analyzer` активен: POST `/msf-signal` валидного адреса → полный прогон → запись вердикта в sink (не Telegram).
2. Дайджест: ≥3 reject-записей → в следующем 4ч окне сформирован digest-файл.
3. `/analyze` валидного адреса → вердикт в sink с типом `manual`.
4. Outcome-loop: вердикт PASS старше 24ч → исход в `verdict_outcomes.jsonl`.
5. Демонтаж: msf_listener.py удалён, Telegram-модули не импортируются, suite зелёный.
6. Юниты: `rab9-analyzer` active (владелец), старые остановлены (владелец).
7. SDG-интенты закрыты SHA, CHRONOLOGY в день изменения.

## Границы интеграции

- Читает: `.env` (существующие ключи LLM), `data/kabal_library.json`, `data/community_sentiment.jsonl` (путь из фичи-cleanup).
- Пишет: `data/analyses_out/`, `data/verdict_outcomes.jsonl`, `data/rab9_trades.db` (как раньше), логи.
- НЕ трогает: operators/, cabal_detector, wallet_intel, loop_verifier (только их вызов), BURNIE-кроны, pumpportal_listener (фича 1).
