# Crypto (ex-RAB9) — рабочая среда Hermes

Проект: MSF-сигналы крипто-трейдинга с AI-анализом.
Бот: Python, Birdeye + DexScreener + xAI/Grok.
Путь: /home/hermes-workspace/rab9/

## Старт сессии

1. `skill_view("hermes-self-knowledge")` — 14 паттернов харнеса
2. Прочитай `~/hermes-vault/30_Logs/Арсенал Hermes.md` — полный арсенал
3. Затем этот файл

## Архитектура (v2 — 07.07.2026, n8n исключён)

### Поток сигналов

```
Мемы (Telegram) → @msf_rab_bot (видит сообщение)
    → msf_listener.py (long-poll, событийная модель)
        → HTTP POST :8089/msf-signal
            → rab9_bot.py
                → cabal_detector (pre-check)
                → Birdeye/DexScreener (enrichment)
                → wallet_intel (cross-reference KABAL)
                → Hy3 295B анализ (OpenRouter, free tier, 256K ctx)
                → loop_verifier (PASS/FLAG/FAIL)
                → Telegram-сигнал в Песочницу
```

### LLM Backend

| Модель | Провайдер | Стоимость | Контекст | Роль |
|--------|-----------|-----------|----------|------|
| **Tencent Hy3 295B** | OpenRouter (free) | **$0** | 256K | Основной анализ |
| Grok (grok-3-mini) | xAI | $0.30/1M | 32K | Fallback (`RAB9_LLM=grok`) |

Переключение: `RAB9_LLM=hy3|grok` в `.env`. Hy3 даёт более структурный анализ с конкретными цифрами (Liq/MC%, Vol/MC%, b/s ratio).

### Два Telegram-бота

| Бот | Токен | Назначение |
|-----|-------|-----------|
| **@msf_rab_bot** | `msf_token.txt` | Слушает Мемы, детектит DexScreener/адреса |
| **@rab2610bot** | `.env:TELEGRAM_BOT_TOKEN` | Анализирует, шлёт в Песочницу (`-1003979753733`) |

### Компоненты

| Компонент | Файл | PID/Статус |
|-----------|------|-----------|
| **RAB9 Core** | `rab9_bot.py` | systemd: `rab9-crypto-hermes` |
| **MSF Listener** | `msf_listener.py` | background (потеряется при ребуте → systemd) |
| **MSF HTTP** | `msf_http.py` :8089 | внутри rab9_bot.py |
| **Cabal Detector** | `cabal_detector.py` | pre-check перед анализом |
| **Wallet Intel** | `wallet_intel.py` | cross-reference KABAL (8 шт, P≥80%) |

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
Trigger (@msf_rab_bot → msf_listener.py) → Discover (Birdeye/DexScreener) → Delegate MAKER (Grok analysis)
→ Verify CHECKER (DeepSeek via MoA) → Persist (log + signal) → Decide (next or STOP)
```

**Стоп-условия (loop brakes):**
- goal met: PASS от обоих моделей в MoA
- budget spent: максимум 3 enrichment-модуля на сигнал
- stalled: один и тот же FLAG дважды → REJECT
- needs human: сигнал с MC > 5M или unknown token → escalate

**LOOP_PROGRESS.md:** каждый сигнал пишет одну строку в `data/loop_progress.md` — время, токен, вердикт, модели. Читать при старте для контекста.

**Maker ≠ Checker:** Grok предлагает (maker), DeepSeek проверяет (checker). Maker не объявляет себя done.

## Правила строительства RAB9 v1

### 1. Техзадание — сначала думать

- **Диагностика перед кодом.** Прежде чем патчить — проверить инфраструктуру: порт, firewall, логи, curl снаружи.
- **Не бежать впереди.** Никаких деплоев без проверки что сломано.
- **Фиксировать.** Архитектурные решения — в этот файл.

### 2. Инфраструктуру верифицировать при старте

- RAB9 жив? `systemctl status rab9-crypto-hermes` (active)
- MSF HTTP жив? `curl http://localhost:8089/health` (200)
- MSF HTTP снаружи? `curl http://72.60.16.105:8089/health` (200)
- MSF Listener жив? `ps aux | grep "[m]sf_listener"` (PID есть)
- Сигналы идут? `journalctl -u rab9-crypto-hermes | grep "MSF analysis started" | tail -5`
- Telegram-бот отвечает? Послать тестовый адрес в Песочницу
- База трейдов жива? `sqlite3 data/rab9_trades.db "SELECT COUNT(*) FROM pair_trades"`

### 3. Pre-deploy чеклист RAB9

1. `git diff` — что меняется?
2. `python3 -c "import ast; ast.parse(open('file.py').read())"` — синтаксис
3. `sudo systemctl restart rab9-crypto-hermes` — рестарт
4. `curl http://localhost:8089/health` — проверка
5. Тестовый сигнал через Telegram — пришёл?

### 4. Cabal detection — обязательный этап

Каждый MSF-сигнал → сначала `cabal_detector.analyze()` → если CABAL_EXPLOSION/KOL_ACTIVATION → алерт в Песочницу ДО основного анализа.

### 5. Wallet intelligence — cross-reference

Каждый MSF-сигнал → `wallet_intel.cross_reference_makers()` → если KABAL-кошелёк (P≥80%) в топ-20 мейкерах → эскалация.

### 6. Правило отката

```bash
git checkout HEAD~1 -- file.py
sudo systemctl restart rab9-crypto-hermes
```

### 7. Баги → документ

Каждый баг → BUGS.md в корне rab9/. Формат: ID, симптом, причина, fix, статус.

### 8. Self-test перед отправкой

- Локальный прогон анализа на тестовом адресе
- Сравнить с x_search (не противоречит?)
- Проверить формат: без кнопок, без сырых данных
- Гэпы закрыть до отправки

## Правила Сергея

- Self-test до отправки результата (локальный прогон, сравнить с x_search)
- Исправить гэпы перед отправкой
- Не слать сырые результаты
- «rtk примени» = сразу внедрять
- Кратко: Да/Нет/В архив/В работу/Применяй/Используй
- Раздельно с Алиханом (директории, venv, боты, БД, ключи — всё раздельно)
