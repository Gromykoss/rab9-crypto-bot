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

REQUIRED = ["rab9_bot.py", "msf_listener.py", "cabal_detector.py",
            "wallet_intel.py", "msf_http.py", "handlers.py"]

syntax_errors = []
for f in REQUIRED:
    if not Path(f).is_file():
        syntax_errors.append(f"{f}: missing")
        continue
    try:
        py_compile.compile(f, doraise=True)
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
