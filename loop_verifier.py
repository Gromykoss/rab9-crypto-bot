"""Loop Verifier Gate for RAB9 — validates analysis before posting.

Neil XBT structured handoffs pattern (granular Judge):
- verifier checks: number_accuracy, verdict_consistency, cabal_correctness, synthesis_quality
- Each check returns PASS/FAIL with specific issue description
- Overall PASS requires ALL checks PASS
- Uses separate model (different from builder) — never let builder grade own work.

Pattern: CyrilXBT loop-engineering — granular per-check verdicts instead of collapsed score.
Backward compatible: verify_analysis() signature and return dict unchanged.
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
                if line.strip().startswith("#"):
                    continue
                if "XAI_API_KEY" in line:
                    parts = line.split("=", 1)
                    if len(parts) < 2:
                        return ""
                    return parts[1].strip().strip("\"'")
    return ""


def verify_analysis(token_name: str, analysis_text: str, context: dict) -> dict:
    """Grade the RAB9 analysis output using granular per-check verdicts.

    Checks: number_accuracy, verdict_consistency, cabal_correctness, synthesis_quality.
    Each returns PASS/FAIL + issue desc. Overall PASS iff ALL PASS.
    Returns same shape as before for backward compat.
    """
    api_key = _read_api_key()
    if not api_key:
        return {"verdict": "REJECT", "note": "Verifier unavailable"}

    full_report = context.get("full_report", "")

    prompt = f"""You are a strict crypto analysis judge using Neil XBT granular verification.

TOKEN: {token_name}

FULL REPORT (GROUND TRUTH):
```
{full_report[:3000]}
```

AI ANALYSIS TO GRADE:
{analysis_text}

Perform exactly these 4 checks and return PASS/FAIL for each:
1. number_accuracy: Are all numbers consistent with report? (no fabricated MC, volumes etc.)
2. verdict_consistency: Does the synthesis verdict direction match report data?
3. cabal_correctness: Are cabal/KABAL mentions accurate vs report?
4. synthesis_quality: Is the analysis a valid synthesis without contradictions?

Return ONLY valid JSON:
{{"number_accuracy": "PASS|FAIL", "verdict_consistency": "PASS|FAIL", "cabal_correctness": "PASS|FAIL", "synthesis_quality": "PASS|FAIL", "issues": ["specific issue1", ...], "verdict": "PASS|FLAG|FAIL", "score": 0-100}}

Overall verdict: PASS only if ALL 4 checks are PASS. Otherwise FLAG or FAIL based on severity.
"""

    try:
        r = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            json={
                "model": "grok-3-mini",
                "messages": [
                    {"role": "system", "content": "You are a strict granular crypto verifier. Return ONLY the requested JSON with 4 PASS/FAIL checks."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.0,
                "max_tokens": 400,
                "response_format": {"type": "json_object"},
            },
            timeout=TIMEOUT,
        )

        if not r.ok:
            return {"verdict": "REJECT", "note": f"Verifier API error {r.status_code}"}

        content = r.json()["choices"][0]["message"]["content"].strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1].rsplit("```", 1)[0]

        result = json.loads(content)
        if not str(result.get("verdict") or "").strip():
            return {"verdict": "REJECT", "note": "Verifier verdict missing"}
        return result

    except json.JSONDecodeError:
        return {"verdict": "REJECT", "note": "Verifier format error"}
    except Exception as e:
        return {"verdict": "REJECT", "note": f"Verifier error: {str(e)[:100]}"}


if __name__ == "__main__":
    # Test mode
    test_analysis = "Токен TEST с MC $1M демонстрирует сильное давление продаж и не заслуживает внимания."
    test_context = {
        "mc": "$1M", "verdict": "⚫ AVOID", "onchain_risk": "LOW",
        "full_report": "🔍 TEST | MC: $1M\n─── Makers ───\n👥 Всего: 10 (2 buy / 8 sell)\n\n─── Вердикт ───\n→ ⚫ AVOID"
    }
    result = verify_analysis("TEST", test_analysis, test_context)
    print(json.dumps(result, ensure_ascii=False, indent=2))
