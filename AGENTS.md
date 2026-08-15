# Crypto (ex-RAB9) — рабочая среда Hermes

Проект: MSF-сигналы крипто-трейдинга с AI-анализом.
Бот: Python, DexScreener + DeepSeek (primary) + Grok (X-радар).
Путь: /home/hermes-workspace/rab9/

---

# ⛔ CRITICAL GATES — ЧИТАЙ ПЕРВЫМ, ДО ЛЮБОГО ДЕЙСТВИЯ

**0. ЯЗЫК: все мысли (reasoning), ответы и обсуждения — ТОЛЬКО на русском. Без исключений.**

⚠️ DO NOT SKIP: read ALL rules in this file before acting. Самые нарушаемые правила — здесь, наверху.

0. **CONTEXT GATE (MANDATORY):** перед ЛЮБЫМ действием — выбрать триггер и загрузить контекст:
   ```bash
   python3 ~/.hermes/scripts/context_loader.py rab9 <trigger> [--max-tokens 500]
---

## 🗣️ Групповое общение в Buzz (multi-agent)

**Главное правило:** ты — один из нескольких агентов в общем рабочем пространстве. Отвечай **только** когда сообщение адресовано именно тебе.

### Перед каждым ответом в Buzz-канале проходи 5 шагов:

1. **Это мне?**  
   Есть прямое `@ИмяПрофиля` или `@твоё_имя`?  
   - Да → продолжай.  
   - Нет → **не отвечай** (даже если тема касается твоей зоны).

2. **Что было раньше?**  
   Прочитай последние сообщения в канале. Не отвечай в вакуум. Если кто-то уже ответил — не дублируй.

3. **Это чужая зона?**  
   Сообщение явно адресовано другому агенту (например `@Project-RobotMan`)?  
   → **Молчи**, даже если ты тоже можешь ответить.

4. **Это обвинение или претензия?**  
   Кто-то говорит «ты ошибся», «это сломалось», «кто это сделал»?  
   → Сначала проверь, действительно ли это твоя зона. Не принимай вину автоматически.

5. **Я уверен?**  
   Если сомневаешься — пиши «нужно проверить» или переадресуй: «Это к [другой агент]».

### Запрещено в групповом чате Buzz

- Отвечать на сообщения, адресованные другим агентам.
- Лезть в чужую зону «потому что могу помочь».
- Повторять то, что уже сказал другой агент.
- Использовать слово **«тишина»** (это триггер эхо-петли).
- Отвечать на сообщения без упоминания (если не стоит `default_profile`).

### ⛔ ПРАВИЛО ВОЗВРАТА В TELEGRAM (ОБЯЗАТЕЛЬНО)

Если работаешь с Сергеем по своему проекту в своей Telegram-группе и понадобилось **уйти в Buzz** (уточнить у другого агента, решить инфраструктурную проблему):

1. Ушёл в Buzz — решил вопрос — **ОБЯЗАТЕЛЬНО вернись в свою Telegram-группу**.
2. Продолжи работу с Сергеем / доложи результат там, где начал.
3. Buzz — **временный инструмент уточнения**, НЕ конечная точка. Не застревай: тебя ждёт ответ Сергею в Telegram.

**Проверка перед отправкой в Buzz:** «Ухожу за уточнением → вернусь в Telegram и закрою вопрос с Сергеем». Нет ответа в Telegram = работа НЕ закончена.

### Примеры правильного поведения

- `@Project-GULAG проверь баланс` → отвечает только GULAG.
- `@Project-RobotMan статистика поста` → молчит GULAG, даже если знает ответ.
- Сообщение без `@` → молчат все (кроме случаев `default_profile`).

**Цель:** каждый агент отвечает только за свою зону и только когда его позвали.

---


   ```
   Вывод вставить в reasoning ДО действия. Триггеры:
   - `session_start` → gates + last-3-days
   - `code_change` → gates + chronology (код бота)
   - `signal_analysis` → signal-flow + chronology (анализ сигналов)
   - `audit` → chronology + bugs
   - `default` → gates only

0. **CNC-ПРАВИЛО — Codex/Grok = ИНЖЕНЕРЫ, НЕ ОТВЁРТКА (26.07.2026):** Codex и Grok Build — станки с ЧПУ. Делегируй ЦЕЛЬ, не инструкцию. ❌ «В rab9_bot.py, строка 42, замени X на Y» → ✅ «BURNIE показал памп на 40%. Разберись в rab9_bot.py и DexScreener. Пойми паттерн. Предложи фильтр.» Codex читает код, анализирует, ПОНИМАЕТ. Ты проверяешь результат. **Обязательное чтение:** `~/.hermes/docs/graph-harness-principles.md`. **MoA Auto:** `skill_view('moa-auto')`.
   **⛔ НИКОГДА `delegate_task` без `acp_command`** — spawn default-сабагента (DeepSeek-клон), пустая трата токенов.
   **Правильные вызовы:** Codex = `delegate_task(acp_command='codex', goal=..., context=...)`, Grok = `delegate_task(acp_command='grok', acp_args=['agent', 'stdio'], goal=..., context=...)`.

