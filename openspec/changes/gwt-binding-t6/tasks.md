# Tasks: gwt-binding-t6

MUST NOT (держим в голове при каждой задаче):
* не менять поведение продакшн-кода (только тесты/спеки/карта);
* не «подгонять» тест под код: ожидаемое значение — из текста сценария спеки;
* не закрывать сценарий заглушкой: нет реализации — сценарий остаётся prose и идёт в отчёт.

Формат id: `<домен>.<snake_case>` (совпадает с `^[a-z0-9-]+\.[a-z0-9_]+$`).

## Итог (19.11, финал)

**45 сценариев из 46** связаны (карточка с id + pytest-маркер + запись в `scenario_map.yaml` +
код домена). Первая волна дала 42; ещё три (`analysis-filters.supply_concentration_flag`,
`analysis-filters.social_negative_priority`, `analysis-filters.confirmed_scam_drop`) закрыты
реальным поведением домена отдельными коммитами `ea179e5`…`ef2c4bd` — не заглушками: сначала
появился код (оператор концентрации top-10, per-token social-weight на rate_gate с одним
X-вызовом на токен, queue-level DROP в обе очереди + `sink(reject)`), затем карточка и тест.

Не связан один сценарий — `standalone-analyzer` «агент забрал дайджест»
(прежнее имя `digest_offset_advance`): помечен `<!-- no-ci -->` со ссылкой на
`delivery-reader-contract` — доставка и offset принадлежат внешнему RAB9-агенту, в репозитории
реализации нет и по контракту быть не должно. Линтер: **0 ошибок, 1 предупреждение**
(ровно этот prose-сценарий) вместо 46 предупреждений на старте.

Пять FROZEN-спек после T6: pumpportal-ingress **v0.4**, analysis-filters **v1.4**,
standalone-analyzer **v1.4**, wallet-watch **v1.1**, accumulation-radar **v1.1** —
текст шагов сценариев не менялся, менялась форма карточки (+3 версии закрыты реальным
поведением по ходу T6).

## Волна 0 — каркас

- [x] T0.1 change-каталог `openspec/changes/gwt-binding-t6/` (proposal.md, tasks.md) —
      критерий: файлы в репо, поведенческих дельт не заявлено (биндинг).
- [x] T0.2 линтер понимает prose-класс (коммит `eb14688`) — критерий: `lint-cards` зелёный
      на prose-форме, полнота GIVEN/WHEN/THEN проверяется (10 кейсов проверки формы).

## Волна 1 — pumpportal-ingress (9 сценариев)

- [x] T1.1 `tests/test_pumpportal_ingress_gwt.py`: тест на каждый из 9 сценариев, маркеры
      `pumpportal-ingress.*` — критерий: `pytest tests/test_pumpportal_ingress_gwt.py -q` зелёный.
- [x] T1.2 Спека: карточные заголовки + пункты WHEN/THEN, v0.3→v0.4, запись в таблице фризов —
      критерий: линтер 0 ошибок, текст сценариев дословно сохранён.
- [x] T1.3 Карта: 9 записей `card/test/code` — критерий: `check_scenario_map` без mismatch.

## Волна 2 — wallet-watch (4) и accumulation-radar (6)

- [x] T2.1 `tests/test_wallet_watch_gwt.py` (4) — критерий: файл зелёный.
- [x] T2.2 `tests/test_accumulation_radar_gwt.py` (6) — критерий: файл зелёный.
- [x] T2.3 Спеки: карточки + v1.0→v1.1 у обеих, таблица фризов — критерий: линтер 0 ошибок.
- [x] T2.4 Карта: 10 записей — критерий: `check_scenario_map` без mismatch.

## Волна 3 — standalone-analyzer (15) и analysis-filters (12)

- [x] T3.1 `tests/test_standalone_analyzer_gwt.py` (15) — критерий: файл зелёный.
- [x] T3.2 `tests/test_analysis_filters_gwt.py` (12) — критерий: файл зелёный.
- [x] T3.3 Спеки: карточки, v1.2→v1.3 и v1.1→v1.2, таблица фризов — критерий: линтер 0 ошибок.
- [x] T3.4 Карта: 27 записей — критерий: `check_scenario_map` без mismatch.

## Волна 4 — уборка whitelist и верификация

- [x] T4.1 Убрать из `WHITELIST` строки, покрытые картой (`tests/test_pumpportal_listener.py`,
      `tests/test_standalone_analyzer.py` остаются — это тесты домена, но код домена
      `analyzer_main.py`/`pumpportal_listener.py`/`sink.py` должен уйти из whitelist и попасть
      в карту как `code`) — критерий: `check_diff_coverage` не ругается на изменённые файлы.
- [x] T4.2 Негативная проверка честности тестов: мутация 2–3 констант домена по очереди →
      соответствующий сценарный тест обязан упасть; константа возвращается на место —
      критерий: по каждому домену ≥1 подтверждённая мутация.
- [x] T4.3 Полные гейты: pytest всего набора, линтер, `check_scenario_map --base`, прогон
      workflow `gwt` на main — критерий: всё зелёное, ссылка на прогон в отчёте.
      Факт 19.11: `pytest tests/ -q` → **101 passed** (сценарный срез `-m scenario` → 63 passed,
      38 deselected); `lint_gwt_cards.py openspec/specs --map .ci/scenario_map.yaml` →
      **0 errors, 1 expected warning**; `check_scenario_map.py --base HEAD~10` →
      «scenario map completeness OK: 51 scenarios»; workflow `gwt` на `main` (коммит `6843650`) —
      run [44530242330](https://github.com/Gromykoss/rab9-crypto-bot/actions/runs/44530242330),
      jobs lint-cards / completeness / scenarios — все **success**.
- [x] T4.4 Отчёт владельцу: связано N из 46, что осталось prose и почему, остаточные риски.
      Отчёт отдан владельцу в чат 19.11 (45 из 46; остаток — `no-ci` доставка; риски в отчёте).
