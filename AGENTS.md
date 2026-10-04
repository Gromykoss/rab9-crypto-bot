# Crypto (ex-RAB9) — рабочая среда Hermes

Проект: MSF-сигналы крипто-трейдинга с AI-анализом.
Бот: Python, DexScreener + DeepSeek (primary) + Grok (X-радар).
Путь: /home/hermes-workspace/rab9/

---

# ⛔ CRITICAL GATES — ЧИТАЙ ПЕРВЫМ, ДО ЛЮБОГО ДЕЙСТВИЯ

**0. ЯЗЫК: все мысли (reasoning), ответы и обсуждения — ТОЛЬКО на русском. Без исключений.**

⚠️ DO NOT SKIP: read ALL rules in this file before acting. Самые нарушаемые правила — здесь, наверху.

0. **CONTEXT GATE (MANDATORY):** перед ЛЮБЫМ действием — `python3 ~/.hermes/scripts/context_loader.py rab9 <trigger> [--max-tokens 500]`. Триггеры: `session_start` → gates + last-3-days · `code_change` → gates + chronology · `signal_analysis` → signal-flow + chronology · `audit` → chronology + bugs · `default` → gates only.

0.5. **CONTRACT INDEX GATE (05.09.2026):** единый вход сессии — PROJECT_MEMORY_GRAPH.md (корень). Boot Rule: граф + AGENTS Gates на старте, остальные доки по маршруту из графа. Изменил домен/инвариант → обнови граф + CHRONOLOGY; иначе запись «Contract index update: not needed» в CHRONOLOGY. Старт сессии: 1) `~/rab9/CHRONOLOGY.md` (последние события), 2) `~/hermes-vault/30_Logs/Арсенал Hermes.md`, 3) этот файл.

## 🗣️ Buzz (multi-agent): правило ответа

Отвечай **только** когда адресовано тебе (`@Project-RAB9`). Перед ответом: 1) прямое упоминание? нет → молчи; 2) не дублируй сказанное другим; 3) чужая зона → молчи; 4) обвинение → сначала сверься с данными, вину автоматически не принимай; 5) не уверен → «нужно проверить» или переадресуй. Без `@` → молчат все (кроме `default_profile`); слово **«тишина»** запрещено (эхо-петля).

**Возврат в Telegram (ОБЯЗАТЕЛЬНО):** ушёл в Buzz за уточнением → вернись в свою Telegram-группу и закрой вопрос с Сергеем там. Нет ответа в Telegram = работа НЕ закончена. Пример: `@Project-GULAG проверь баланс` → отвечает только GULAG.

1. **PRE-PATCH GATE (MANDATORY):** перед любым изменением кода — `grep -rn "имя" .`, показать grep пользователю, проследить логику в КАЖДОМ месте. Нет grep → патч не принят. Откат.
2. **No production without approval:** сигналы в Песочницу (`-1003979753733`) только через approval gate. Не менять systemd unit.
3. **REJECT default:** MoA — оба agree → PASS, расходятся → FLAG, иначе REJECT.
4. **НЕ байпасить** cabal_detector, wallet_intel, loop_verifier.
5. **Never expose credentials:** `msf_token.txt`, `TELEGRAM_BOT_TOKEN`, API ключи — не коммитить, не логировать.
6. **Раздельно с Алиханом:** директории, venv, боты, БД, ключи — всё раздельно.
7. **⛔ X/Twitter WRITE — ЗАПРЕЩЕНЫ (02.08.2026):** xurl reply/post/like/retweet/follow — не зона Rab9 (публикация — только robot-man). Исключение: `xurl --app my-app --auth oauth2 /2/...` read-only для X-радара (radar_x.py). Инцидент 01.08: голый tweet ID вместо текста в reply.
8. **CNC-ПРАВИЛО (26.07.2026):** Codex/Grok Build — ИНЖЕНЕРЫ, не отвёртка: делегируй ЦЕЛЬ, не инструкцию (❌ «строка 42 замени X» → ✅ «BURNIE пампнул 40%, разберись и предложи фильтр»). Чтение: `~/.hermes/docs/graph-harness-principles.md`. **Никогда `delegate_task` без `acp_command`** (spawn default-сабагента = пустая трата токенов). Вызовы: Codex = `delegate_task(acp_command='codex', goal, context)`, Grok = `delegate_task(acp_command='grok', acp_args=['agent','stdio'], goal, context)`.

