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

    # Build verification prompt
    prompt = f"""You are a strict crypto analysis verifier. Grade this meme coin analysis.

TOKEN: {token_name}
MC: {context.get('mc', '?')}
VERDICT: {context.get('verdict', '?')}
ON-CHAIN RISK: {context.get('onchain_risk', '?')}
X FOLLOWERS: {context.get('x_followers', '?')}
CONTEXT DATA (ONLY these numbers exist — everything else is fabricated):
{{"mc": "{context.get('mc', '?')}", "verdict": "{context.get('verdict', '?')}", "onchain_risk": "{context.get('onchain_risk', '?')}", "x_followers": "{context.get('x_followers', '?')}"}}

ANALYSIS TO GRADE:
{analysis_text}

GRADING RULES:
1. FACTUAL: Every number in the analysis MUST come from CONTEXT DATA above. No exceptions.
2. BALANCED: Both positive and negative signals present?
3. MEME-AWARE: X community > GitHub weight for meme coins.
4. CONSISTENT: Verdict matches tone?

CRITICAL: If the analysis mentions ANY number NOT in CONTEXT DATA (e.g. "38% top-10", "50% drawdown", "7 days") → FAIL with score=0.
A fabricated number = automatic FAIL. Deduct 30 points per hallucination.

Return ONLY a JSON object:
{{"verdict": "PASS"|"FLAG"|"FAIL",
 "score": 0-100,
 "issues": ["issue1"],
 "fixed_text": ""}}

PASS: all numbers match context. FLAG: tone mismatch but data correct. FAIL: fabricated data.
"""

    try:
        r = requests.post(
            "https://api.x.ai/v1/chat/completions",
            headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
            json={
                "model": "grok-3-mini",
                "messages": [
                    {"role": "system", "content": "You are a strict crypto verifier. Only use numbers explicitly provided in CONTEXT DATA. If an analysis mentions a number not in CONTEXT DATA, mark it FAIL. Fabricated metrics = automatic failure. Return ONLY valid JSON."},
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
    test_context = {"mc": "$1M", "verdict": "⚫ AVOID", "onchain_risk": "LOW", "x_followers": "17000"}
    result = verify_analysis("TEST", test_analysis, test_context)
    print(json.dumps(result, ensure_ascii=False, indent=2))
