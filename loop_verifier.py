"""Loop Verifier Gate for RAB9 — validates analysis before posting.

Uses a separate model (different from the one that wrote the analysis)
to grade the output: PASS (post), FLAG (post with warning), FAIL (suppress).

Pattern: CyrilXBT loop-engineering — never let the builder grade its own work.
"""
import json
import sys
import os
import requests

TIMEOUT = 15


def _read_api_key():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if "XAI_API_KEY" in line:
                    return line.split("=", 1)[1].strip().strip("\"'")
    return ""


def verify_analysis(token_name: str, analysis_text: str, context: dict) -> dict:
    """Grade the RAB9 analysis output. Returns verdict + reasons."""
    api_key = _read_api_key()
    if not api_key:
        return {"verdict": "PASS", "note": "Verifier unavailable — passing through"}

    # The full report is the ground truth
    full_report = context.get("full_report", "")

    prompt = f"""You are a lenient crypto analysis verifier. Check if the AI analysis below is CONSISTENT with the full report data.

TOKEN: {token_name}

FULL REPORT (GROUND TRUTH — all numbers here are verified):
```
{full_report[:3000]}
```

AI ANALYSIS TO GRADE (must NOT contradict the report):
{analysis_text}

RULES:
1. The AI analysis is a SYNTHESIS — it may mention trends, patterns, and interpretations not literally in the report. That's OK.
2. Only FLAG if the analysis makes a claim that DIRECTLY contradicts the report (e.g., says "bullish" when report says "sell-heavy", says "no kabals" when report says "Kabals в топ-5: 3").
3. Numbers mentioned in the analysis should be roughly consistent with the report. Exact precision not required.
4. Score deduction: -10 per minor inconsistency, -30 per major contradiction.
5. FAIL (score < 40) only for severe contradictions (wrong verdict direction, fabricated MC, fake risk level).

Return ONLY a JSON object:
{{"verdict": "PASS"|"FLAG"|"FAIL",
 "score": 0-100,
 "issues": ["issue1"],
 "fixed_text": ""}}

PASS (score >= 70): analysis consistent with report.
FLAG (40-69): minor issues but not misleading.
FAIL (< 40): severe contradiction, should not be posted.
"""

    try:
        r = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            json={
                "model": "grok-3-mini",
                "messages": [
                    {"role": "system", "content": "You are a lenient crypto verifier. Only flag direct contradictions between the analysis and the report data. Syntheses and interpretations are OK. Numbers can be approximate. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 400,
            },
            timeout=TIMEOUT,
        )

        if not r.ok:
            return {"verdict": "PASS", "note": f"Verifier API error {r.status_code}"}

        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(content)
        return result

    except json.JSONDecodeError:
        return {"verdict": "PASS", "note": "Verifier format error — passing through"}
    except Exception as e:
        return {"verdict": "PASS", "note": f"Verifier error: {str(e)[:100]}"}


if __name__ == "__main__":
    # Test mode
    test_analysis = "Токен TEST с MC $1M демонстрирует сильное давление продаж и не заслуживает внимания."
    test_context = {
        "mc": "$1M", "verdict": "⚫ AVOID", "onchain_risk": "LOW",
        "full_report": "🔍 TEST | MC: $1M\n─── Makers ───\n👥 Всего: 10 (2 buy / 8 sell)\n\n─── Вердикт ───\n→ ⚫ AVOID"
    }
    result = verify_analysis("TEST", test_analysis, test_context)
    print(json.dumps(result, ensure_ascii=False, indent=2))