## ⚖️ ENFORCED-ЗАКОНЫ (operators/ — детерминировано в коде, 15.08.2026)

Слой `operators/` зашивает поведение в enum-вердикты (`ALLOW/BLOCK/HOLD/DROP/REJECT/INCONCLUSIVE`), fail-closed, чистые функции, stdlib-only. Детали: узел «Operator Layer» в PROJECT_MEMORY_GRAPH.md.

| Закон | Оператор | Вердикты | Точка вшивания |
|-------|----------|----------|----------------|
| **DESTINATION_LOCK** | `check_destination()` | ALLOW / BLOCK | `msf_http.send_msf_pairresolve` (ранний return) + `handlers` (helper `destination_allowed` во все 5 send-путей) + `alerts.alert_loop` + `burnie.send_telegram` |
| **REJECT_DEFAULT** | `check_verifier()` | ALLOW / REJECT / HOLD | `msf_http` verifier-gate (default `REJECT`, `except → suppress`, FLAG+`fixed_text`→ALLOW / FLAG без →HOLD) + `loop_verifier` 3 fail-ветки → `REJECT` |
| **APPROVAL_REQUIRED** (только мутации) | `check_mutation()` | ALLOW / HOLD / BLOCK | fail-closed грань для будущих CLI-мутаций (конфиг/systemd/deploy меняет Сергей вручную) |
| **SAFETY_GATES** | `check_safety()` | ALLOW / DROP / INCONCLUSIVE | `msf_http.send_msf_pairresolve` + `handlers` (3 ручных анализа) + `msf_dedupe._is_junk` |

- **Destination:** автопилот шлёт без approval на событие; allowlist = **ДВА** чата: Cryptanalyst `-1004425561477` + Песочница `-1003979753733`. Вне allowlist → `BLOCK`. Approval — только на мутации конфига/деплой.
- **Safety-семантика:** hard DROP = только подтверждённый scam (`honeypot=fail` Jupiter, `rugcheck=rugged`). Эвристики (`phase=DEAD`, `rugcheck=high`) → INCONCLUSIVE + честная пометка «⚠️ safety не подтверждена», НЕ молчание (иначе автопилот ложно замолчит на легитимных тихих токенах). `build_compact_analysis_text` возвращает `(text, safety_flags)` из того же прогона; предупреждение вшивается после verifier'а.

## Архитектура (v2 — 07.07.2026)

**Поток сигналов:** Мемы (Telegram) → @msf_rab_bot → msf_listener.py (long-poll) → HTTP POST :8089/msf-signal → rab9_bot.py → cabal_detector (pre-check) → DexScreener (enrichment) → wallet_intel (cross-ref KABAL) → DeepSeek (primary, 128K) → loop_verifier (PASS/FLAG/FAIL) → Telegram-сигнал в Песочницу. Birdeye исключён 17.07.2026; DexScreener — единственный источник обогащения.

**LLM backend:** DeepSeek `deepseek-v4-pro` (128K, основной анализ) · Grok `grok-3-mini` xAI ($0.30/1M, 32K, research/X-радар). xAI напрямую; cron-модель glm-5.3-flash (Nous Portal).

**Два Telegram-бота:** @msf_rab_bot (`msf_token.txt`) слушает Мемы, детектит адреса · @rab2610bot (`.env:TELEGRAM_BOT_TOKEN`) анализирует, шлёт в Песочницу.