1. **PRE-PATCH GATE (MANDATORY):** перед любым изменением кода — `grep -rn "имя" .`, показать grep пользователю, проследить логику в КАЖДОМ месте. Нет grep → патч не принят. Откат.
2. **No production without approval:** сигналы в Песочницу (`-1003979753733`) только через approval gate. Не менять systemd unit.
3. **REJECT default:** MoA — оба agree → PASS, расходятся → FLAG, иначе REJECT.
4. **НЕ байпасить** cabal_detector, wallet_intel, loop_verifier.
5. **Never expose credentials:** `msf_token.txt`, `TELEGRAM_BOT_TOKEN`, API ключи — не коммитить, не логировать.
6. **Раздельно с Алиханом:** директории, venv, боты, БД, ключи — всё раздельно.
7. **⛔ X/Twitter WRITE-ОПЕРАЦИИ — ЗАПРЕЩЕНЫ (02.08.2026):** xurl reply/post/like/retweet/follow — не зона Rab9. Rab9 = крипто-анализ, не управление X-аккаунтами. Единственное исключение: `xurl --app my-app --auth oauth2 /2/...` в read-only режиме для X-радара (radar_x.py). Публикация постов — только через robot-man профиль. Нарушение привело к багу 01.08.2026: xurl reply с голым tweet ID вместо текста.

---

## ⚖️ ENFORCED-ЗАКОНЫ (operators/ — детерминировано в коде, 15.08.2026)

Слой `operators/` зашивает поведение в enum-вердикты (`ALLOW/BLOCK/HOLD/DROP/REJECT/INCONCLUSIVE`), fail-closed. Чистые функции, stdlib-only, без side-effects. Детали: скилл `agent-laws-code-scaffold`, узел `Operator Layer — Детерминирование профилей`.

| Закон | Оператор | Вердикты | Точка вшивания |
|-------|----------|----------|----------------|
| **DESTINATION_LOCK** | `check_destination()` | ALLOW / BLOCK | `msf_http.send_msf_pairresolve` (ранний return) + `handlers` (helper `destination_allowed` во все 5 send-путей) + `alerts.alert_loop` + `burnie.send_telegram` |
| **REJECT_DEFAULT** | `check_verifier()` | ALLOW / REJECT / HOLD | `msf_http` verifier-gate (default `REJECT`, `except → suppress`, FLAG+`fixed_text`→ALLOW / FLAG без →HOLD) + `loop_verifier` 3 fail-ветки → `REJECT` |
| **APPROVAL_REQUIRED** (только мутации) | `check_mutation()` | ALLOW / HOLD / BLOCK | готов как fail-closed грань для будущих CLI-мутаций (конфиг/systemd/deploy меняет Сергей вручную) |
| **SAFETY_GATES** | `check_safety()` | ALLOW / DROP / INCONCLUSIVE | `msf_http.send_msf_pairresolve` + `handlers` (3 ручных анализа) + `msf_dedupe._is_junk`. DROP только на детерминированные scam-факты: `honeypot=fail` и `rugcheck=rugged`. `dead`/`high`/`unknown` → INCONCLUSIVE + пометка «⚠️ safety не подтверждена», НЕ молчание |

**Ключевое про destination (15.08.2026):** автопилот — сигналы шлются **без approval на каждое событие**. Allowlist = **ДВА** чата: Cryptanalyst `-1004425561477` + Песочница `-1003979753733`. Approval нужен **только на мутации конфига/деплой**. Отправка в любой чат вне allowlist → `BLOCK`.

**SAFETY-семантика (15.08.2026, проходы 1-4):** hard DROP = только подтверждённый scam (`honeypot=fail` по Jupiter, `rugcheck=rugged`). Эвристики (`phase=DEAD`, `rugcheck=high`) — НЕ DROP, а INCONCLUSIVE с честной пометкой в тексте, иначе автопилот ложно замолчит на легитимных тихих токенах (ранний вход). `build_compact_analysis_text` возвращает `(text, safety_flags)` из того же прогона (без повторного API), safety-факты читаются до verifier'а, предупреждение вшивается после verifier'а.

---

## Старт сессии

1. `skill_view("hermes-self-knowledge")` — 14 паттернов харнеса
2. Прочитай `~/hermes-vault/30_Logs/Арсенал Hermes.md`
3. Затем этот файл

## Архитектура (v2 — 07.07.2026)

### Поток сигналов

Мемы (Telegram) → @msf_rab_bot → msf_listener.py (long-poll) → HTTP POST :8089/msf-signal → rab9_bot.py → cabal_detector (pre-check) → DexScreener (enrichment) → wallet_intel (cross-reference KABAL) → DeepSeek (primary, 128K) → loop_verifier (PASS/FLAG/FAIL) → Telegram-сигнал в Песочницу

Примечание: Birdeye исключён 17.07.2026 (API key suspended). DexScreener — единственный источник обогащения.

### LLM Backend

