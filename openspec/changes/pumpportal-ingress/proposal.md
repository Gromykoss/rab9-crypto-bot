# Proposal: pumpportal-ingress

## Проблема

Пуш-вход проекта умер: Telegram-группа «Мемы» больше не существует, боты @msf_rab_bot и @rab2610bot удалены владельцем (11.10). `msf_listener.py` слушает несуществующий канал, `rab9_bot.py` не может подняться без токена. Сигнальный пайплайн без пуш-входа; поллинг-сканеры не покрывают ранний вход (миграции pump.fun).

## Зачем сейчас

Единственный живой пуш-кандидат — PumpPortal WS (проверен тест-коннектом с VPS 11.10: коннект OK, подписка принимается). Пока входа нет, KPI «Сигналы/день» держится только на сканерах. Вторая фича (standalone-ядро) независима и идёт следом.

## Скоуп

- Новый модуль `pumpportal_listener.py`: WS `wss://pumpportal.fun/api/data`, подписка ТОЛЬКО `subscribeMigration`.
- Конвертация события → POST `http://localhost:8089/msf-signal` `{chain:"solana", address}` + `X-RAB9-SECRET` (из `.env`, как у msf_listener).
- Ресилиенс: автопереподключение WS с backoff, логинг, один процесс.
- Юнит-файл `pumpportal-listener.service` (ставит владелец; я код + файл юнита в репо).
- Зависимость: `websockets==16.0` (уже в venv ~/rab9/venv, добавлена в requirements.txt при рефризе v0.2).
- Валидация адреса на входе до POST (та же логика `is_msf_solana_address`).
- SDG-интент перед мутацией; тест-сигнал через ingress для приёмки.

## Вне скоупа

- Демонтаж `msf_listener.py` / `msf-listener.service` → фича 2 (standalone-analyzer).
- Любые изменения пайплайна: cabal_detector, wallet_intel, loop_verifier, operators, msf_dedupe, дедуп 24ч — НЕ трогаем.
- Подписки `subscribeTokenTrade` / `subscribeNewToken` — отдельное решение после обкатки.
- Замена ботов/токенов — владелец отказался; доставка — фича 2.
- BURNIE-кроны (accumulator/sentiment/price watch) — не затрагиваются.

## Критерий готовности

1. `pumpportal_listener.py` поднимается, WS коннектится, при миграции шлёт валидный POST в `/msf-signal` и получает 200.
2. Валидный тест-сигнал (вставленный вручную адрес) проходит полный прогон: 200 + статус `sent` от ingress.
3. Обрыв WS → автопереподключение (тест: kill соединения → реконнект за backoff-окно).
4. Невалидный адрес → POST не отправляется (модуль фильтрует до сети).
5. `pytest -q` зелёный; SDG-интент закрыт SHA; CHRONOLOGY-запись в день изменения.
6. Юнит установлен владельцем, `systemctl is-active pumpportal-listener` = active.

## Границы интеграции

- Читает: `.env:RAB9_HTTP_SECRET`.
- Пишет: только в ingress `/msf-signal` и свой stdout-лог. Не пишет в БД/файлы данных.
- Затрагиваемые файлы: новый `pumpportal_listener.py`, новый `pumpportal-listener.service`, `.gitignore` (offset-стейт при необходимости), CHRONOLOGY.md, spec_drift_log.md.