**Компоненты:** RAB9 Core `rab9_bot.py` (systemd `rab9-crypto-hermes`) · MSF Listener `msf_listener.py` (system-юнит `msf-listener.service`, MainPID) · MSF HTTP `msf_http.py:8089` (внутри rab9_bot.py) · Cabal Detector `cabal_detector.py` (pre-check) · Wallet Intel `wallet_intel.py` (cross-ref KABAL, P≥80%) · 5 enrichment: radar_x, radar_gh, chart, onchain, meme_score (115 pts, 7-pillar v3.0) · Verifier: loop-verifier (PASS/FLAG/FAIL), REJECT default.

**Сервер:** VPS Hostinger 72.60.16.105, Ubuntu 24.04, RAM 15 GB, диск 120/193 GB (62%). **БД:** SQLite `data/rab9_trades.db`. **API:** DexScreener (публичный), X API via xurl (OAuth2 read-only), DeepSeek, Grok/xAI.

**Loop Engineering (v0.18):** Trigger → Discover (DexScreener) → Delegate MAKER (DeepSeek) → Verify CHECKER (Grok, MoA `/moa deepseek-xai`) → Persist → Decide. Стоп-условия: PASS от обоих · max 3 enrichment-модуля · FLAG дважды → REJECT · MC > 5M / unknown → escalate. Maker ≠ Checker: DeepSeek предлагает, Grok проверяет.

## KPI

| Метрика | Что меряет | Цель |
|---------|-----------|------|
| Сигналы/день | MSF-сигналы, доведённые до анализа за 24ч | >0 (мемы молчат ≠ поломка) |
| Точность верификатора | PASS/FLAG loop_verifier, совпавшие с ручным исходом | ≥80% |
| False-positive rate | доля REJECT/SKIP (thin-liq / MC>5M / scam) | <15% |
| Аптайм листенера | `systemctl is-active msf-listener` | 100% (MainPID жив) |
| Latency | мем → сигнал в Песочницу | <5 мин |

## Мемкоины

- MC 1M+ = mid · GitHub = норма · X = ключевой сигнал · BURNIE: 80/100 SOLID

## Cron

BURNIE sentiment tracker: script-first only (`python3 burnie_sentiment_tracker.py`). Cron prompt не пишет inline бизнес-логику — делегировать в Codex/Grok.

# Правила строительства

**Общие правила (все проекты):** `skill_view('build')`. **Перед делегированием:** `skill_view('codex')` / `skill_view('grok-build-cli')`.