| Модель | Провайдер | Стоимость | Контекст | Роль |
|--------|-----------|-----------|----------|------|
| **DeepSeek** | deepseek-v4-pro | — | 128K | Основной анализ |
| Grok (grok-3-mini) | xAI API | $0.30/1M | 32K | Research / X-радар |

Primary: DeepSeek.

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

## Архитектура и инфраструктура

### Сервер
| Параметр | Значение |
|----------|----------|
| **Хост** | VPS Hostinger |
| **IP** | 72.60.16.105 |
| **ОС** | Ubuntu 24.04 |
| **RAM** | 15 GB |
| **Диск** | 72/193 GB (37%) |

### Сервисы (systemd)
| Сервис | Файл | Назначение |
|--------|------|-----------|
| **rab9-crypto-hermes** | `rab9_bot.py` | Основной бот, HTTP :8089, анализ сигналов |
| **msf-listener** | `msf_listener.py` | Long-poll @msf_rab_bot, приём мемов |

### База данных
| Параметр | Значение |
|----------|----------|
| **Тип** | SQLite |
| **Файл** | `data/rab9_trades.db` |
| **Проверка** | `sqlite3 data/rab9_trades.db ".tables"` |

### Внешние API
| API | Назначение | Доступ |
|-----|-----------|--------|
| **DexScreener** | Обогащение токенов (цена, ликвидность, volume) | Публичный |
| **X API (xurl)** | X-радар (radar_x.py) | OAuth2, read-only |
| **DeepSeek API** | Primary LLM-анализ (128K контекст) | API key |
| **Grok (xAI)** | MoA-верификация, research | API key |

### Секреты и зависимости
| Файл | Содержание |
|------|-----------|
| `msf_token.txt` | Токен @msf_rab_bot |
| `.env` | `TELEGRAM_BOT_TOKEN`, API-ключи |

### Data Flow (полный цикл)
```
Мемы (Telegram)
  → @msf_rab_bot (приём)
    → msf_listener.py (long-poll)
      → HTTP POST :8089/msf-signal
        → rab9_bot.py (оркестратор)
          → cabal_detector (pre-check: cabal/не cabal)
            → DexScreener (обогащение: цена, ликвидность)
              → wallet_intel (cross-reference KABAL, P≥80%)
                → DeepSeek (primary analysis, 128K)
                  → loop_verifier (PASS/FLAG/FAIL)
                    → @rab2610bot (отправка)
                      → Песочница (-1003979753733)
```

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

DeepSeek (reference) — риск-анализ, supply, onchain.
Grok (aggregator) — мемкоин-радар, тренды X.

Порог: оба agree → PASS. Расходятся → FLAG. REJECT default.

Для cron: «Use /moa deepseek-xai preset to verify this signal with DeepSeek + Grok consensus.»

## Loop Engineering (v0.18)

**Цикл сигнала:**
Trigger (@msf_rab_bot → msf_listener.py) → Discover (DexScreener) → Delegate MAKER (DeepSeek) → Verify CHECKER (Grok via MoA) → Persist (log + signal) → Decide (next or STOP)

**Стоп-условия (loop brakes):**
- goal met: PASS от обоих в MoA
- budget spent: max 3 enrichment-модуля
- stalled: FLAG дважды → REJECT
- needs human: MC > 5M или unknown token → escalate

**LOOP_PROGRESS.md:** каждая строка — время, токен, вердикт, модели. Читать при старте.

**Maker ≠ Checker:** DeepSeek предлагает, Grok проверяет.

# ⚠️ DO NOT SKIP: прочитай ВСЕ правила ниже перед любым действием

## Правила строительства

**Общие правила (все проекты):** `skill_view('build')`

## Agent-Driven Development Rules (Codex CLI / Grok Build)

**Загрузить перед делегированием:** `skill_view('codex-grok-delegation')`

При делегировании задач в Codex CLI или Grok Build:

1. **Read docs first** — прочитать этот AGENTS.md + `CHRONOLOGY.md` перед любым изменением
2. **Use build plan** — для задач >20 строк кода: Шаблон 1 из `codex-grok-delegation` (Goal Mode)
3. **Preserve security** — НЕ байпасить cabal_detector, wallet_intel, loop_verifier. MSF-токены не логировать
4. **Verification ladder** — `pytest -q` → MSF test signal → grep .env → `journalctl -u rab9 -n 10` → CHRONOLOGY.md
5. **⛔ CHRONOLOGY АВТОМАТИЧЕСКИ** — после ЛЮБОГО фикса/инцидента сразу обнови CHRONOLOGY.md (датированная запись: причина→что сделал→как проверил→файлы). Не по напоминанию, не в конец сессии. Часть фикса.
6. **Reproducible setup** — `pip install -r requirements.txt`, использовать `RAB9_LLM=hy3|grok` из `.env`
7. **No production without approval** — сигналы в Песочницу (`-1003979753733`) только через approval gate. Не менять systemd unit
8. **Never expose credentials** — `msf_token.txt`, `TELEGRAM_BOT_TOKEN`, Birdeye/DexScreener ключи — не коммитить
9. **Preserve user changes** — `git status` перед работой, не перезаписывать чужие правки

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