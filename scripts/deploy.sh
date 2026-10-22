#!/usr/bin/env bash
# RAB9 Crypto — Deploy Script (standalone-analyzer era, 22.10.2026)
# Правила: бэкап → diff → линт → деплой → рестарт → smoke.
# 22.10: приведён к живой архитектуре после рефакторинга 13.10 (a69d2b6):
# rab9_bot.py / handlers.py / msf_listener.py удалены, юнит rab9-crypto-hermes
# disabled 19.10 → деплой и рестарт живут в rab9-analyzer.service.
set -euo pipefail

DIR="/home/hermes-workspace/rab9"
BACKUP_TS=$(date +%m%d_%H%M)

red()  { echo -e "\033[31m✗ $*\033[0m"; }
green(){ echo -e "\033[32m✓ $*\033[0m"; }
info() { echo -e "\033[36m→ $*\033[0m"; }

info "=== RAB9 Deploy — $(date '+%Y-%m-%d %H:%M:%S') ==="

# 1. Проверка git
cd "$DIR"
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    red "Есть незакоммиченные изменения. Сначала git commit."
    exit 1
fi

# 2. Бэкап ключевых файлов (живое ядро = scorer REQUIRED + точка входа юнита)
info "Бэкап..."
for f in analyzer_main.py msf_http.py cabal_detector.py wallet_intel.py burnie_sentiment_tracker.py; do
    [ -f "$f" ] && cp "$f" "$f.bak.$BACKUP_TS"
done
green "Бэкап готов"

# 3. Линт
info "Линт..."
for f in analyzer_main.py msf_http.py cabal_detector.py wallet_intel.py burnie_sentiment_tracker.py; do
    python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>/dev/null && \
        green "  $f OK" || red "  $f ОШИБКА"
done

# ── EVAL GATE (fleet standard eval-gates, 20.10.2026, kind: service) ──
info "Eval gate (kind: service)..."
if python3 "$HOME/.hermes/scripts/eval_runner.py" "$DIR/evals/deploy-gate/eval.yaml" > /dev/null 2>&1; then
    green "Eval gate PASS"
else
    red "Eval gate FAIL — вердикт: $DIR/evals/deploy-gate/.evals/latest.json"
    exit 2
fi

# 4. Рестарт сервиса (rab9-crypto-hermes disabled 19.10 → живой юнит rab9-analyzer)
info "Рестарт rab9-analyzer.service..."
sudo systemctl restart rab9-analyzer.service
sleep 2
systemctl is-active --quiet rab9-analyzer.service && green "Сервис active" || red "Сервис НЕ active!"

# 5. Health check (ingress :8089 — analyzer)
info "Health check..."
sleep 1
HEALTH=$(curl -s --max-time 5 http://localhost:8089/health 2>/dev/null)
echo "$HEALTH" | grep -q '"ok".*true' && green "Health OK: $HEALTH" || red "Health FAIL: $HEALTH"

# 6. Smoke
info "Smoke..."
bash ~/.hermes/scripts/rab9-smoke-monitor.sh && green "Smoke ПРОЙДЕН" || red "Smoke ПРОВАЛЕН"

green "=== Деплой завершён ==="