При делегировании Codex/Grok Build:
1. **Read docs first** — этот AGENTS.md + CHRONOLOGY.md перед любым изменением; **Preserve user changes** — `git status` перед работой
2. **Goal Mode** для задач >20 строк: делегируй ЦЕЛЬ, не инструкцию (см. gate #8)
3. **Verification ladder** — `pytest -q` → MSF test signal → grep .env → `journalctl -u rab9 -n 10` → CHRONOLOGY.md
4. **⛔ CHRONOLOGY АВТОМАТИЧЕСКИ** — после ЛЮБОГО фикса/инцидента сразу датированная запись (причина→что сделал→как проверил→файлы). Часть фикса, не «в конце сессии»
5. Gates #2 (approval), #4 (не байпасить), #5 (секреты, включая Birdeye/DexScreener ключи), #6 (раздельно с Алиханом) — обязательны и при делегировании; **MSF-токены не логировать**

### RAB9-специфичное

- **Cabal detection:** каждый MSF-сигнал → `cabal_detector.analyze()` → CABAL_EXPLOSION/KOL_ACTIVATION → алерт в Песочницу ДО основного анализа.
- **Wallet intel:** каждый MSF-сигнал → `wallet_intel.cross_reference_makers()` → KABAL-кошелёк (P≥80%) в топ-20 мейкерах → эскалация.
- **Self-test перед отправкой:** локальный прогон на тестовом адресе, сверка с x_search, формат без кнопок и сырых данных, гэпы закрыть до отправки.

### Инфраструктура RAB9 (при старте)
- RAB9 жив? `systemctl status rab9-crypto-hermes` (active)
- MSF HTTP жив? `curl http://localhost:8089/health` (200) и снаружи `curl http://72.60.16.105:8089/health` (200)
- MSF Listener жив? `systemctl status msf-listener.service` (MainPID=листенер, active). НЕ `systemctl --user start` — user-scope дубль поднимет второй long-poll = 409.
- Сигналы идут? `journalctl -u rab9-crypto-hermes | grep "MSF analysis started" | tail -5`
- Telegram-бот отвечает? Тестовый адрес в Песочницу · БД жива? `sqlite3 data/rab9_trades.db "SELECT COUNT(*) FROM pair_trades"`

## Правила Сергея

- «rtk примени» = сразу внедрять
- Кратко: Да/Нет/В архив/В работу/Применяй/Используй
- Самотест и «раздельно с Алиханом» — уже в CRITICAL GATES, не дублировать

## SPEC DRIFT GATE (перед любой spec-affecting мутацией)
Spec-affecting мутация = правка кода/данных/конфига/спеки узла. Отчёты/посты/сбор/чтение — мимо гейта.
1. ДО мутации — append-строка в spec_drift_log.md (через flock, см. шаг журнала): время UTC, что меняю (ПУТИ файлов), зачем (инвариант/требование), что НЕ трогаю. Поле результата пустое.
2. Выполнить мутацию.
3. Закоммитить. Hook пропустит по открытому интенту — интент ОДНОРАЗОВЫЙ: после коммита строка считается закрытой, следующий spec-affecting коммит требует НОВОЙ строки.
4. СРАЗУ после коммита — дописать SHA в поле результата той же строки (в рабочей копии, попадёт в следующий коммит или остаётся локально — аудит сверяет по timestamp+файлам).
5. Незаписанная мутация = нарушение (аудит в scorecard оператора). Fail-closed.

Формат: | Время-UTC | что меняю (пути) | зачем | что НЕ трогаю | SHA/пусто |

Пример: `| 2026-09-06T08:00 | gateway/run.py | fix suppress race | tests/ | 708eac5790 |` (открытый интент = поле 6 пусто; закрытый = SHA дописан).
Разбор полей: awk -F'|' — поле 2 = Время, 3 = что меняю, 4 = зачем, 5 = что НЕ трогаю, 6 = SHA/пусто. `|` в ячейках (заменять `\|`) и переносы строк запрещены.

Запрещено: код без записи; «улучшать спеку молча»; записи задним числом; редактирование старых строк (только append).
Meta-правило: правка AGENTS.md — тоже spec-affecting (кроме самой этой секции при bootstrap).
Bootstrap: самый первый коммит, СОЗДАЮЩИЙ spec_drift_log.md в репо, разрешён без интента (журнала ещё нет — ловить нечем). Помечается в теме коммита `[drift-bootstrap]`.

## ⛔ ЖЁСТКИЕ ГРАНИЦЫ ПРОЕКТА (директива Сергея 27.09, флот-канон)

Работа ТОЛЬКО внутри границ своего проекта. Без явного мандата Директора запрещено:
1. Чужие зоны: репо и папки других профилей/проектов (read-only — и то только по задаче).
2. Общие ресурсы оператора: системный crontab, корень ~/.hermes (кроме своего
   профильного подкаталога), gateway-конфиги, cron-сторы чужих профилей,
   systemd/docker/сеть.
3. Правки и пуши в чужие репозитории.
Свои расписания — только в СВОЁМ cron-скоупе (`hermes -p <имя> cron ...`),
системный crontab не трогать никогда.
Наружное/спорное — NEEDS-DECISION Директору, не самодеятельность.
Нарушение = отключение.
