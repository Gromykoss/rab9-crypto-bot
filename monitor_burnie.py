#!/usr/bin/env python3
"""BURNIE weekly monitor — tracks accumulation signal for election catalyst play."""
import json
import sys
import os

TOKEN = "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump"
RAB9 = os.path.dirname(os.path.abspath(__file__)) if "__file__" in dir() else "/home/hermes-workspace/rab9"
VENV_PY = os.path.join(RAB9, "venv", "bin", "python3")

def run(script, arg):
    import subprocess
    r = subprocess.run([VENV_PY, os.path.join(RAB9, script), arg],
                       capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout) if r.returncode == 0 else {}
    except:
        return {}

# Run analysis
chart = run("chart_analysis.py", TOKEN)
score = run("meme_score.py", TOKEN)
creator = run("creator_monitor.py", TOKEN)

if not chart.get("ok"):
    print("⚠️ BURNIE monitor: chart data unavailable")
    sys.exit(0)

phase = chart.get("phase", "?")
vol_zone = chart.get("vol_trend_zone", "?")
flat_days = chart.get("flat_days", 0)
price = chart.get("price", 0)
ath = chart.get("ath", 0)
drawdown = chart.get("ath_drawdown", 0)
trend = chart.get("trend", "?")
memescore = score.get("score", "?")
tier = score.get("tier", "?")
creator_signal = creator.get("signal", "?")
creator_note = creator.get("note", "")

# Phase emoji
phase_emoji = {
    "accumulation": "📦", "markup": "🚀", "distribution": "📤", "decay": "💤", "dead": "💀"
}.get(phase, "❓")

vol_emoji = {"rising": "▲", "falling": "▼", "stable": "—"}.get(vol_zone, "?")

lines = [
    f"🔥 BURNIE weekly",
    f"",
    f"Цена: ${price:.6f} | ATH: ${ath:.6f} | DD: {drawdown}%",
    f"Тренд: {trend} | Фаза: {phase_emoji} {phase} (vol {vol_emoji})",
    f"Flat zone: {flat_days}д | MemeScore: {memescore}/100 {tier}",
    f"Creator: {creator_signal} — {creator_note}" if creator_signal != "unknown" else "Creator: отслеживается (первый снапшот)",
    f"",
]

# Signal logic
if phase == "accumulation" and vol_zone == "rising":
    lines.append("🚨 СИГНАЛ: НАКОПЛЕНИЕ С РАСТУЩИМ ОБЪЁМОМ — разогрев начался!")
elif phase == "accumulation":
    lines.append("📦 Накопление. Объём пока не растёт — ждём.")
elif phase == "decay" and vol_zone == "falling":
    lines.append("💤 Затухание. Можно добавлять понемногу, ждать разворота.")
elif phase == "decay":
    lines.append("💤 Затухание, объём стабилен. Следим.")
elif phase == "markup":
    lines.append("🚀 Разгон! Не докупать — ждать коррекции.")
elif phase == "distribution":
    lines.append("📤 Распределение. Осторожно.")
else:
    lines.append(f"Фаза: {phase}")

lines.append("")
lines.append("——")
lines.append("Стратегия: накопление малыми частями до выборов (ноябрь 2026).")
lines.append("Триггер: vol ▲ на флэте = разогрев.")

print("\n".join(lines))
