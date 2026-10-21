#!/usr/bin/env python3
"""rab9 deploy-gate scorer (kind: service) — флотовый стандарт eval-gates, 20.10.2026.

Детерминированная pre-deploy проверка: py_compile синтаксис ключевых модулей +
наличие обязательных файлов. pytest в окружении нет — при появлении тестов
расширить scorer (метрика tests_passed_ratio). Пишет metrics.json:
  {"syntax_ok": 1.0|0.0, "files_present": 1.0|0.0}
"""
import json
import py_compile
from pathlib import Path

# Путь к модулям — от __file__ (раннер исполняет scorer с cwd = директория eval):
# evals/deploy-gate/scorer.py → parents[2] = корень rab9
ROOT = Path(__file__).resolve().parents[2]
# Живое ядро (факт 21.10): rab9_bot/msf_listener/handlers удалены при рефакторинге
# 13.10 (deploy.sh частично протух — юнит rab9-crypto-hermes disabled);
# деплоится и живёт: BURNIE-трекер + enforced-тройка.
REQUIRED = ["burnie_sentiment_tracker.py", "msf_http.py",
            "cabal_detector.py", "wallet_intel.py"]

syntax_errors = []
for f in REQUIRED:
    p = ROOT / f
    if not p.is_file():
        syntax_errors.append(f"{f}: missing")
        continue
    try:
        py_compile.compile(str(p), doraise=True)
    except py_compile.PyCompileError as e:
        syntax_errors.append(f"{f}: {e}")

metrics = {
    "files_present": 1.0 if not any("missing" in e for e in syntax_errors) else 0.0,
    "syntax_ok": 1.0 if not syntax_errors else 0.0,
}
Path("metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2) + "\n")
if syntax_errors:
    print("ERRORS: " + "; ".join(syntax_errors))
print(json.dumps(metrics, ensure_ascii=False))
