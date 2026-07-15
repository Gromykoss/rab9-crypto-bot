# Crypto (ex-RAB9) — рабочая среда Hermes

Проект: MSF-сигналы крипто-трейдинга с AI-анализом.
Бот: Python, Birdeye + DexScreener + xAI/Grok.
Путь: /home/hermes-workspace/rab9/

## Старт сессии

1. `skill_view("hermes-self-knowledge")` — 14 паттернов харнеса
2. Прочитай `~/hermes-vault/30_Logs/Арсенал Hermes.md`
3. Затем этот файл

## Архитектура (v2 — 07.07.2026)

### Поток сигналов

Мемы (Telegram) → @msf_rab_bot → msf_listener.py (long-poll) → HTTP POST :8089/msf-signal → rab9_bot.py → cabal_detector (pre-check) → Birdeye/DexScreener (enrichment) → wallet_intel (cross-reference KABAL) → Grok (xAI, $0.30/1M) → loop_verifier (PASS/FLAG/FAIL) → Telegram-сигнал в Песочницу

### LLM Backend

| Модель | Провайдер | Стоимость | Контекст | Роль |
|--------|-----------|-----------|----------|------|
| **Grok (grok-3-mini)** | xAI API | $0.30/1M | 32K | Основной анализ |
| DeepSeek | OpenRouter | pay-per-token | 128K | Fallback |

Fallback chain: Grok → DeepSeek.

### Два Telegram-бота

| Бот | Токен | Назначение |
|-----|-------|-----------|
| **@msf_rab_bot** | `msf_token.txt` | Слушает Мемы, детектит адреса |
| **@rab2610bot** | `.env:TELEGRAM_BOT_TOKEN` | Анализирует, шлёт в Песочницу (`-1003979753733`) |

### Компоненты

| Компонент | Файл | Статус |
|-----------|------|--------|
| **RAB9 Core** | `rab9_bot.py` | systemd: `rab9-crypto-hermes` |
| **MSF Listener** | `msf_listener.py` | background (→ systemd) |
| **MSF HTTP** | `msf_http.py :8089` | внутри rab9_bot.py |
| **Cabal Detector** | `cabal_detector.py` | pre-check |
| **Wallet Intel** | `wallet_intel.py` | cross-reference KABAL (P≥80%) |

- 5 enrichment модулей: radar_x, radar_gh, chart, onchain, meme_score (100pts)
- Verifier: loop-verifier (PASS/FLAG/FAIL), REJECT default
- Loop engineering: trigger → process → verification → stop

## Мемкоины

- MC 1M+ = mid
- GitHub = норма
- X = ключевой сигнал
- BURNIE: 80/100 SOLID

## Быстрые команды

```bash
ps aux | grep "[r]ab9_bot"
sqlite3 /home/hermes-workspace/rab9/data/rab9_trades.db ".tables"
journalctl -u rab9-crypto-hermes --no-pager -n 30
```

## Cron

BURNIE sentiment tracker: script-first only (`python3 burnie_sentiment_tracker.py`). Cron prompt не пишет inline бизнес-логику — делегировать в Codex/Grok.

## MoA верификация сигналов (v0.18)

При ручном анализе: `/moa deepseek-xai`

Grok (reference) — мемкоин-радар, тренды X.
DeepSeek (aggregator) — риск-анализ, supply, onchain.

Порог: оба agree → PASS. Расходятся → FLAG. REJECT default.

Для cron: «Use /moa deepseek-xai preset to verify this signal with Grok + DeepSeek consensus.»

## Loop Engineering (v0.18)

**Цикл сигнала:**
Trigger (@msf_rab_bot → msf_listener.py) → Discover (Birdeye/DexScreener) → Delegate MAKER (Grok) → Verify CHECKER (DeepSeek via MoA) → Persist (log + signal) → Decide (next or STOP)

**Стоп-условия (loop brakes):**
- goal met: PASS от обоих в MoA
- budget spent: max 3 enrichment-модуля
- stalled: FLAG дважды → REJECT
- needs human: MC > 5M или unknown token → escalate

**LOOP_PROGRESS.md:** каждая строка — время, токен, вердикт, модели. Читать при старте.

**Maker ≠ Checker:** Grok предлагает, DeepSeek проверяет.

## Правила строительства

**Общие правила (все проекты):** `skill_view('build')`

### ⛔ PRE-PATCH GATE (MANDATORY — все проекты)

Перед любым изменением кода:
1. `grep -rn "имя" .` — все места использования функции/переменной
2. Показать grep в ответе пользователю
3. Проследить логику в КАЖДОМ найденном месте
4. Только потом патч

Если grep не показан — патч не принят. Откат.

## Agent-Driven Development Rules (Codex CLI / Grok Build)

**Загрузить перед делегированием:** `skill_view('codex-grok-delegation')`

При делегировании задач в Codex CLI или Grok Build:

1. **Read docs first** — прочитать этот AGENTS.md + `CHRONOLOGY.md` перед любым изменением
2. **Use build plan** — для задач >20 строк кода: Шаблон 1 из `codex-grok-delegation` (Goal Mode)
3. **Preserve security** — НЕ байпасить cabal_detector, wallet_intel, loop_verifier. MSF-токены не логировать
4. **Verification ladder** — `pytest -q` → MSF test signal → grep .env → `journalctl -u rab9 -n 10` → CHRONOLOGY.md
5. **Reproducible setup** — `pip install -r requirements.txt`, использовать `RAB9_LLM=hy3|grok` из `.env`
6. **No production without approval** — сигналы в Песочницу (`-1003979753733`) только через approval gate. Не менять systemd unit
7. **Never expose credentials** — `msf_token.txt`, `TELEGRAM_BOT_TOKEN`, Birdeye/DexScreener ключи — не коммитить
8. **Preserve user changes** — `git status` перед работой, не перезаписывать чужие правки

### RAB9-специфичные

#### Cabal detection — обязательный этап
Каждый MSF-сигнал → `cabal_detector.analyze()` → если CABAL_EXPLOSION/KOL_ACTIVATION → алерт в Песочницу ДО основного анализа.

#### Wallet intelligence — cross-reference
Каждый MSF-сигнал → `wallet_intel.cross_reference_makers()` → если KABAL-кошелёк (P≥80%) в топ-20 мейкерах → эскалация.

#### Self-test перед отправкой
- Локальный прогон на тестовом адресе
- Сравнить с x_search
- Проверить формат: без кнопок, без сырых данных
- Гэпы закрыть до отправки

#### Инфраструктура RAB9 (при старте)
- RAB9 жив? `systemctl status rab9-crypto-hermes` (active)
- MSF HTTP жив? `curl http://localhost:8089/health` (200)
- MSF HTTP снаружи? `curl http://72.60.16.105:8089/health` (200)
- MSF Listener жив? `ps aux | grep "[m]sf_listener"` (PID)
- Сигналы идут? `journalctl -u rab9-crypto-hermes | grep "MSF analysis started" | tail -5`
- Telegram-бот отвечает? Тестовый адрес в Песочницу
- База трейдов жива? `sqlite3 data/rab9_trades.db "SELECT COUNT(*) FROM pair_trades"`

## Правила Сергея

- Self-test до отправки (локальный прогон, сравнить с x_search)
- Исправить гэпы перед отправкой
- Не слать сырые результаты
- «rtk примени» = сразу внедрять
- Кратко: Да/Нет/В архив/В работу/Применяй/Используй
- Раздельно с Алиханом (директории, venv, боты, БД, ключи — всё раздельно)