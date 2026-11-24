"""Общие фикстуры тестов RAB9.

Герметичность: тест не должен писать в боевое персистентное состояние
(``~/rab9/data/*.json``). Прод-код резолвит эти пути двумя способами — из env
(``RADAR_X_CACHE_PATH``) и из модульной константы
(``msf_dedupe.DEDUPE_PATH``), поэтому autouse-фикстура уводит оба в ``tmp_path``
для КАЖДОГО теста.

Почему это нужно:

* ``put_cached`` (флуд-проверка TTL в ``test_analysis_filters_gwt.py``)
  перезаписывал боевой ``data/radar_x_per_token.json`` 200 синтетическими
  записями с будущим ``ts`` и вытеснял реальные записи (prune по
  ``max_entries``);
* ``msf_analysis.build_compact_analysis_text`` → ``dedupe_record`` писал в
  боевой ``data/msf_dedupe.json`` из тестов, которые мокали только
  ``check_dedupe`` (ветку чтения), но не ветку записи.

``loop_state.json`` (loop_memory.STATE_FILE) сюда не входит — его изолирует
собственная autouse-фикстура в ``test_standalone_analyzer_gwt.py``.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_prod_state(monkeypatch, tmp_path):
    """Персистентное состояние прода — в per-test tmp, боевые файлы не трогаются."""
    monkeypatch.setenv("RADAR_X_CACHE_PATH", str(tmp_path / "radar_x_per_token.json"))
    import msf_dedupe

    monkeypatch.setattr(msf_dedupe, "DEDUPE_PATH", str(tmp_path / "msf_dedupe.json"))
    yield
